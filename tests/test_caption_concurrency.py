"""Parallel generation must preserve serial writes, recovery and cancellation."""
import asyncio
import sqlite3
import threading
import time

import pytest
from fastapi import HTTPException
from PIL import Image
from pydantic import ValidationError

from mikazuki.llm.config import UnifiedConfigStore, config_revision
from mikazuki.llm.contracts import LLMProfile
from mikazuki.llm.http import LLMRequestError
from mikazuki.llm.scheduler import LocalRequestScheduler
from mikazuki.llm.service import UnifiedLLMService
from mikazuki.tagger.caption_api import CaptionJobRequest, _snapshot_request
from mikazuki.tagger.caption_job import CaptionJobManager
from mikazuki.tagger.caption_maintenance import rollback_job
from mikazuki.tagger.caption_store import CaptionJobStore
from mikazuki.tagger.progress import tagger_progress


PROFILE = LLMProfile(id="fake", name="Fake", model="fake", source="remote",
                     endpoint="http://localhost/v1/chat/completions",
                     capabilities=("vision",), languages=("en",))
CONTENT = '{"caption":"A small sample image.","language":"en"}'


@pytest.fixture
def managers():
    tagger_progress.reset_idle()
    created = []

    def create(service, store=None):
        manager = CaptionJobManager(service, job_store=store)
        created.append(manager)
        return manager

    yield create
    for manager in created:
        if manager.is_busy():
            manager.cancel()
        if manager._thread and manager._thread.ident:
            manager._thread.join(timeout=5)
    tagger_progress.reset_idle()


def images(directory, count):
    paths = []
    for index in range(count):
        path = directory / f"{index:02d}.png"
        Image.new("RGB", (16, 16), (index, 50, 50)).save(path)
        paths.append(path)
    return paths


def wait(manager):
    manager._thread.join(timeout=5)
    assert not manager._thread.is_alive()
    return manager.status()


class Vision:
    def __init__(self, delays=None, failures=()):
        self.delays = delays or {}
        self.failures = set(failures)
        self.calls = []
        self.finished = []
        self.active = 0
        self.peak = 0
        self.loops = set()

    async def complete_vision(self, image_path, *_args, **_kwargs):
        self.calls.append(image_path.name)
        self.loops.add(asyncio.get_running_loop())
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(self.delays.get(image_path.name, .02))
            self.finished.append(image_path.name)
            if image_path.name in self.failures:
                raise RuntimeError("synthetic failure")
            return PROFILE, {"choices": [{"finish_reason": "stop"}]}, CONTENT, {}
        finally:
            self.active -= 1


def test_request_defaults_and_tag_parameter_boundary():
    assert CaptionJobRequest(path="images").concurrency == 3
    assert _snapshot_request(CaptionJobRequest(path="images"))["concurrency"] == 3
    assert "concurrency" not in _snapshot_request(CaptionJobRequest(path="images", mode="tag"))
    with pytest.raises(HTTPException) as error:
        _snapshot_request(CaptionJobRequest(path="images", mode="tag", concurrency=3))
    assert error.value.status_code == 400
    assert error.value.detail["code"] == "tagger_parameter_unsupported"


@pytest.mark.parametrize("value", [0, 17, True, False, 2.5, "3", None])
def test_concurrency_rejects_out_of_range_and_non_integer_values(value):
    with pytest.raises(ValidationError):
        CaptionJobRequest(path="images", concurrency=value)


@pytest.mark.parametrize("concurrency", [1, 3, 5])
def test_bounded_generation_uses_one_loop_and_ordered_reports(tmp_path, managers, concurrency):
    images(tmp_path, 7)
    service = Vision()
    manager = managers(service)
    manager.start({"path": str(tmp_path), "mode": "natural", "concurrency": concurrency})
    status = wait(manager)
    assert service.peak == concurrency
    assert service.active == 0
    assert len(service.loops) == 1
    assert status["succeeded"] == status["current"] == status["total"] == 7
    assert status["snapshot"]["concurrency"] == concurrency
    assert [item["index"] for item in status["report"]["items"]] == list(range(7))


