from __future__ import annotations

import pytest
import time

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
