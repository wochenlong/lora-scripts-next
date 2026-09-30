from __future__ import annotations

import asyncio

from mikazuki.tag_translation import api


def test_dictionary_precedence_and_no_caption_mutation(monkeypatch):
    caption = "blue_eyes, unknown_tag"

    async def ready(_locale):
        return {}

    async def wait():
        return {}

    async def network(tags, _locale):
        assert tags == ["unknown_tag"]
        return {"unknown_tag": "网络译文"}

    async def llm(_locale, items):
        assert items == []
        return {}

    monkeypatch.setattr(api.dictionary_service, "ensure", ready)
    monkeypatch.setattr(api.dictionary_service, "wait_for_update", wait)
    monkeypatch.setattr(api.dictionary_service, "lookup", lambda tags: {"blue_eyes": {"text": "蓝瞳", "category": 0, "post_count": 1}})
    monkeypatch.setattr(api.translation_store, "get_results", lambda *args: {})
    monkeypatch.setattr(api, "translate_mymemory", network)
    monkeypatch.setattr(api.translation_manager, "resolve", llm)

    result = asyncio.run(api.resolve_tag_translations(api.TagTranslationRequest(tags=caption.split(", "), provider="auto")))

    assert result["data"]["items"][0]["translation"] == "蓝瞳"
    assert result["data"]["items"][0]["source"] == "danbooru"
    assert result["data"]["items"][1]["source"] == "mymemory"
    assert caption == "blue_eyes, unknown_tag"


def test_dictionary_only_never_calls_external_provider(monkeypatch):
    async def ready(_locale):
        return {}

    async def wait():
        return {}

    async def forbidden(*_args):
        raise AssertionError("external provider must not run")

    monkeypatch.setattr(api.dictionary_service, "ensure", ready)
    monkeypatch.setattr(api.dictionary_service, "wait_for_update", wait)
    monkeypatch.setattr(api.dictionary_service, "lookup", lambda tags: {})
    monkeypatch.setattr(api, "translate_mymemory", forbidden)
    monkeypatch.setattr(api.translation_manager, "resolve", forbidden)

    result = asyncio.run(api.resolve_tag_translations(api.TagTranslationRequest(tags=["missing"], provider="danbooru")))

    assert result["data"]["items"] == [{"tag": "missing", "translation": None, "source": None, "status": "missing", "cached": False, "error_code": None, "category": None, "post_count": None}]


def test_mymemory_cache_avoids_second_network_request(monkeypatch):
    async def ready(_locale):
        return {}

    async def wait():
        return {}

    monkeypatch.setattr(api.dictionary_service, "ensure", ready)
    monkeypatch.setattr(api.dictionary_service, "wait_for_update", wait)
    monkeypatch.setattr(api.dictionary_service, "lookup", lambda tags: {})
    monkeypatch.setattr(api.translation_store, "get_results", lambda *args: {"unknown": {"text": "缓存译文"}})
    monkeypatch.setattr(api, "translate_mymemory", lambda *_args: (_ for _ in ()).throw(AssertionError("network must not run")))

    result = asyncio.run(api.resolve_tag_translations(api.TagTranslationRequest(tags=["unknown"], provider="mymemory")))

    assert result["data"]["items"][0]["translation"] == "缓存译文"
    assert result["data"]["items"][0]["cached"] is True


def test_llm_rows_are_adapted_to_public_strings(monkeypatch):
    async def ready(_locale):
        return {}

    async def wait():
        return {}

    async def resolve(_locale, _items):
        return {"unknown": {"text": "模型译文", "origin": "ai_cache"}}

    monkeypatch.setattr(api.dictionary_service, "ensure", ready)
    monkeypatch.setattr(api.dictionary_service, "wait_for_update", wait)
    monkeypatch.setattr(api.dictionary_service, "lookup", lambda tags: {})
    monkeypatch.setattr(api.translation_store, "get_results", lambda *args: {})
    monkeypatch.setattr(api.translation_manager, "resolve", resolve)

    result = asyncio.run(api.resolve_tag_translations(api.TagTranslationRequest(tags=["unknown"], provider="llm")))

    assert result["data"]["items"][0]["translation"] == "模型译文"
    assert isinstance(result["data"]["items"][0]["translation"], str)