def test_out_of_order_completion_keeps_backup_and_rollback_indices(tmp_path, managers):
    paths = images(tmp_path, 4)
    for index, image in enumerate(paths):
        image.with_suffix(".txt").write_bytes(f"Original caption {index}.\r\n".encode())
    service = Vision({"00.png": .08, "01.png": .06, "02.png": .01})
    store = CaptionJobStore(tmp_path / "jobs.sqlite3")
    manager = managers(service, store)
    manager.start({"path": str(tmp_path), "mode": "natural", "concurrency": 3, "conflict_action": "copy"})
    status = wait(manager)
    assert service.finished[0] == "02.png"
    for index, item in enumerate(status["report"]["items"]):
        assert item["index"] == index
        assert item["filename"] == paths[index].name
        assert store.get_backup(status["job_id"], index)["content"] == f"Original caption {index}.\r\n".encode()
    assert rollback_job(manager, status["job_id"])["restored"] == 4
    for index, image in enumerate(paths):
        assert image.with_suffix(".txt").read_bytes() == f"Original caption {index}.\r\n".encode()


@pytest.mark.parametrize("complete_first", [False, True])
def test_cancel_clears_all_inflight_and_pending_without_late_writes(tmp_path, managers, complete_first):
    images(tmp_path, 7)
    entered = threading.Event()

    class WaitingVision(Vision):
        aborted = 0

        async def complete_vision(self, image_path, *_args, **_kwargs):
            self.calls.append(image_path.name)
            if complete_first and image_path.name == "00.png":
                return PROFILE, {"choices": [{"finish_reason": "stop"}]}, CONTENT, {}
            self.active += 1
            if self.active == 3:
                entered.set()
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                self.aborted += 1
                # A provider that returns despite cancellation must not write.
                return PROFILE, {"choices": [{"finish_reason": "stop"}]}, CONTENT, {}
            finally:
                self.active -= 1

    service = WaitingVision()
    manager = managers(service)
    manager.start({"path": str(tmp_path), "mode": "natural", "concurrency": 3})
    assert entered.wait(timeout=3)
    manager.cancel()
    status = wait(manager)
    assert status["phase"] == "cancelled"
    completed = int(complete_first)
    assert status["current"] == status["succeeded"] == completed
    assert status["cancelled"] == 7 - completed
    assert len(service.calls) == 3 + completed
    assert service.aborted == 3
    assert service.active == 0
    assert len(list(tmp_path.glob("*.txt"))) == completed
    assert not tagger_progress.is_busy()


def test_retry_after_restart_keeps_frozen_concurrency_and_only_failed_paths(tmp_path, managers):
    paths = images(tmp_path, 5)
    store = CaptionJobStore(tmp_path / "jobs.sqlite3")
    service = Vision({"01.png": .05}, failures={"01.png", "03.png"})
    first = managers(service, store)
    first.start({"path": str(tmp_path), "mode": "natural", "concurrency": 4})
    status = wait(first)
    assert status["failed"] == 2
    assert status["current"] == 5
    before = {str(path): path.with_suffix(".txt").read_bytes() for path in paths if path.with_suffix(".txt").exists()}
    retry_service = Vision()
    restarted = managers(retry_service, CaptionJobStore(store.path))
    restarted.retry_failed()
    retried = wait(restarted)
    assert retry_service.calls == ["01.png", "03.png"]
    assert retried["snapshot"]["concurrency"] == 4
    assert retried["parent_job_id"] == status["job_id"]
    assert retried["succeeded"] == retried["current"] == 2
    for path in paths:
        if str(path) in before:
            assert path.with_suffix(".txt").read_bytes() == before[str(path)]


