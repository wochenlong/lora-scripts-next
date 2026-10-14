"""Translation review regressions use isolated storage and synthetic providers."""
import asyncio
import json

import pytest

from mikazuki.llm.cache import CaptionCache
from mikazuki.llm.caption_translation import CaptionTextTranslator
from mikazuki.llm.config import UnifiedConfigStore, config_revision
from mikazuki.llm.http import LLMRequestError
from mikazuki.llm.service import UnifiedLLMService
from mikazuki.tag_translation import api
from mikazuki.tag_translation.translation_config import OnlineServiceConfig
from mikazuki.tag_translation.translation_service import DeepSeekClient, TranslationManager
from mikazuki.tag_translation.translation_store import TranslationStore


def _tag_manager(tmp_path, monkeypatch):
    path = tmp_path / "translation.json"
    legacy = OnlineServiceConfig(path)
    legacy.save({})
    shared = UnifiedConfigStore(path)
    shared.save({"profiles": [
        {"id": identifier, "source": "remote", "model": "same-model", "api_key": "fixture-key",
         "endpoint": f"https://{identifier}.example.test/v1/chat/completions",
         "capabilities": ["text"], "languages": ["zh-CN"]}
        for identifier in ("first", "second")
    ], "routes": {"translation": "first"}, "local_fallback_enabled": False})
    for profile in shared.load()["profiles"]:
        shared.record_verification(profile["id"], config_revision(profile), "text")
    store = TranslationStore(str(tmp_path / "cache.sqlite3"))
    manager = TranslationManager(path, store)
    assert manager._active_llm_config(legacy.load())["max_retries"] == 3

    async def no_retry_delay(*_args, **_kwargs):
        pass

    monkeypatch.setattr(DeepSeekClient, "_retry_delay", no_retry_delay)
    return shared, store, manager


def _tags_content(value):
    return {"choices": [{"finish_reason": "stop"}]}, json.dumps({
        "translations": [] if value is None else [{"tag": "cat", "translation": value}],
    })


@pytest.mark.parametrize("change", ["route", "endpoint", "key"])
def test_failure_cache_changes_with_shared_profile_identity(tmp_path, monkeypatch, change):
    shared, store, manager = _tag_manager(tmp_path, monkeypatch)
    calls = []
    succeed = False

    async def request(_self, profile, _payload):
        calls.append(profile.id)
        return _tags_content("猫" if succeed else None)

    monkeypatch.setattr(UnifiedLLMService, "_request", request)

    async def verify():
        nonlocal succeed
        item = {"name": "cat", "category": 0}
        assert await manager.resolve("zh-CN", [item]) == {}
        assert calls == ["first"] * 4  # Default retry budget, not a zero-retry fixture.
        assert await manager.resolve("zh-CN", [item]) == {}
        assert len(calls) == 4
        previous_revision = manager.profile_revision()
        if change == "route":
            shared.save({"routes": {"translation": "second"}})
        else:
            config = shared.load()
            profile = next(p for p in config["profiles"] if p["id"] == "first")
            profile["endpoint" if change == "endpoint" else "api_key"] = (
                "https://changed.example.test/v1/chat/completions" if change == "endpoint" else "changed-fixture-key"
            )
            shared.save({"profiles": config["profiles"]})
            profile = next(p for p in shared.load()["profiles"] if p["id"] == "first")
            shared.record_verification("first", config_revision(profile), "text")
        assert manager.profile_revision() != previous_revision
        succeed = True
        result = await manager.resolve("zh-CN", [item])
        assert result["cat"]["text"] == "猫"
        assert len(calls) == 5
        assert not store.get_failures("zh", ["cat"], profile_revision=manager.profile_revision())

    asyncio.run(verify())


def test_clear_handler_removes_failure_cache_and_retries(tmp_path, monkeypatch):
    _shared, store, manager = _tag_manager(tmp_path, monkeypatch)
    calls = []
    succeed = False

    async def request(_self, _profile, _payload):
        calls.append(True)
        return _tags_content("猫" if succeed else None)

    monkeypatch.setattr(UnifiedLLMService, "_request", request)
    monkeypatch.setattr(api, "translation_store", store)
    # Isolate the other half of the shared clear endpoint as well.
    from mikazuki.llm import runtime
    monkeypatch.setattr(runtime, "caption_cache", CaptionCache(tmp_path / "caption.sqlite3"))

    async def verify():
        nonlocal succeed
        item = {"name": "cat", "category": 0}
        assert await manager.resolve("zh-CN", [item]) == {}
        revision = manager.profile_revision()
        assert store.get_failures("zh", ["cat"], profile_revision=revision) == {"cat"}
        result = await api.clear_tag_translation_cache()
        assert result["data"]["total"] == 0
        assert not store.get_failures("zh", ["cat"], profile_revision=revision)
        succeed = True
        assert (await manager.resolve("zh-CN", [item]))["cat"]["text"] == "猫"
        assert len(calls) == 5

    asyncio.run(verify())


