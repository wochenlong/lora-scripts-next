"""Tag 两种来源的确定性契约；配置和缓存均使用临时目录。"""

from __future__ import annotations

import asyncio
import json
import sqlite3

import aiohttp
import pytest

from mikazuki.llm.config import UnifiedConfigStore, config_revision
from mikazuki.llm.service import UnifiedLLMService
from mikazuki.tag_translation import api, providers
from mikazuki.tag_translation.chinese_dictionary_service import ChineseDictionaryService
from mikazuki.tag_translation.translation_service import TranslationError, TranslationManager
from mikazuki.tag_translation.translation_store import TranslationStore


DICT_TAG = "blue_eyes"
MISSING_TAG = "unlisted_tag"
DICT_ROW = {"text": "蓝瞳", "category": 0, "post_count": 42}


class _Dictionary:
    def __init__(self):
        self.lookups = []

    async def ensure(self, _locale):
        return self.status()

    async def wait_for_update(self):
        return self.status()

    def status(self):
        return {"state": "ready", "installed": True}

    def lookup(self, tags):
        self.lookups.append(list(tags))
        return {DICT_TAG: dict(DICT_ROW)} if DICT_TAG in tags else {}

    lookup_all = lookup


@pytest.fixture(autouse=True)
def _deny_real_http(monkeypatch):
    """错误即使被业务层捕获，测试结束时仍会检查是否试图发出真实请求。"""
    attempts = []

    async def forbidden(_session, method, url, **_kwargs):
        attempts.append((method, str(url)))
        raise AssertionError("source-mode tests must not perform real HTTP")

    monkeypatch.setattr(aiohttp.ClientSession, "_request", forbidden)
    yield
    assert attempts == []


def _services(tmp_path, monkeypatch, *, configured=False):
    config_path = tmp_path / "translation.json"
    shared = UnifiedConfigStore(config_path)
    if configured:
        shared.save({
            "profiles": [{
                "id": "fixture-text",
                "source": "remote",
                "endpoint": "https://translation.example.test/v1/chat/completions",
                "model": "fixture-text",
                "api_key": "source-mode-fixture-key",
                "capabilities": ["text"],
                "languages": ["zh-CN"],
            }],
            "routes": {"translation": "fixture-text"},
            "local_fallback_enabled": False,
        })
        profile = shared.load()["profiles"][0]
        shared.record_verification(profile["id"], config_revision(profile), "text")
    else:
        assert not config_path.exists()
        assert shared.load()["profiles"] == []

    dictionary = _Dictionary()
    store = TranslationStore(str(tmp_path / "cache.sqlite3"))
    manager = TranslationManager(config_path, store, primary_store=dictionary)
    monkeypatch.setattr(api, "dictionary_service", dictionary)
    monkeypatch.setattr(api, "translation_store", store)
    monkeypatch.setattr(api, "translation_manager", manager)
    return config_path, shared, store, manager


def _request(provider, *, tags=None, refresh=False):
    return api.TagTranslationRequest(
        tags=[DICT_TAG, MISSING_TAG] if tags is None else tags,
        locale="zh-CN",
        provider=provider,
        refresh=refresh,
    )


def _assert_dictionary_hit(item):
    assert item == {
        "tag": DICT_TAG,
        "translation": "蓝瞳",
        "source": "danbooru",
        "status": "hit",
        "cached": False,
        "error_code": None,
        "category": 0,
        "post_count": 42,
    }


