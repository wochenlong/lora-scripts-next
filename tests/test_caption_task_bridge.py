import asyncio
import json
import threading
import uuid
from pathlib import Path

import pytest

from mikazuki.llm.contracts import LLMProfile
from mikazuki.tagger.caption_job import CaptionJobManager, CaptionPersistenceError
from mikazuki.tagger.caption_store import CaptionJobStore
from mikazuki.tagger.task_bridge import CaptionTaskBridge
from mikazuki.tagger.progress import tagger_progress
from mikazuki.tasks import TaskManager, TaskStatus


class Vision:
    def __init__(self, wait=False):
        self.wait = wait
        self.started = threading.Event()
        self.calls = []
        self.aborted = False

    async def complete_vision(self, image, prompt, **kwargs):
        self.calls.append(kwargs)
        self.started.set()
        try:
            while self.wait:
                await asyncio.sleep(.01)
        except asyncio.CancelledError:
            self.aborted = True
            raise
        return LLMProfile(id="fake", name="fake", model="fake", endpoint="http://localhost/v1/chat/completions", source="local-endpoint", capabilities=("vision",), languages=("zh-CN",)), {"choices": [{"finish_reason": "stop"}]}, '{"caption":"一只猫。","language":"zh-CN"}', {}


@pytest.fixture
def setup(tmp_path):
    image = tmp_path / "images" / "a.png"
    image.parent.mkdir()
    image.write_bytes(b"test-image")
    tasks = TaskManager()
    bridge = CaptionTaskBridge(tmp_path / "user_data", tasks)
    store = CaptionJobStore(tmp_path / "jobs.sqlite3")
    tagger_progress.reset_idle()
    managers = []

    def create(service):
        manager = CaptionJobManager(service, job_store=store, task_bridge=bridge)
        managers.append(manager)
        return manager

    yield image, tasks, bridge, store, create
    for manager in managers:
        if manager.is_busy():
            manager.cancel()
        if manager._thread and manager._thread.ident is not None:
            manager._thread.join(timeout=5)
    tagger_progress.reset_idle()


def test_new_job_archives_frozen_configuration_and_appears_in_task_manager(setup):
    image, tasks, bridge, _store, create = setup
    service = Vision()
    manager = create(service)
    result = manager.start({"path": str(image.parent), "mode": "natural", "system_prompt": "可见事实", "max_tokens": 123, "temperature": .2, "model_id": "llm:fake", "runtime": "local", "api_key": "should-not-persist"})
    manager._thread.join(timeout=5)
    assert manager.status()["succeeded"] == 1, manager.status()
    job_id = result["job_id"]
    directory = bridge.locations[job_id]
    assert directory.relative_to(bridge.root).parts[:2] == ("tasks", "dataset-tagger")
    config = json.loads((directory / "config.json").read_text(encoding="utf-8"))
    assert config["parameters"]["system_prompt"] == "可见事实"
    assert config["parameters"]["max_tokens"] == 123
    assert "should-not-persist" not in json.dumps(config)
    archived = json.loads((directory / "task.json").read_text(encoding="utf-8"))
    assert archived["state"]["succeeded"] == 1
    assert tasks.tasks[job_id].status == TaskStatus.FINISHED
    assert tasks.tasks[job_id].metadata["kind"] == "dataset_caption"
    assert str(image.parent) not in json.dumps(tasks.dump())


def test_task_page_stop_cancels_the_actual_caption_inference_without_writing(setup):
    image, tasks, _bridge, _store, create = setup
    service = Vision(wait=True)
    manager = create(service)
    job_id = manager.start({"path": str(image.parent), "mode": "natural"})["job_id"]
    assert service.started.wait(timeout=3)
    tasks.terminate_task(job_id)
    manager._thread.join(timeout=5)
    assert not manager._thread.is_alive()
    assert service.aborted
    assert manager.status()["phase"] == "cancelled"
    assert tasks.tasks[job_id].status == TaskStatus.TERMINATED
    assert not image.with_suffix(".txt").exists()


def test_archive_failure_prevents_worker_and_provider_start(setup, monkeypatch):
    image, tasks, bridge, _store, create = setup
    service = Vision()
    manager = create(service)

    def fail(*args, **kwargs):
        raise OSError("disk unavailable")

    monkeypatch.setattr(bridge, "_write", fail)
    with pytest.raises(CaptionPersistenceError):
        manager.start({"path": str(image.parent), "mode": "natural"})
    assert not service.calls
    assert not tasks.dump()
    assert not manager._thread.is_alive()
    assert not tagger_progress.is_busy()