def test_write_intent_failure_stops_other_workers_and_recovers_written_image(tmp_path, managers, monkeypatch):
    images(tmp_path, 4)
    store = CaptionJobStore(tmp_path / "jobs.sqlite3")
    original = store.remember_format

    def fail_format(*_args, **_kwargs):
        raise sqlite3.OperationalError("synthetic persistence failure")

    monkeypatch.setattr(store, "remember_format", fail_format)
    # All replies become ready in the same loop turn. Storage failure must set
    # the stop flag before gather propagates it and before a sibling can commit.
    service = Vision()
    manager = managers(service, store)
    manager.start({"path": str(tmp_path), "mode": "natural", "concurrency": 3})
    status = wait(manager)
    assert status["phase"] == "error"
    assert status["errors"][0]["code"] == "caption_persistence_failed"
    assert service.active == 0
    assert len(service.calls) == 3
    written = list(tmp_path.glob("*.txt"))
    assert len(written) == 1
    written_index = int(written[0].stem)
    assert store.get()["recovery"]["intent"]["index"] == written_index
    monkeypatch.setattr(store, "remember_format", original)
    recovered = managers(Vision(), CaptionJobStore(store.path)).status()
    assert recovered["succeeded"] == 1
    assert recovered["failed"] == 3
    assert recovered["report"]["items"][written_index]["recovered_write"] is True
    assert [item["index"] for item in recovered["report"]["items"]] == [0, 1, 2, 3]


@pytest.mark.parametrize("stage", ["dispatch", "error_record", "completion_record"])
def test_every_persistence_stage_stops_ready_siblings(tmp_path, managers, monkeypatch, stage):
    images(tmp_path, 4)
    store = CaptionJobStore(tmp_path / "jobs.sqlite3")
    save = store.save
    failed = []

    def fail_once(state, *_args, **_kwargs):
        statuses = [item["status"] for item in state["report"]["items"]]
        matches = (
            stage == "dispatch" and state["filename"] == "00.png" and not statuses
            or stage == "error_record" and "error" in statuses
            or stage == "completion_record" and "written" in statuses
        )
        if matches and not failed:
            failed.append(stage)
            raise sqlite3.OperationalError("synthetic save failure")
        return save(state, *_args, **_kwargs)

    monkeypatch.setattr(store, "save", fail_once)
    service = Vision(delays={"00.png": .001, "01.png": .2, "02.png": .2} if stage == "error_record" else None,
                     failures={"00.png"} if stage == "error_record" else ())
    manager = managers(service, store)
    manager.start({"path": str(tmp_path), "mode": "natural", "concurrency": 3})
    status = wait(manager)
    assert failed == [stage]
    assert status["phase"] == "error"
    assert status["errors"][0]["code"] == "caption_persistence_failed"
    assert service.active == 0
    assert len(service.calls) == (0 if stage == "dispatch" else 3)
    files = list(tmp_path.glob("*.txt"))
    assert len(files) == int(stage == "completion_record")
    saved = store.get()
    if stage == "completion_record":
        assert saved["recovery"]["intent"]["index"] == int(files[0].stem)
    recovered = managers(Vision(), CaptionJobStore(store.path)).status()
    assert recovered["current"] == int(stage != "dispatch")
    assert recovered["succeeded"] == int(stage == "completion_record")
    assert recovered["failed"] == 4 - int(stage == "completion_record")


def configured_service(tmp_path, remote=True):
    store = UnifiedConfigStore(tmp_path / "translation.json")
    profiles = [{"id": "local", "name": "Local", "model": "local", "source": "managed-local",
                 "endpoint": "http://localhost/v1/chat/completions", "capabilities": ["vision"], "languages": ["en"]}]
    if remote:
        profiles.insert(0, {**profiles[0], "id": "remote", "name": "Remote", "model": "remote", "source": "remote", "api_key": "fixture-runtime-key"})
    store.save({"profiles": profiles, "local_fallback_enabled": True})
    for selected in store.load()["profiles"]:
        store.record_verification(selected["id"], config_revision(selected), "vision")
    return UnifiedLLMService(store)