@pytest.mark.parametrize("provider", ["mymemory", "llm"])
def test_selected_source_only_translates_dictionary_misses_and_uses_its_own_cache(
    tmp_path, monkeypatch, provider,
):
    _config, _shared, store, manager = _services(tmp_path, monkeypatch, configured=True)
    calls = {"mymemory": [], "llm": []}
    translations = {"mymemory": "免费译文", "llm": "模型译文"}

    async def free(tags, locale):
        calls["mymemory"].append((list(tags), locale))
        return {tag: translations["mymemory"] for tag in tags}

    async def llm(_service, profile, payload):
        prompt = payload["messages"][-1]["content"]
        request = json.loads(prompt.rsplit("\n", 1)[-1])
        tags = [item["tag"] for item in request["tags"]]
        calls["llm"].append((tags, profile.id))
        return {"choices": [{"finish_reason": "stop"}]}, json.dumps({
            "translations": [{"tag": tag, "translation": translations["llm"]} for tag in tags],
        })

    monkeypatch.setattr(api, "translate_mymemory", free)
    monkeypatch.setattr(UnifiedLLMService, "_request", llm)
    # 另一来源的已有译文不能跳过用户所选来源；词库译文也不能被缓存覆盖。
    other = "llm" if provider == "mymemory" else "mymemory"
    revision = manager.profile_revision() if other == "llm" else "mymemory-v1"
    store.save_results("zh", other, revision, api._items([DICT_TAG, MISSING_TAG]), {
        DICT_TAG: "另一来源蓝眼睛",
        MISSING_TAG: "另一来源缓存",
    })

    async def verify():
        first = await api.resolve_tag_translations(_request(provider))
        second = await api.resolve_tag_translations(_request(provider))
        for response in (first, second):
            items = response["data"]["items"]
            _assert_dictionary_hit(items[0])
            assert items[1]["translation"] == translations[provider]
            assert items[1]["source"] == provider
            assert items[1]["status"] == "hit"
            assert items[1]["error_code"] is None
        assert first["data"]["items"][1]["cached"] is False
        assert second["data"]["items"][1]["cached"] is True

    asyncio.run(verify())
    assert calls[other] == []
    assert len(calls[provider]) == 1
    assert calls[provider][0][0] == [MISSING_TAG]


@pytest.mark.parametrize("provider", ["mymemory", "llm"])
def test_all_dictionary_hits_work_without_llm_configuration_or_provider_calls(
    tmp_path, monkeypatch, provider,
):
    config_path, _shared, _store, manager = _services(tmp_path, monkeypatch)
    calls = []

    async def unexpected(*_args, **_kwargs):
        calls.append(True)
        raise AssertionError("dictionary hits must not call an external translator")

    monkeypatch.setattr(api, "translate_mymemory", unexpected)
    monkeypatch.setattr(manager, "resolve", unexpected)
    response = asyncio.run(api.resolve_tag_translations(_request(provider, tags=[DICT_TAG])))
    _assert_dictionary_hit(response["data"]["items"][0])
    assert calls == []
    assert not config_path.exists()


@pytest.mark.parametrize("provider", ["mymemory", "llm"])
def test_native_escaped_dictionary_hits_do_not_call_external_providers(
    tmp_path, monkeypatch, provider,
):
    config_path, _shared, _store, manager = _services(tmp_path, monkeypatch)
    with sqlite3.connect(tmp_path / "tag.sqlite") as connection:
        connection.execute(
            "CREATE TABLE tags (name TEXT PRIMARY KEY, category INTEGER, cn_name TEXT, post_count INTEGER)"
        )
        connection.executemany(
            "INSERT INTO tags VALUES (?, 0, ?, 1)",
            [(";)", "眨眼笑"), ("poster_(object)", "海报（物体）")],
        )
    monkeypatch.setattr(api, "dictionary_service", ChineseDictionaryService(str(tmp_path)))
    calls = []

    async def unexpected(*_args, **_kwargs):
        calls.append(True)
        raise AssertionError("native escaped dictionary hits must not call an external provider")

    monkeypatch.setattr(api, "translate_mymemory", unexpected)
    monkeypatch.setattr(manager, "resolve", unexpected)
    response = asyncio.run(api.resolve_tag_translations(
        _request(provider, tags=[r";\)", r"poster \(object\)"], refresh=True)
    ))

    assert [item["translation"] for item in response["data"]["items"]] == ["眨眼笑", "海报（物体）"]
    assert all(item["source"] == "danbooru" and item["status"] == "hit" for item in response["data"]["items"])
    assert calls == []
    assert not config_path.exists()


