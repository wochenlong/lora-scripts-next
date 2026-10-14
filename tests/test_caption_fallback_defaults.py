"""Contract checks for the hidden, shared local-fallback default."""
from __future__ import annotations

import asyncio
import json

from PIL import Image

from mikazuki.llm import api as llm_api
from mikazuki.llm.cache import CaptionCache
from mikazuki.llm.config import UnifiedConfigStore, config_revision
from mikazuki.llm.http import LLMRequestError
from mikazuki.llm.service import UnifiedLLMService
from mikazuki.tagger import caption_api
from mikazuki.tagger.caption_job import CaptionJobManager


class _SharedConfig:
    def __init__(self, enabled: bool):
        self.enabled = enabled

    def config(self, *, masked: bool = False):
        assert masked is False
        return {"local_fallback_enabled": self.enabled}


def test_caption_job_omitted_fallback_freezes_shared_default(monkeypatch):
    monkeypatch.setattr(caption_api, "llm_service", _SharedConfig(True))
    request = caption_api.CaptionJobRequest(path="C:/dataset")
    frozen = caption_api._snapshot_request(request)
    assert frozen["allow_local_fallback"] is True

    explicit = caption_api.CaptionJobRequest(path="C:/dataset", allow_local_fallback=False)
    assert caption_api._snapshot_request(explicit)["allow_local_fallback"] is False

    monkeypatch.setattr(caption_api, "llm_service", _SharedConfig(False))
    disabled_by_config = caption_api.CaptionJobRequest(path="C:/dataset")
    assert caption_api._snapshot_request(disabled_by_config)["allow_local_fallback"] is False


def test_caption_translation_omitted_fallback_uses_shared_default(monkeypatch):
    captured = {}

    class FakeTranslator:
        def __init__(self, *_args):
            pass

        async def translate(self, **kwargs):
            captured.update(kwargs)
            return {"translation": "一只猫。", "skipped": False, "cached": False}

    monkeypatch.setattr(llm_api, "llm_service", _SharedConfig(True))
    monkeypatch.setattr(llm_api, "caption_cache", object())
    monkeypatch.setattr("mikazuki.llm.caption_translation.CaptionTextTranslator", FakeTranslator)

    class Request:
        async def is_disconnected(self):
            return False

    asyncio.run(llm_api.translate_caption_text(llm_api.CaptionTranslationRequest(text="A cat."), Request()))
    assert captured["allow_local_fallback"] is True

    captured.clear()
    explicit = llm_api.CaptionTranslationRequest(text="A cat.", allow_local_fallback=False)
    asyncio.run(llm_api.translate_caption_text(explicit, Request()))
    assert captured["allow_local_fallback"] is False


def test_caption_fallback_replays_local_cache_before_retrying_local_provider(tmp_path, monkeypatch):
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    Image.new("RGB", (16, 16), "white").save(image_dir / "cat.png")
    store = UnifiedConfigStore(tmp_path / "config.json")
    store.save({"profiles": [
        {"id": "remote", "name": "Remote", "endpoint": "https://remote.example/v1/chat/completions", "model": "remote", "source": "remote", "api_key": "fixture", "capabilities": ["vision"], "languages": ["en"]},
        {"id": "local", "name": "Local", "endpoint": "http://127.0.0.1:9999/v1/chat/completions", "model": "local", "source": "local-endpoint", "capabilities": ["vision"], "languages": ["en"]},
    ], "local_fallback_enabled": True, "routes": {"caption": "remote"}})
    for profile in store.load()["profiles"]:
        store.record_verification(profile["id"], config_revision(profile), "vision")
    service = UnifiedLLMService(store)
    cache = CaptionCache(tmp_path / "cache.sqlite3")
    calls = []

    async def request(profile, _payload, **_options):
        calls.append(profile.id)
        if profile.id == "remote":
            raise LLMRequestError("offline", "llm_unreachable")
        return {"choices": [{"finish_reason": "stop"}]}, json.dumps({"caption": "A cached cat.", "language": "en"})

    monkeypatch.setattr("mikazuki.llm.service.chat_completion", request)
    manager = CaptionJobManager(service, cache=cache)
    request_payload = {"path": str(image_dir), "language": "en", "allow_local_fallback": True, "conflict_action": "ignore"}
    manager.start(request_payload)
    manager._thread.join(timeout=5)
    assert manager.status()["succeeded"] == 1
    assert manager.status()["report"]["items"][0]["source"] == "local-endpoint"
    assert manager.status()["report"]["items"][0]["cached"] is False
    (image_dir / "cat.txt").unlink()

    manager.start(request_payload)
    manager._thread.join(timeout=5)
    assert manager.status()["succeeded"] == 1
    assert manager.status()["report"]["items"][0]["cached"] is True
    assert calls == ["remote", "local", "remote"]

    # A cached local result from an allowed fallback must not bypass an
    # explicit remote-only policy, even when the shared default is enabled.
    original_bytes = (image_dir / "cat.txt").read_bytes()
    manager.start({**request_payload, "allow_local_fallback": False, "conflict_action": "copy"})
    manager._thread.join(timeout=5)
    status = manager.status()
    assert status["snapshot"]["allow_local_fallback"] is False
    assert status["succeeded"] == 0
    assert status["failed"] == 1
    assert (image_dir / "cat.txt").read_bytes() == original_bytes
    assert calls == ["remote", "local", "remote", "remote"]