@pytest.mark.parametrize("remote", [False, True])
def test_high_concurrency_local_and_remote_fallback_keep_one_local_inference(tmp_path, managers, monkeypatch, remote):
    images(tmp_path, 8)
    from mikazuki.llm import scheduler, service as service_module
    queue = LocalRequestScheduler()
    monkeypatch.setattr(scheduler, "shared_local_scheduler", queue)
    counts = {"remote": 0, "local": 0, "active": 0, "peak": 0}

    async def transport(profile, _payload, **_kwargs):
        counts[profile.model] += 1
        if profile.source == "remote":
            await asyncio.sleep(.01)
            raise LLMRequestError("synthetic remote failure", "llm_auth_failed")
        counts["active"] += 1
        counts["peak"] = max(counts["peak"], counts["active"])
        try:
            await asyncio.sleep(.01)
            return {"choices": [{"finish_reason": "stop"}]}, CONTENT
        finally:
            counts["active"] -= 1

    monkeypatch.setattr(service_module, "chat_completion", transport)
    manager = managers(configured_service(tmp_path, remote))
    manager.start({"path": str(tmp_path), "mode": "natural", "concurrency": 16,
                   "allow_local_fallback": True, "profile_id": "remote" if remote else "local"})
    status = wait(manager)
    assert status["succeeded"] == 8
    assert status["failed"] == 0
    assert counts["local"] == 8
    assert counts["remote"] == (8 if remote else 0)
    assert counts["peak"] == 1
    assert counts["active"] == 0
    assert {item["source"] for item in status["report"]["items"]} == {"managed-local"}
    assert queue.snapshot()["active"] == queue.snapshot()["waiting"] == 0


def test_local_capacity_wait_is_cancelled_and_leaves_other_requests_running(tmp_path, managers, monkeypatch):
    images(tmp_path, 5)
    from mikazuki.llm import scheduler, service as service_module
    queue = LocalRequestScheduler()
    monkeypatch.setattr(scheduler, "shared_local_scheduler", queue)
    release = threading.Event()
    entered = threading.Event()
    local_calls = []

    async def occupy():
        async with queue.slot():
            entered.set()
            while not release.is_set():
                await asyncio.sleep(.01)

    async def fill_queue():
        await asyncio.gather(*(occupy() for _ in range(3)))

    thread = threading.Thread(target=lambda: asyncio.run(fill_queue()), daemon=True)
    thread.start()
    assert entered.wait(timeout=2)
    try:
        deadline = time.monotonic() + 2
        while queue.snapshot()["waiting"] < 2 and time.monotonic() < deadline:
            time.sleep(.01)
        assert queue.snapshot()["waiting"] == 2

        async def transport(_profile, _payload, **_kwargs):
            local_calls.append(1)
            return {"choices": [{"finish_reason": "stop"}]}, CONTENT

        monkeypatch.setattr(service_module, "chat_completion", transport)
        manager = managers(configured_service(tmp_path, False))
        manager.start({"path": str(tmp_path), "mode": "natural", "concurrency": 5, "profile_id": "local", "allow_local_fallback": True})
        time.sleep(.12)
        assert manager.status()["failed"] == 0
        assert manager.is_busy()
        assert local_calls == []
        manager.cancel()
        status = wait(manager)
        assert status["cancelled"] == 5
        assert status["phase"] == "cancelled"
        assert queue.snapshot()["active"] == 1
        assert queue.snapshot()["waiting"] == 2
        assert not list(tmp_path.glob("*.txt"))
    finally:
        release.set()
        thread.join(timeout=3)
    assert not thread.is_alive()
    assert queue.snapshot()["active"] == queue.snapshot()["waiting"] == 0


