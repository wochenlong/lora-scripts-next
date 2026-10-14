import json
import os
import subprocess
import sys
from pathlib import Path

from mikazuki.llm.contracts import LLMProfile
from mikazuki.tagger.caption_job import CaptionJobManager, caption_sha256
from mikazuki.tagger.caption_store import CaptionJobStore
from mikazuki.tagger.progress import tagger_progress


class Vision:
    def __init__(self, fail=None):
        self.fail = fail
        self.calls = []

    async def complete_vision(self, image_path, prompt, **kwargs):
        self.calls.append(image_path.name)
        if image_path.name == self.fail:
            raise RuntimeError("fake failure")
        return LLMProfile(id="fake", name="fake", endpoint="http://localhost:8080/v1/chat/completions",
                          model="fake", source="local-endpoint", capabilities=("text", "vision")), \
            {"choices": [{"finish_reason": "stop"}]}, '{"caption":"一只猫。","language":"zh-CN"}', {}


def wait(manager):
    manager._thread.join(timeout=5)
    assert not manager._thread.is_alive()


def test_partial_failure_survives_restart_and_retries_only_failed_image(tmp_path):
    images = tmp_path / "images"
    images.mkdir()
    for name in ["a", "b"]:
        (images / (name + ".png")).write_bytes(b"fake")
    store = CaptionJobStore(tmp_path / "translations.sqlite3")
    first = CaptionJobManager(Vision(fail="b.png"), job_store=store)
    first.start({"path": str(images), "mode": "natural", "language": "zh-CN"})
    wait(first)
    first_id = first.status()["job_id"]
    before = (images / "a.txt").read_bytes()
    service = Vision()
    restarted = CaptionJobManager(service, job_store=CaptionJobStore(store.path))
    assert restarted.status()["failed"] == 1
    restarted.retry_failed()
    wait(restarted)
    assert service.calls == ["b.png"]
    assert restarted.status()["parent_job_id"] == first_id
    assert restarted.status()["succeeded"] == 1
    assert (images / "a.txt").read_bytes() == before
    assert restarted.detail(first_id)["failed"] == 1
    assert len(restarted.history()) == 2
    assert str(tmp_path) not in json.dumps(restarted.detail(first_id))


def test_retry_after_restart_preserves_external_caption_edit(tmp_path):
    image = tmp_path / "b.png"
    image.write_bytes(b"fake")
    store = CaptionJobStore(tmp_path / "translations.sqlite3")
    first = CaptionJobManager(Vision(fail="b.png"), job_store=store)
    first.start({"path": str(tmp_path), "mode": "natural", "language": "zh-CN"})
    wait(first)
    image.with_suffix(".txt").write_text("user updated caption", encoding="utf-8")
    service = Vision()
    restarted = CaptionJobManager(service, job_store=store)
    restarted.retry_failed()
    wait(restarted)
    assert service.calls == []
    assert restarted.status()["errors"][0]["code"] == "caption_conflict"
    assert image.with_suffix(".txt").read_text() == "user updated caption"


def test_restart_marks_pending_items_retryable_without_automatic_calls(tmp_path):
    image = tmp_path / "a.png"
    image.write_bytes(b"fake")
    store = CaptionJobStore(tmp_path / "translations.sqlite3")
    state = {**CaptionJobManager._idle(), "job_id": "interrupted", "phase": "captioning", "total": 1}
    store.save(state, {"path": str(tmp_path), "mode": "natural", "language": "zh-CN", "expected_hashes": {str(image): None}}, [str(image)], [], [])
    service = Vision()
    restarted = CaptionJobManager(service, job_store=store)
    assert service.calls == []
    assert not restarted.is_busy()
    assert restarted.status()["recovered"] is True
    assert restarted.status()["failed"] == 1
    assert restarted.status()["report"]["items"][0]["code"] == "caption_interrupted"
    assert store.get("interrupted")["state"]["report"]["items"][0]["code"] == "caption_interrupted"
    restarted.retry_failed()
    wait(restarted)
    assert service.calls == ["a.png"]
    assert restarted.status()["succeeded"] == 1


def test_crash_after_atomic_overwrite_recovers_completion_without_reinference(tmp_path):
    images = tmp_path / "images"
    images.mkdir()
    image = images / "a.png"
    image.write_bytes(b"fake")
    image.with_suffix(".txt").write_bytes(b"original\r\ncaption")
    database = tmp_path / "translations.sqlite3"
    script = r'''
import os, sys, asyncio
from pathlib import Path
from mikazuki.llm.contracts import LLMProfile
from mikazuki.tagger.caption_store import CaptionJobStore
from mikazuki.tagger import caption_job
class Vision:
    async def complete_vision(self, *args, **kwargs):
        return LLMProfile(id="fake", name="fake", endpoint="http://localhost:8080/v1/chat/completions", model="fake", source="local-endpoint", capabilities=("text", "vision")), {"choices":[{"finish_reason":"stop"}]}, '{"caption":"一只猫。","language":"zh-CN"}', {}
original = caption_job.write_caption_atomic
def interrupted_write(*args, **kwargs):
    original(*args, **kwargs)
    os._exit(91)
caption_job.write_caption_atomic = interrupted_write
manager = caption_job.CaptionJobManager(Vision(), job_store=CaptionJobStore(sys.argv[2]))
manager.start({"path":sys.argv[1], "mode":"natural", "language":"zh-CN", "conflict_action":"copy"})
manager._thread.join()
'''
    result = subprocess.run([sys.executable, "-c", script, str(images), str(database)],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, timeout=30,
                            env={**os.environ, "MIKAZUKI_TAG_TRANSLATION_ROOT": str(tmp_path / "runtime")})
    assert result.returncode == 91
    written = image.with_suffix(".txt").read_bytes()
    assert written.decode("utf-8").strip() == "一只猫。"
    service = Vision()
    restarted = CaptionJobManager(service, job_store=CaptionJobStore(database))
    assert restarted.status()["succeeded"] == 1
    assert restarted.status()["failed"] == 0
    assert restarted.status()["phase"] == "done"
    assert restarted.status()["report"]["items"][0]["recovered_write"] is True
    assert service.calls == []
    assert image.with_suffix(".txt").read_bytes() == written