def test_task_page_delete_preserves_dataset_and_does_not_resurrect_history(setup):
    image, tasks, bridge, store, create = setup
    manager = create(Vision())
    job_id = manager.start({"path": str(image.parent), "mode": "natural"})["job_id"]
    manager._thread.join(timeout=5)
    written = image.with_suffix(".txt").read_bytes()
    assert tasks.delete_task(job_id)
    assert image.is_file()
    assert image.with_suffix(".txt").read_bytes() == written
    restored_tasks = TaskManager()
    CaptionTaskBridge(bridge.root, restored_tasks).restore(store)
    assert restored_tasks.dump() == []
    assert (bridge.locations[job_id] / "config.json").is_file()


def test_sqlite_recovery_preserves_all_new_generation_parameters(setup):
    image, _tasks, bridge, store, create = setup
    manager = create(Vision())
    job_id = manager.start({"path": str(image.parent), "mode": "natural", "system_prompt": "系统提示词", "max_tokens": 333, "temperature": .4, "model_id": "llm:fake", "runtime": "local", "preset_revision": "r1"})["job_id"]
    manager._thread.join(timeout=5)
    service = Vision()
    restored_tasks = TaskManager()
    restored = CaptionJobManager(service, job_store=store, task_bridge=CaptionTaskBridge(bridge.root, restored_tasks))
    assert restored._request["system_prompt"] == "系统提示词"
    assert restored._request["max_tokens"] == 333
    assert restored._request["temperature"] == .4
    assert restored._request["model_id"] == "llm:fake"
    assert restored_tasks.tasks[job_id].status == TaskStatus.FINISHED
    assert service.calls == []


def test_interrupted_archive_restores_failed_task_without_auto_inference_and_can_retry(setup):
    image, _tasks, bridge, store, _create = setup
    job_id = str(uuid.uuid4())
    state = {**CaptionJobManager._idle(), "job_id": job_id, "phase": "captioning", "mode": "natural", "total": 1}
    request = {"path": str(image.parent), "mode": "natural", "system_prompt": "冻结系统提示词", "max_tokens": 234, "temperature": .3, "expected_hashes": {str(image): None}}
    request["_task_archive"] = bridge.prepare(state, request, [str(image)], lambda: None)
    store.save(state, request, [str(image)], [], [])
    restored_tasks = TaskManager()
    service = Vision()
    restarted = CaptionJobManager(service, job_store=store, task_bridge=CaptionTaskBridge(bridge.root, restored_tasks))
    assert service.calls == []
    assert restarted.status()["recovered"] is True
    assert restored_tasks.tasks[job_id].status == TaskStatus.FAILED
    result = restarted.retry_failed(job_id)
    restarted._thread.join(timeout=5)
    assert result["parent_job_id"] == job_id
    assert service.calls[0]["system_prompt"] == "冻结系统提示词"
    assert service.calls[0]["max_tokens"] == 234
    assert service.calls[0]["temperature"] == .3
    assert restored_tasks.tasks[result["job_id"]].status == TaskStatus.FINISHED


def test_historical_retry_does_not_use_a_newer_tasks_configuration(setup):
    image, _tasks, _bridge, _store, create = setup

    class Flaky(Vision):
        async def complete_vision(self, *args, **kwargs):
            raise RuntimeError("failed")

    manager = create(Flaky())
    old = manager.start({"path": str(image.parent), "mode": "natural", "system_prompt": "旧系统提示词", "max_tokens": 222})["job_id"]
    manager._thread.join(timeout=5)
    newer_image = image.parent / "b.png"
    newer_image.write_bytes(b"second")
    service = Vision()
    manager.service = service
    manager.start({"path": str(image.parent), "paths": [str(newer_image)], "mode": "natural", "system_prompt": "新系统提示词", "max_tokens": 555})
    manager._thread.join(timeout=5)
    retried = manager.retry_failed(old)
    manager._thread.join(timeout=5)
    assert retried["parent_job_id"] == old
    assert manager.status()["total"] == 1
    assert service.calls[-1]["system_prompt"] == "旧系统提示词"
    assert service.calls[-1]["max_tokens"] == 222