@pytest.mark.parametrize("late_value", [None, "旧译文"])
def test_clear_detaches_new_requests_and_blocks_late_cache_writes(tmp_path, monkeypatch, late_value):
    _shared, store, manager = _tag_manager(tmp_path, monkeypatch)

    async def verify():
        started = asyncio.Event()
        release = asyncio.Event()
        calls = 0

        async def request(_self, _profile, _payload):
            nonlocal calls
            calls += 1
            if calls == 1:
                started.set()
                await release.wait()
                return _tags_content(late_value)
            # First old request retries remain invalid; a distinct new request
            # is identified by its task name, independent of completion order.
            if asyncio.current_task().get_name() == "old-provider":
                return _tags_content(late_value)
            return _tags_content("新译文")

        # Keep the old retry tasks identifiable without changing production.
        original_translate = DeepSeekClient.translate

        async def named_translate(client, items, locale):
            asyncio.current_task().set_name("old-provider" if not started.is_set() else "new-provider")
            return await original_translate(client, items, locale)

        monkeypatch.setattr(DeepSeekClient, "translate", named_translate)
        monkeypatch.setattr(UnifiedLLMService, "_request", request)
        item = {"name": "cat", "category": 0}
        old = asyncio.create_task(manager.resolve("zh-CN", [item]))
        await started.wait()
        old_generation = store.cache_generation("llm")
        store.clear_results("llm")
        assert store.cache_generation("llm") == old_generation + 1
        fresh = await asyncio.wait_for(manager.resolve("zh-CN", [item]), timeout=2)
        assert fresh["cat"]["text"] == "新译文"
        release.set()
        await old
        revision = manager.profile_revision()
        assert store.get_results("zh", ["cat"], "llm", revision)["cat"]["text"] == "新译文"
        assert not store.get_failures("zh", ["cat"], profile_revision=revision)

    asyncio.run(verify())


def test_refresh_failure_returns_no_old_success_and_bypasses_normal_inflight(tmp_path, monkeypatch):
    _shared, store, manager = _tag_manager(tmp_path, monkeypatch)

    async def verify():
        started, release = asyncio.Event(), asyncio.Event()
        calls = 0

        async def request(_self, _profile, _payload):
            nonlocal calls
            calls += 1
            if calls == 1:
                started.set()
                await release.wait()
                return _tags_content("普通请求译文")
            return _tags_content(None)

        monkeypatch.setattr(UnifiedLLMService, "_request", request)
        item = {"name": "cat", "category": 0}
        normal = asyncio.create_task(manager.resolve("zh-CN", [item]))
        await started.wait()
        revision = manager.profile_revision()
        store.save_results("zh", "llm", revision, [item], {"cat": "旧缓存译文"})
        refreshed = await asyncio.wait_for(manager.resolve("zh-CN", [item], refresh=True), timeout=2)
        assert refreshed == {}
        assert calls == 5
        assert store.get_results("zh", ["cat"], "llm", revision)["cat"]["text"] == "旧缓存译文"
        release.set()
        assert (await normal)["cat"]["text"] == "普通请求译文"

    asyncio.run(verify())


def _caption_translator(tmp_path):
    shared = UnifiedConfigStore(tmp_path / "config.json")
    shared.save({"profiles": [
        {"id": "remote", "source": "remote", "model": "remote", "api_key": "fixture-key",
         "endpoint": "https://remote.example.test/v1/chat/completions",
         "capabilities": ["text"], "languages": ["zh-CN"]},
        {"id": "local", "source": "local-endpoint", "model": "local",
         "endpoint": "http://127.0.0.1:9/v1/chat/completions",
         "capabilities": ["text"], "languages": ["zh-CN"]},
    ], "local_fallback_enabled": True})
    for profile in shared.load()["profiles"]:
        shared.record_verification(profile["id"], config_revision(profile), "text")
    cache = CaptionCache(tmp_path / "cache.sqlite3")
    return shared, cache, CaptionTextTranslator(UnifiedLLMService(shared), cache)