def test_mymemory_adapter_translates_without_any_llm_configuration(tmp_path, monkeypatch):
    config_path, _shared, store, manager = _services(tmp_path, monkeypatch)
    free_calls, llm_calls = [], []

    class Response:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def json(self, **_kwargs):
            return {"responseStatus": 200, "responseData": {"translatedText": "免费译文"}}

    class Session:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        def get(self, url, *, params, headers):
            free_calls.append((url, dict(params), dict(headers)))
            return Response()

    async def unexpected_llm(*_args, **_kwargs):
        llm_calls.append(True)
        raise AssertionError("free mode must not call an LLM")

    monkeypatch.setattr(providers.aiohttp, "ClientSession", Session)
    monkeypatch.setattr(manager, "resolve", unexpected_llm)
    response = asyncio.run(api.resolve_tag_translations(_request("mymemory")))
    _assert_dictionary_hit(response["data"]["items"][0])
    assert response["data"]["items"][1]["translation"] == "免费译文"
    assert response["data"]["items"][1]["source"] == "mymemory"
    assert len(free_calls) == 1
    assert free_calls[0][0] == providers.MYMEMORY_URL
    assert free_calls[0][1] == {"q": MISSING_TAG, "langpair": "en|zh-CN"}
    assert "Authorization" not in free_calls[0][2]
    assert llm_calls == []
    assert store.result_count("mymemory") == 1
    assert not config_path.exists()


def test_llm_mode_without_a_profile_preserves_dictionary_hits_and_never_uses_free(
    tmp_path, monkeypatch,
):
    _services(tmp_path, monkeypatch)
    calls = []

    async def unexpected(*_args, **_kwargs):
        calls.append(True)
        raise AssertionError("unconfigured LLM mode must not fall back to free")

    monkeypatch.setattr(api, "translate_mymemory", unexpected)
    monkeypatch.setattr(UnifiedLLMService, "_request", unexpected)
    response = asyncio.run(api.resolve_tag_translations(_request("llm")))
    _assert_dictionary_hit(response["data"]["items"][0])
    missing = response["data"]["items"][1]
    assert missing["translation"] is None
    assert missing["source"] is None
    assert missing["status"] == "missing"
    assert missing["error_code"] == "translation_missing"
    assert calls == []


@pytest.mark.parametrize("provider", ["mymemory", "llm"])
@pytest.mark.parametrize("failure", ["empty", "exception"])
def test_missing_provider_failures_preserve_dictionary_hits_without_cross_fallback(
    tmp_path, monkeypatch, provider, failure,
):
    _config, _shared, _store, manager = _services(tmp_path, monkeypatch)
    calls = {"mymemory": [], "llm": []}
    error_code = "fixture_free_unavailable" if provider == "mymemory" else "fixture_llm_unavailable"

    async def fail(source, tags):
        calls[source].append(list(tags))
        if failure == "exception":
            raise TranslationError("synthetic provider unavailable", error_code)
        return {}

    async def free(tags, _locale):
        return await fail("mymemory", tags)

    async def llm(_locale, items, **_kwargs):
        return await fail("llm", [item["name"] for item in items])

    monkeypatch.setattr(api, "translate_mymemory", free)
    monkeypatch.setattr(manager, "resolve", llm)
    response = asyncio.run(api.resolve_tag_translations(_request(provider)))
    _assert_dictionary_hit(response["data"]["items"][0])
    missing = response["data"]["items"][1]
    assert missing["translation"] is None
    assert missing["source"] is None
    if failure == "exception":
        assert missing["status"] == "error"
        assert missing["error_code"] == error_code
    elif provider == "mymemory":
        assert missing["status"] == "error"
        assert missing["error_code"] == "network_no_result"
    else:
        assert missing["status"] == "missing"
        assert missing["error_code"] == "translation_missing"
    assert calls[provider] == [[MISSING_TAG]]
    assert calls["llm" if provider == "mymemory" else "mymemory"] == []