def test_cancelling_local_inference_releases_the_slot_and_caption_backlog(tmp_path, managers, monkeypatch):
    images(tmp_path, 8)
    from mikazuki.llm import scheduler, service as service_module
    queue = LocalRequestScheduler()
    monkeypatch.setattr(scheduler, "shared_local_scheduler", queue)
    entered = threading.Event()
    calls = []
    aborted = []

    async def transport(_profile, _payload, **_kwargs):
        calls.append(1)
        entered.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            aborted.append(1)
            return {"choices": [{"finish_reason": "stop"}]}, CONTENT

    monkeypatch.setattr(service_module, "chat_completion", transport)
    manager = managers(configured_service(tmp_path, False))
    manager.start({"path": str(tmp_path), "mode": "natural", "concurrency": 16, "profile_id": "local", "allow_local_fallback": True})
    assert entered.wait(timeout=3)
    manager.cancel()
    status = wait(manager)
    assert status["phase"] == "cancelled"
    assert status["cancelled"] == 8
    assert calls == aborted == [1]
    assert not list(tmp_path.glob("*.txt"))
    assert queue.snapshot()["active"] == queue.snapshot()["waiting"] == 0


def test_new_job_waits_for_previous_worker_to_release_runtime(tmp_path, managers, monkeypatch):
    images(tmp_path, 1)
    service = Vision()
    manager = managers(service)
    released = threading.Event()
    exit_worker = threading.Event()
    release = tagger_progress.release

    def hold_after_release():
        release()
        released.set()
        assert exit_worker.wait(timeout=3)

    monkeypatch.setattr(tagger_progress, "release", hold_after_release)
    manager.start({"path": str(tmp_path), "mode": "natural"})
    assert released.wait(timeout=3)
    try:
        assert manager.status()["phase"] == "done"
        assert not tagger_progress.is_busy()
        assert manager._thread.is_alive()
        with pytest.raises(RuntimeError):
            manager.start({"path": str(tmp_path), "mode": "natural"})
        assert service.calls == ["00.png"]
    finally:
        exit_worker.set()
        wait(manager)
    monkeypatch.setattr(tagger_progress, "release", release)
    manager.start({"path": str(tmp_path), "mode": "natural"})
    assert wait(manager)["skipped"] == 1


def test_cancel_at_local_semaphore_admission_never_starts_next_provider(tmp_path, managers, monkeypatch):
    images(tmp_path, 5)
    from mikazuki.llm import scheduler, service as service_module
    queue = LocalRequestScheduler()
    monkeypatch.setattr(scheduler, "shared_local_scheduler", queue)
    original_semaphore = asyncio.Semaphore
    holder = {}
    calls = []

    class CancellingAdmission:
        def __init__(self, value):
            self.semaphore = original_semaphore(value)
            self.admitted = 0

        async def __aenter__(self):
            await self.semaphore.acquire()
            self.admitted += 1
            if self.admitted == 2:
                # Deterministic cancellation exactly after local admission,
                # before the independent 50 ms poll notices the stop flag.
                holder["manager"].cancel()

        async def __aexit__(self, *_args):
            self.semaphore.release()

    monkeypatch.setattr(asyncio, "Semaphore", CancellingAdmission)

    async def transport(_profile, _payload, **_kwargs):
        calls.append(1)
        await asyncio.sleep(.01)
        return {"choices": [{"finish_reason": "stop"}]}, CONTENT

    monkeypatch.setattr(service_module, "chat_completion", transport)
    manager = holder["manager"] = managers(configured_service(tmp_path, False))
    manager.start({"path": str(tmp_path), "mode": "natural", "concurrency": 5, "profile_id": "local", "allow_local_fallback": True})
    state = wait(manager)
    assert state["phase"] == "cancelled"
    assert calls == [1]
    # The first request may have committed before cancellation. No later
    # admission may call the provider or produce an additional caption.
    files = list(tmp_path.glob("*.txt"))
    assert len(files) == state["succeeded"] <= 1
    assert not files or files[0].name == "00.txt"
    assert queue.snapshot()["active"] == queue.snapshot()["waiting"] == 0