def test_fallback_caption_cache_is_used_after_remote_failure_and_remote_still_wins(tmp_path, monkeypatch):
    _shared, cache, translator = _caption_translator(tmp_path)
    calls = []
    remote_ready = False

    async def request(_self, profile, _payload):
        calls.append(profile.id)
        if profile.id == "remote" and not remote_ready:
            raise LLMRequestError("fixture offline", "llm_unreachable")
        return {"choices": [{"finish_reason": "stop"}]}, json.dumps({
            "translation": "远程译文" if profile.id == "remote" else "本地译文", "language": "zh-CN",
        })

    monkeypatch.setattr(UnifiedLLMService, "_request", request)

    async def verify():
        nonlocal remote_ready
        # This test explicitly authorizes fallback. The internal translator
        # keeps its remote-only default; the public API inherits shared policy.
        first = await translator.translate("A cat.", allow_local_fallback=True)
        second = await translator.translate("A cat.", allow_local_fallback=True)
        assert first["profile_id"] == second["profile_id"] == "local"
        assert not first["cached"] and second["cached"]
        assert calls == ["remote", "local", "remote"]
        remote_ready = True
        third = await translator.translate("A cat.", allow_local_fallback=True)
        assert third["translation"] == "远程译文" and third["profile_id"] == "remote"
        assert calls == ["remote", "local", "remote", "remote"]
        assert cache.translation_count() == 2

    asyncio.run(verify())


@pytest.mark.parametrize("disabled", ["shared", "request"])
def test_disabled_caption_cache_never_reads_or_writes_any_candidate(tmp_path, monkeypatch, disabled):
    shared, cache, translator = _caption_translator(tmp_path)
    if disabled == "shared":
        shared.save({"cache": {"translation": False, "caption": True}})

    def forbidden(*_args, **_kwargs):
        raise AssertionError("disabled cache must not be read or written")

    monkeypatch.setattr(cache, "get_translation", forbidden)
    monkeypatch.setattr(cache, "put_translation", forbidden)
    monkeypatch.setattr(cache, "translation_generation", forbidden)

    async def request(_self, profile, _payload):
        if profile.id == "remote":
            raise LLMRequestError("fixture offline", "llm_unreachable")
        return {"choices": [{"finish_reason": "stop"}]}, '{"translation":"本地译文","language":"zh-CN"}'

    monkeypatch.setattr(UnifiedLLMService, "_request", request)
    result = asyncio.run(translator.translate("A cat.", allow_local_fallback=True, use_cache=disabled != "request"))
    assert result["translation"] == "本地译文" and not result["cached"]


def test_caption_clear_blocks_late_translation_write(tmp_path, monkeypatch):
    _shared, cache, translator = _caption_translator(tmp_path)

    async def verify():
        started, release = asyncio.Event(), asyncio.Event()

        async def request(*_args):
            started.set()
            await release.wait()
            return {"choices": [{"finish_reason": "stop"}]}, '{"translation":"一只猫。","language":"zh-CN"}'

        monkeypatch.setattr(UnifiedLLMService, "_request", request)
        operation = asyncio.create_task(translator.translate("A cat."))
        await started.wait()
        cache.clear_translations()
        release.set()
        assert (await operation)["translation"] == "一只猫。"
        assert cache.translation_count() == 0

    asyncio.run(verify())


def test_disabled_tag_cache_skips_generations_failures_reads_and_writes(tmp_path, monkeypatch):
    shared, store, manager = _tag_manager(tmp_path, monkeypatch)
    shared.save({"cache": {"translation": False, "caption": True}})

    def forbidden(*_args, **_kwargs):
        raise AssertionError("disabled cache must not be read or written")

    for name in ("cache_generation", "get_results", "get_failures", "save_results", "save_failures"):
        monkeypatch.setattr(store, name, forbidden)

    async def request(*_args):
        return _tags_content("猫")

    monkeypatch.setattr(UnifiedLLMService, "_request", request)
    assert asyncio.run(manager.resolve("zh-CN", [{"name": "cat", "category": 0}]))["cat"]["text"] == "猫"