def test_store_never_persists_request_credentials_or_provider_envelope(tmp_path):
    store = CaptionJobStore(tmp_path / "translations.sqlite3")
    state = {**CaptionJobManager._idle(), "job_id": "safe"}
    store.save(state, {"mode": "natural", "language": "zh-CN", "api_key": "fixture-private-key", "config_snapshot": {"api_key": "fixture-private-key"}}, [], [], [])
    assert "fixture-private-key" not in store.path.read_bytes().decode("latin1")
    assert "api_key" not in json.dumps(store.get())


def test_persistence_failure_prevents_inference_and_releases_shared_reservation(tmp_path, monkeypatch):
    import sqlite3
    image = tmp_path / "a.png"
    image.write_bytes(b"fake")
    store = CaptionJobStore(tmp_path / "translations.sqlite3")
    original = store.save
    calls = 0

    def fail_after_submission(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise sqlite3.OperationalError("private disk path")
        return original(*args, **kwargs)

    monkeypatch.setattr(store, "save", fail_after_submission)
    service = Vision()
    manager = CaptionJobManager(service, job_store=store)
    manager.start({"path": str(tmp_path), "mode": "natural", "language": "zh-CN"})
    wait(manager)
    assert manager.status()["phase"] == "error"
    assert "private disk path" not in json.dumps(manager.status())
    assert service.calls == []
    assert not tagger_progress.is_busy()
    assert not image.with_suffix(".txt").exists()


def test_retry_uses_frozen_prompt_after_preset_is_deleted(tmp_path):
    image = tmp_path / "a.png"
    image.write_bytes(b"fake")
    store = CaptionJobStore(tmp_path / "translations.sqlite3")

    class PresetVision(Vision):
        presets = [{"id": "frozen", "name": "Frozen", "template": "Original {{language}} {{image_name}}", "language": "zh-CN"}]

        def config(self, **kwargs):
            return {"prompt_presets": self.presets}

        async def complete_vision(self, image_path, prompt, **kwargs):
            assert prompt == "Original zh-CN image"
            return await super().complete_vision(image_path, prompt, **kwargs)

    service = PresetVision(fail="a.png")
    first = CaptionJobManager(service, job_store=store)
    first.start({"path": str(tmp_path), "mode": "natural", "language": "zh-CN", "prompt_id": "frozen"})
    wait(first)
    assert first.status()["snapshot"]["prompt_id"] == "frozen"
    service.presets = []
    service.fail = None
    restarted = CaptionJobManager(service, job_store=store)
    restarted.retry_failed()
    wait(restarted)
    assert restarted.status()["succeeded"] == 1


def test_restart_can_retry_task_level_error_before_first_image(tmp_path):
    image = tmp_path / "a.png"
    image.write_bytes(b"fake")
    store = CaptionJobStore(tmp_path / "translations.sqlite3")
    state = {**CaptionJobManager._idle(), "job_id": "failed-before-image", "phase": "error", "total": 1}
    store.save(state, {"path": str(tmp_path), "mode": "natural", "language": "zh-CN", "expected_hashes": {str(image): None}}, [str(image)], [], [])
    service = Vision()
    restarted = CaptionJobManager(service, job_store=store)
    assert restarted.status()["failed"] == 1
    restarted.retry_failed()
    wait(restarted)
    assert service.calls == ["a.png"]
    assert restarted.status()["succeeded"] == 1


def test_short_natural_caption_provenance_blocks_tag_cleanup(tmp_path, monkeypatch):
    image = tmp_path / "a.png"
    image.write_bytes(b"fake")
    store = CaptionJobStore(tmp_path / "translations.sqlite3")

    class ShortVision(Vision):
        async def complete_vision(self, *args, **kwargs):
            profile, envelope, _content, info = await super().complete_vision(*args, **kwargs)
            return profile, envelope, '{"caption":"一只猫","language":"zh-CN"}', info

    natural = CaptionJobManager(ShortVision(), job_store=store)
    natural.start({"path": str(tmp_path), "mode": "natural", "language": "zh-CN"})
    wait(natural)
    target = image.with_suffix(".txt")
    before = target.read_bytes()
    assert store.find_format(target, caption_sha256(target)) == "natural"
    tag = CaptionJobManager(Vision(), job_store=store)
    monkeypatch.setattr(tag, "_prepare_tag_model", lambda request: None)
    monkeypatch.setattr(tag, "_generate_tags", lambda path, request: ["cat"])
    tag.start({"path": str(tmp_path), "mode": "tag", "conflict_action": "append"})
    wait(tag)
    assert tag.status()["failed"] == 1
    assert target.read_bytes() == before