def test_cancel_at_shared_scheduler_admission_never_calls_provider(tmp_path, managers, monkeypatch):
    from contextlib import asynccontextmanager
    images(tmp_path, 5)
    from mikazuki.llm import scheduler, service as service_module
    queue = LocalRequestScheduler()
    monkeypatch.setattr(scheduler, "shared_local_scheduler", queue)
    holder = {}
    calls = []

    @asynccontextmanager
    async def admitted_then_cancelled(_profile):
        async with queue.slot():
            holder["manager"].cancel()
            yield

    async def transport(_profile, _payload, **_kwargs):
        calls.append(1)
        return {"choices": [{"finish_reason": "stop"}]}, CONTENT

    monkeypatch.setattr(scheduler, "local_request_slot", admitted_then_cancelled)
    monkeypatch.setattr(service_module, "chat_completion", transport)
    manager = holder["manager"] = managers(configured_service(tmp_path, False))
    manager.start({"path": str(tmp_path), "mode": "natural", "concurrency": 5, "profile_id": "local", "allow_local_fallback": True})
    assert wait(manager)["phase"] == "cancelled"
    assert calls == []
    assert not list(tmp_path.glob("*.txt"))
    assert queue.snapshot()["active"] == queue.snapshot()["waiting"] == 0


def test_cancel_during_capacity_retry_never_retries_admission(tmp_path, managers, monkeypatch):
    from contextlib import asynccontextmanager
    images(tmp_path, 3)
    from mikazuki.llm import scheduler, service as service_module
    holder = {}
    admissions = []
    calls = []
    original_sleep = asyncio.sleep

    @asynccontextmanager
    async def full_then_available(_profile):
        admissions.append(1)
        if len(admissions) == 1:
            holder["manager"].cancel()
            raise LLMRequestError("synthetic full queue", "llm_local_queue_full")
        yield

    async def immediate_retry(delay, *args, **kwargs):
        # Keep the independent cancellation poll suspended: retry's own check
        # must reject admission, even before a loop turn can cancel its task.
        if delay != .05:
            await original_sleep(delay, *args, **kwargs)

    async def transport(_profile, _payload, **_kwargs):
        calls.append(1)
        return {"choices": [{"finish_reason": "stop"}]}, CONTENT

    monkeypatch.setattr(scheduler, "local_request_slot", full_then_available)
    monkeypatch.setattr(service_module, "chat_completion", transport)
    monkeypatch.setattr(asyncio, "sleep", immediate_retry)
    manager = holder["manager"] = managers(configured_service(tmp_path, False))
    manager.start({"path": str(tmp_path), "mode": "natural", "concurrency": 3, "profile_id": "local", "allow_local_fallback": True})
    assert wait(manager)["phase"] == "cancelled"
    assert admissions == [1]
    assert calls == []
    assert not list(tmp_path.glob("*.txt"))


@pytest.mark.parametrize("swallow_cancel", [False, True])
def test_repeated_local_cancellation_never_admits_a_second_provider(tmp_path, managers, monkeypatch, swallow_cancel):
    from mikazuki.llm import scheduler, service as service_module
    queue = LocalRequestScheduler()
    monkeypatch.setattr(scheduler, "shared_local_scheduler", queue)
    entered = threading.Event()
    calls = []

    async def transport(_profile, _payload, **_kwargs):
        calls.append(1)
        entered.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            if not swallow_cancel:
                raise
            return {"choices": [{"finish_reason": "stop"}]}, CONTENT

    monkeypatch.setattr(service_module, "chat_completion", transport)
    service = configured_service(tmp_path, False)
    for iteration in range(20):
        case = tmp_path / f"cancel-{iteration}"
        case.mkdir()
        images(case, 5)
        entered.clear()
        before = len(calls)
        manager = managers(service)
        manager.start({"path": str(case), "mode": "natural", "concurrency": 16, "profile_id": "local", "allow_local_fallback": True})
        assert entered.wait(timeout=3)
        manager.cancel()
        assert wait(manager)["phase"] == "cancelled"
        assert len(calls) - before == 1
        assert not list(case.glob("*.txt"))
        assert queue.snapshot()["active"] == queue.snapshot()["waiting"] == 0
