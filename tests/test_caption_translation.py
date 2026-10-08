import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mikazuki.llm import api
from mikazuki.llm.cache import CaptionCache
from mikazuki.llm.caption_translation import CaptionTextTranslator, is_chinese_text
from mikazuki.llm.contracts import LLMContractError, LLMProfile, LLMRouteError


class Service:
    def __init__(self):
        self.profile = LLMProfile(id="text", name="Text", endpoint="https://example.test/v1/chat/completions", model="text-model", source="remote", capabilities=("text",), languages=("zh-CN",))
        self.calls = []
        self.content = '{"translation":"一只猫坐在窗边。","language":"zh-CN"}'
        self.reason = "stop"

    def config(self, **_):
        return {"cache": {"translation": True}}

    def resolve(self, capability, **options):
        assert capability == "text"
        return self.profile

    async def complete_text(self, prompt, **options):
        self.calls.append((prompt, options))
        return self.profile, {"choices": [{"finish_reason": self.reason}]}, self.content


@pytest.mark.parametrize("text,expected", [("一只猫。", True), ("一只猫坐在 Qwen 标牌前。", True), ("A cat next to a sign reading 猫.", False), ("猫が窓のそばに座る。", False), ("A cat by a window.", False)])
def test_chinese_detection(text, expected):
    assert is_chinese_text(text) is expected


def test_chinese_needs_no_profile_or_model(tmp_path):
    class Unconfigured(Service):
        def resolve(self, *args, **kwargs):
            raise AssertionError("Chinese must never resolve a profile")
    result = asyncio.run(CaptionTextTranslator(Unconfigured(), CaptionCache(tmp_path / "cache.db")).translate("一只猫。"))
    assert result["skipped"] and result["translation"] == "一只猫。"


def test_whole_text_translation_cache_and_revision(tmp_path):
    service = Service()
    cache = CaptionCache(tmp_path / "cache.db")
    translator = CaptionTextTranslator(service, cache)
    source = "A cat, looking through a window."
    first = asyncio.run(translator.translate(source))
    second = asyncio.run(translator.translate(source))
    assert first["translation"] == "一只猫坐在窗边。" and not first["cached"]
    assert second["cached"] and len(service.calls) == 1
    assert source in service.calls[0][0]
    assert service.calls[0][1]["allow_local_fallback"] is False
    assert cache.count() == 0 and cache.translation_count() == 1
    service.profile = LLMProfile(**{**service.profile.__dict__, "model": "changed-model"})
    asyncio.run(translator.translate(source, allow_local_fallback=True))
    assert len(service.calls) == 2 and service.calls[1][1]["allow_local_fallback"] is True
    cache.clear_translations()
    assert cache.translation_count() == 0


@pytest.mark.parametrize("content", ['{"translation":"English","language":"zh-CN"}', '{"translation":"中文","language":"en"}', '{"translation":"中文","language":"zh-CN","extra":1}', 'not JSON'])
def test_invalid_response_is_not_cached(tmp_path, content):
    service = Service()
    service.content = content
    cache = CaptionCache(tmp_path / "cache.db")
    with pytest.raises(LLMContractError):
        asyncio.run(CaptionTextTranslator(service, cache).translate("A cat."))
    assert cache.translation_count() == 0


def test_http_bounded_input_and_sanitized_errors(tmp_path, monkeypatch):
    service = Service()
    monkeypatch.setattr(api, "llm_service", service)
    monkeypatch.setattr(api, "caption_cache", CaptionCache(tmp_path / "cache.db"))
    app = FastAPI()
    app.include_router(api.router, prefix="/api")
    client = TestClient(app)
    result = client.post("/api/llm/caption-translation", json={"text": "A cat."})
    assert result.status_code == 200 and result.json()["data"]["translation"] == "一只猫坐在窗边。"
    for body in ({"text": "x" * 2001}, {"text": "A cat.", "image_path": "private-path"}):
        assert client.post("/api/llm/caption-translation", json=body).status_code == 422
    def fail(*_, **__):
        raise LLMRouteError("private-connection-detail")
    monkeypatch.setattr(service, "resolve", fail)
    response = client.post("/api/llm/caption-translation", json={"text": "Another image."})
    assert response.status_code == 409 and "private-connection-detail" not in response.text
    assert client.post("/api/llm/caption-translation", json={"text": "中文无需翻译"}).json()["data"]["skipped"]


def test_truncated_translation_not_cached(tmp_path):
    service = Service()
    service.reason = "length"
    cache = CaptionCache(tmp_path / "cache.db")
    with pytest.raises(LLMContractError, match="truncated"):
        asyncio.run(CaptionTextTranslator(service, cache).translate("A cat."))
    assert cache.translation_count() == 0


def test_unconfigured_remote_is_not_contacted_and_local_cache_replays(tmp_path, monkeypatch):
    from mikazuki.llm.config import UnifiedConfigStore
    from mikazuki.llm.service import UnifiedLLMService
    store = UnifiedConfigStore(tmp_path / "config.json")
    store.save({"profiles": [
        {"id": "empty", "endpoint": "https://unconfigured.test/v1/chat/completions", "model": "remote", "source": "remote", "capabilities": ["text"], "languages": ["zh-CN"]},
        {"id": "local", "endpoint": "http://127.0.0.1:9999/v1/chat/completions", "model": "local", "source": "local-endpoint", "capabilities": ["text"], "languages": ["zh-CN"]},
    ]})
    calls = []
    async def complete(service, prompt, **options):
        profile = service.resolve("text", language=options["language"], allow_local_fallback=options["allow_local_fallback"])
        calls.append(profile.id)
        return profile, {"choices": [{"finish_reason": "stop"}]}, '{"translation":"一只猫。","language":"zh-CN"}'
    monkeypatch.setattr(UnifiedLLMService, "complete_text", complete)
    translator = CaptionTextTranslator(UnifiedLLMService(store), CaptionCache(tmp_path / "cache.db"))
    with pytest.raises(LLMRouteError):
        asyncio.run(translator.translate("A cat."))
    asyncio.run(translator.translate("A cat.", allow_local_fallback=True))
    assert asyncio.run(translator.translate("A cat.", allow_local_fallback=True))["cached"]
    assert calls == ["local"]
    assert store.load()["profiles"][0]["ready"] is True


def test_disconnected_translation_cancels_provider_without_caching(tmp_path, monkeypatch):
    cancelled = []
    class Slow(Service):
        async def complete_text(self, *_args, **_kwargs):
            try:
                await asyncio.sleep(20)
            except asyncio.CancelledError:
                cancelled.append(True)
                raise
    class Request:
        calls = 0
        async def is_disconnected(self):
            self.calls += 1
            return self.calls > 2
    cache = CaptionCache(tmp_path / "cache.db")
    monkeypatch.setattr(api, "llm_service", Slow())
    monkeypatch.setattr(api, "caption_cache", cache)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as raised:
        asyncio.run(api.translate_caption_text(api.CaptionTranslationRequest(text="A cat."), Request()))
    assert raised.value.status_code == 499 and cancelled == [True]
    assert cache.translation_count() == 0