INVALID_CONFIGS = {
    "broken_json": "{",
    "invalid_legacy": json.dumps({"deepseek": {"batch_size": 0}}),
    "invalid_shared_profile": json.dumps({"llm": {"profiles": [{"id": "invalid"}]}}),
}


@pytest.mark.parametrize("provider", ["mymemory", "llm"])
@pytest.mark.parametrize("invalid_config", INVALID_CONFIGS)
def test_dictionary_hits_skip_config_and_cache_with_invalid_real_config_files(
    tmp_path, monkeypatch, provider, invalid_config,
):
    config_path, _shared, store, manager = _services(tmp_path, monkeypatch)
    config_path.write_text(INVALID_CONFIGS[invalid_config], encoding="utf-8")
    attempts = []

    def forbidden(*_args, **_kwargs):
        attempts.append(True)
        raise AssertionError("dictionary hits must not read configuration or external caches")

    monkeypatch.setattr(manager, "cache_enabled", forbidden)
    monkeypatch.setattr(manager, "profile_revision", forbidden)
    monkeypatch.setattr(manager, "resolve", forbidden)
    monkeypatch.setattr(api, "translate_mymemory", forbidden)
    for name in ("cache_generation", "get_results", "save_results"):
        monkeypatch.setattr(store, name, forbidden)
    response = asyncio.run(api.resolve_tag_translations(_request(provider, tags=[DICT_TAG])))
    _assert_dictionary_hit(response["data"]["items"][0])
    assert attempts == []


@pytest.mark.parametrize("provider", ["mymemory", "llm"])
@pytest.mark.parametrize("invalid_config", INVALID_CONFIGS)
def test_invalid_real_config_preserves_dictionary_and_selected_source_behavior(
    tmp_path, monkeypatch, provider, invalid_config,
):
    config_path, _shared, store, manager = _services(tmp_path, monkeypatch)
    config_path.write_text(INVALID_CONFIGS[invalid_config], encoding="utf-8")
    free_calls, llm_requests, cache_attempts, revisions = [], [], [], []
    original_revision = manager.profile_revision

    def revision(*args, **kwargs):
        revisions.append(True)
        return original_revision(*args, **kwargs)

    def cache_forbidden(*_args, **_kwargs):
        cache_attempts.append(True)
        raise AssertionError("unreadable cache policy must disable external caches")

    async def free(tags, _locale):
        free_calls.append(list(tags))
        return {MISSING_TAG: "免费译文"}

    async def unexpected_llm_request(*_args, **_kwargs):
        llm_requests.append(True)
        raise AssertionError("invalid configuration must not create an LLM HTTP request")

    monkeypatch.setattr(manager, "profile_revision", revision)
    monkeypatch.setattr(api, "translate_mymemory", free)
    monkeypatch.setattr(UnifiedLLMService, "_request", unexpected_llm_request)
    if invalid_config != "invalid_shared_profile":
        for name in ("cache_generation", "get_results", "save_results"):
            monkeypatch.setattr(store, name, cache_forbidden)
    response = asyncio.run(api.resolve_tag_translations(_request(provider)))
    _assert_dictionary_hit(response["data"]["items"][0])
    missing = response["data"]["items"][1]
    if provider == "mymemory":
        assert missing["translation"] == "免费译文"
        assert missing["source"] == "mymemory"
        assert missing["status"] == "hit"
        assert missing["cached"] is False
        assert missing["error_code"] is None
        assert free_calls == [[MISSING_TAG]]
        assert revisions == []
    else:
        assert missing["translation"] is None
        assert missing["source"] is None
        assert missing["status"] == "error"
        assert missing["error_code"] in {"llm_request_failed", "llm_invalid_response"}
        assert free_calls == []
    assert llm_requests == []
    assert cache_attempts == []