def test_corrupt_task_record_recovers_valid_backup_and_sqlite_state(setup):
    image, _tasks, bridge, store, create = setup
    manager = create(Vision())
    job_id = manager.start({"path": str(image.parent), "mode": "natural"})["job_id"]
    manager._thread.join(timeout=5)
    path = bridge.locations[job_id] / "task.json"
    path.write_bytes(b"invalid json")
    restored_tasks = TaskManager()
    CaptionTaskBridge(bridge.root, restored_tasks).restore(store)
    assert restored_tasks.tasks[job_id].status == TaskStatus.FINISHED
    assert json.loads(path.read_text(encoding="utf-8"))["state"]["succeeded"] == 1


def test_old_task_cancel_does_not_cancel_newer_active_job(setup):
    image, tasks, _bridge, _store, create = setup
    manager = create(Vision())
    old_id = manager.start({"path": str(image.parent), "mode": "natural"})["job_id"]
    manager._thread.join(timeout=5)
    second = image.parent / "b.png"
    second.write_bytes(b"second-image")
    waiting = Vision(wait=True)
    manager.service = waiting
    new_id = manager.start({"path": str(image.parent), "paths": [str(second)], "mode": "natural"})["job_id"]
    assert waiting.started.wait(timeout=3)
    tasks.tasks[old_id]._on_cancel()
    assert manager.status()["job_id"] == new_id
    assert manager.is_busy()
    assert not waiting.aborted
    manager.cancel()
    manager._thread.join(timeout=5)


def test_sqlite_failure_after_archive_registration_prevents_inference(setup, monkeypatch):
    image, tasks, _bridge, store, create = setup
    service = Vision()
    manager = create(service)

    def fail(*args, **kwargs):
        raise OSError("database unavailable")

    monkeypatch.setattr(store, "save", fail)
    with pytest.raises(CaptionPersistenceError):
        manager.start({"path": str(image.parent), "mode": "natural"})
    assert not service.calls
    assert not image.with_suffix(".txt").exists()
    assert next(iter(tasks.tasks.values())).status == TaskStatus.FAILED
    assert not tagger_progress.is_busy()


def test_task_stop_cancels_tag_asset_download_before_inference(setup, monkeypatch):
    image, tasks, _bridge, _store, create = setup
    service = Vision()
    manager = create(service)
    downloading = threading.Event()
    tick = threading.Event()
    generated = []

    def prepare(request):
        downloading.set()
        while not tagger_progress.is_cancel_requested():
            tick.wait(.01)
        tagger_progress.check_cancelled()

    monkeypatch.setattr(manager, "_prepare_tag_model", prepare)
    monkeypatch.setattr(manager, "_generate_tags", lambda *args: generated.append(True))
    job_id = manager.start({"path": str(image.parent), "mode": "tag"})["job_id"]
    assert downloading.wait(timeout=3)
    tasks.terminate_task(job_id)
    manager._thread.join(timeout=5)
    assert not manager._thread.is_alive()
    assert manager.status()["phase"] == "cancelled"
    assert manager.status()["cancelled"] == 1
    assert manager.status()["failed"] == 0
    assert tasks.tasks[job_id].status == TaskStatus.TERMINATED
    assert not generated and not service.calls
    assert not image.with_suffix(".txt").exists()
    assert not tagger_progress.is_busy()


def test_malformed_archive_state_does_not_prevent_other_tasks_from_restoring(setup):
    image, _tasks, bridge, store, create = setup
    manager = create(Vision())
    job_id = manager.start({"path": str(image.parent), "mode": "natural"})["job_id"]
    manager._thread.join(timeout=5)
    valid = bridge.locations[job_id]
    malformed_id = str(uuid.uuid4())
    malformed = valid.with_name(valid.name.replace(job_id, malformed_id))
    malformed.mkdir()
    (malformed / "config.json").write_text("{}", encoding="utf-8")
    record = json.loads((valid / "task.json").read_text(encoding="utf-8"))
    record["job_id"] = malformed_id
    record["state"].update(job_id=malformed_id, phase=["done"])
    (malformed / "task.json").write_text(json.dumps(record), encoding="utf-8")
    restored = TaskManager()
    CaptionTaskBridge(bridge.root, restored).restore(store)
    assert list(restored.tasks) == [job_id]


def test_unavailable_archive_root_does_not_crash_state_restoration(setup, monkeypatch):
    _image, _tasks, bridge, store, _create = setup

    def unavailable(path):
        raise OSError("archive root unavailable")

    monkeypatch.setattr(bridge, "_contained", unavailable)
    bridge.restore(store)
    assert bridge.locations == {}
