from __future__ import annotations

import asyncio
import pytest
import time
from pathlib import Path

from mikazuki.tagger.caption_job import (
    CaptionJobManager,
    CaptionWriteConflict,
    caption_sha256,
    merge_caption,
    write_caption_atomic,
)
from mikazuki.llm.contracts import LLMProfile


def test_merge_caption_preserves_natural_language_separator():
    assert merge_caption("old sentence.", "new sentence.", "prepend") == (
        "new sentence.\n\nold sentence.",
        True,
    )
    assert merge_caption("old sentence.", "new sentence.", "append") == (
        "old sentence.\n\nnew sentence.",
        True,
    )


def test_ignore_does_not_change_existing_caption():
    assert merge_caption("old", "new", "ignore") == ("old", False)


def test_atomic_write_and_expected_hash_guard(tmp_path):
    target = tmp_path / "sample.txt"
    first = write_caption_atomic(target, "first")
    assert target.read_text(encoding="utf-8") == "first\n"
    assert first == caption_sha256(target)
    write_caption_atomic(target, "second", expected_sha256=first)
    with pytest.raises(CaptionWriteConflict):
        write_caption_atomic(target, "third", expected_sha256=first)


class FakeVisionService:
    async def complete_vision(self, image_path, prompt, **kwargs):
        profile = LLMProfile(
            id="fake-vision",
            name="Fake",
            endpoint="http://127.0.0.1:9999/v1/chat/completions",
            model="fake",
            source="local-endpoint",
            capabilities=("text", "vision"),
            languages=("zh-CN",),
        )
        return profile, {"choices": [{"finish_reason": "stop"}]}, '{"caption":"一只猫。","language":"zh-CN"}', {"bytes": 10}


def test_caption_job_manager_writes_caption_and_reports_status(tmp_path):
    image = tmp_path / "cat.png"
    image.write_bytes(b"fake")
    manager = CaptionJobManager(FakeVisionService())
    manager.start({
        "path": str(tmp_path),
        "mode": "natural",
        "language": "zh-CN",
        "prompt": "describe {{language}}",
        "conflict_action": "copy",
    })
    deadline = time.time() + 5
    while manager.status()["phase"] in {"pending", "captioning"} and time.time() < deadline:
        time.sleep(0.02)
    assert manager.status()["phase"] == "done"
    assert image.with_suffix(".txt").read_text(encoding="utf-8") == "一只猫。" + chr(10)


class MutatingVisionService(FakeVisionService):
    async def complete_vision(self, image_path, prompt, **kwargs):
        Path(image_path).with_suffix(".txt").write_text("user edit", encoding="utf-8")
        return await super().complete_vision(image_path, prompt, **kwargs)


def test_caption_job_detects_external_caption_change_before_atomic_write(tmp_path):
    image = tmp_path / "cat.png"
    image.write_bytes(b"fake")
    image.with_suffix(".txt").write_text("old", encoding="utf-8")
    manager = CaptionJobManager(MutatingVisionService())
    manager.start({
        "path": str(tmp_path),
        "mode": "natural",
        "language": "zh-CN",
        "prompt": "describe {{language}}",
        "conflict_action": "copy",
    })
    deadline = time.time() + 5
    while manager.status()["phase"] in {"pending", "captioning"} and time.time() < deadline:
        time.sleep(0.02)
    assert manager.status()["failed"] == 1
    assert manager.status()["errors"][0]["code"] == "caption_conflict"
    assert image.with_suffix(".txt").read_text(encoding="utf-8") == "user edit"


class SlowVisionService(FakeVisionService):
    async def complete_vision(self, image_path, prompt, **kwargs):
        await asyncio.sleep(0.25)
        return await super().complete_vision(image_path, prompt, **kwargs)


def test_caption_job_cancel_preserves_completed_items(tmp_path):
    first = tmp_path / "a.png"
    second = tmp_path / "b.png"
    first.write_bytes(b"fake")
    second.write_bytes(b"fake")
    manager = CaptionJobManager(SlowVisionService())
    manager.start({
        "path": str(tmp_path),
        "mode": "natural",
        "language": "zh-CN",
        "prompt": "describe {{language}}",
        "conflict_action": "copy",
    })
    deadline = time.time() + 5
    while manager.status()["current"] < 1 and time.time() < deadline:
        time.sleep(0.02)
    manager.cancel()
    while manager.status()["phase"] in {"pending", "captioning", "cancelling"} and time.time() < deadline:
        time.sleep(0.02)
    assert manager.status()["phase"] == "cancelled"
    assert first.with_suffix(".txt").is_file()
    assert not second.with_suffix(".txt").is_file()


def test_atomic_writer_rejects_new_external_file(tmp_path):
    target = tmp_path / "caption.txt"
    target.write_text("user created", encoding="utf-8")
    with pytest.raises(CaptionWriteConflict):
        write_caption_atomic(target, "model output", expected_sha256=None)
    assert target.read_text(encoding="utf-8") == "user created"


def test_ignore_creates_missing_caption_without_touching_existing(tmp_path):
    first = tmp_path / "a.png"
    second = tmp_path / "b.png"
    first.write_bytes(b"fake")
    second.write_bytes(b"fake")
    first.with_suffix(".txt").write_text("user caption", encoding="utf-8")
    manager = CaptionJobManager(FakeVisionService())
    manager.start({"path": str(tmp_path), "mode": "natural", "conflict_action": "ignore"})
    manager._thread.join(timeout=5)
    assert not manager._thread.is_alive()
    assert manager.status()["succeeded"] == 1
    assert manager.status()["skipped"] == 1
    assert first.with_suffix(".txt").read_text(encoding="utf-8") == "user caption"
    assert second.with_suffix(".txt").read_text(encoding="utf-8").strip() == "一只猫。"


def test_cancel_aborts_inflight_inference_and_prevents_write(tmp_path):
    import threading

    entered = threading.Event()
    aborted = threading.Event()

    class WaitingService:
        async def complete_vision(self, *args, **kwargs):
            entered.set()
            try:
                await asyncio.sleep(60)
            finally:
                aborted.set()

    (tmp_path / "a.png").write_bytes(b"fake")
    manager = CaptionJobManager(WaitingService())
    manager.start({"path": str(tmp_path), "mode": "natural"})
    assert entered.wait(timeout=5)
    started = time.monotonic()
    manager.cancel()
    manager._thread.join(timeout=2)
    assert not manager._thread.is_alive()
    assert aborted.is_set()
    assert time.monotonic() - started < 2
    assert manager.status()["phase"] == "cancelled"
    assert manager.status()["cancelled"] == 1
    assert not (tmp_path / "a.txt").exists()


def test_changed_source_image_during_inference_cannot_write_stale_caption(tmp_path):
    image = tmp_path / "a.png"
    image.write_bytes(b"original image")

    class ModifyingVision(FakeVisionService):
        async def complete_vision(self, image_path, prompt, **kwargs):
            image_path.write_bytes(b"new user image")
            return await super().complete_vision(image_path, prompt, **kwargs)

    manager = CaptionJobManager(ModifyingVision())
    manager.start({"path": str(tmp_path), "mode": "natural", "conflict_action": "copy"})
    manager._thread.join(timeout=5)
    assert not manager._thread.is_alive()
    assert manager.status()["failed"] == 1
    assert manager.status()["errors"][0]["code"] == "caption_conflict"
    assert not image.with_suffix(".txt").exists()