def test_mymemory_honors_disabled_shared_cache_without_reading_llm_profile(
    tmp_path, monkeypatch,
):
    _config, shared, store, manager = _services(tmp_path, monkeypatch, configured=True)
    shared.save({"cache": {"translation": False, "caption": True}})
    forbidden_calls, free_calls = [], []

    def forbidden(*_args, **_kwargs):
        forbidden_calls.append(True)
        raise AssertionError("disabled cache and LLM profile must not be consulted")

    async def free(tags, _locale):
        free_calls.append(list(tags))
        return {MISSING_TAG: "免费译文"}

    monkeypatch.setattr(manager, "profile_revision", forbidden)
    monkeypatch.setattr(manager, "resolve", forbidden)
    for name in ("cache_generation", "get_results", "save_results"):
        monkeypatch.setattr(store, name, forbidden)
    monkeypatch.setattr(api, "translate_mymemory", free)
    response = asyncio.run(api.resolve_tag_translations(_request("mymemory")))
    _assert_dictionary_hit(response["data"]["items"][0])
    assert response["data"]["items"][1]["translation"] == "免费译文"
    assert response["data"]["items"][1]["cached"] is False
    assert free_calls == [[MISSING_TAG]]
    assert forbidden_calls == []


@pytest.mark.parametrize("refresh", [False, True])
def test_mymemory_cache_clear_blocks_late_writes_including_refresh(
    tmp_path, monkeypatch, refresh,
):
    _config, _shared, store, _manager = _services(tmp_path, monkeypatch)
    if refresh:
        store.save_results("zh", "mymemory", "mymemory-v1", api._items([MISSING_TAG]), {
            MISSING_TAG: "旧缓存译文",
        })
    original_save = store.save_results
    written_generations, cache_reads = [], []

    def save(*args, **kwargs):
        written_generations.append(kwargs.get("expected_generation"))
        return original_save(*args, **kwargs)

    original_read = store.get_results

    def read(*args, **kwargs):
        cache_reads.append(True)
        return original_read(*args, **kwargs)

    monkeypatch.setattr(store, "save_results", save)
    monkeypatch.setattr(store, "get_results", read)

    async def verify():
        started, release = asyncio.Event(), asyncio.Event()
        initial_generation = store.cache_generation("mymemory")

        async def free(tags, _locale):
            assert tags == [MISSING_TAG]
            started.set()
            await release.wait()
            return {MISSING_TAG: "迟到译文"}

        monkeypatch.setattr(api, "translate_mymemory", free)
        request = asyncio.create_task(api.resolve_tag_translations(_request("mymemory", refresh=refresh)))
        await asyncio.wait_for(started.wait(), timeout=2)
        store.clear_results("mymemory")
        assert store.cache_generation("mymemory") == initial_generation + 1
        release.set()
        response = await asyncio.wait_for(request, timeout=2)
        _assert_dictionary_hit(response["data"]["items"][0])
        assert response["data"]["items"][1]["translation"] == "迟到译文"
        assert written_generations == [initial_generation]
        assert store.result_count("mymemory") == 0

    asyncio.run(verify())
    assert len(cache_reads) == (0 if refresh else 1)


def test_mymemory_refresh_failure_does_not_return_previous_cached_translation(
    tmp_path, monkeypatch,
):
    _config, _shared, store, _manager = _services(tmp_path, monkeypatch)
    store.save_results("zh", "mymemory", "mymemory-v1", api._items([MISSING_TAG]), {
        MISSING_TAG: "旧缓存译文",
    })

    async def empty(tags, _locale):
        assert tags == [MISSING_TAG]
        return {}

    monkeypatch.setattr(api, "translate_mymemory", empty)
    response = asyncio.run(api.resolve_tag_translations(_request("mymemory", refresh=True)))
    _assert_dictionary_hit(response["data"]["items"][0])
    missing = response["data"]["items"][1]
    assert missing["translation"] is None
    assert missing["status"] == "error"
    assert missing["cached"] is False
    assert missing["error_code"] == "network_no_result"
    assert store.get_results("zh", [MISSING_TAG], "mymemory", "mymemory-v1")[MISSING_TAG]["text"] == "旧缓存译文"
