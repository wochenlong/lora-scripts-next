import asyncio
import hashlib
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from mikazuki.llm import api
from mikazuki.llm.cache import CaptionCache
from mikazuki.llm.caption_translation import CaptionTextTranslator, PROMPT_REVISION
from mikazuki.llm.caption_translation_gate import refresh_translation_gate, translation_gate
from mikazuki.llm.config import UnifiedConfigStore, config_revision
from mikazuki.llm.service import UnifiedLLMService


def _translator(tmp_path, *, concurrency=3, source="remote"):
    store = UnifiedConfigStore(tmp_path / "config.json")
    store.save({"profiles": [{
        "id": "text", "name": "Fixture", "source": source, "model": "fixture-model",
        "endpoint": "http://127.0.0.1:9/v1/chat/completions",
        "capabilities": ["text"], "languages": ["zh-CN"],
    }], "caption_translation": {"concurrency": concurrency, "max_tokens": 2048, "temperature": 0},
        "local_fallback_enabled": source != "remote"})
    profile = store.load()["profiles"][0]
    store.record_verification("text", config_revision(profile), "text")
    service = UnifiedLLMService(store)
    cache = CaptionCache(tmp_path / "cache.sqlite3")
    return store, service, cache, CaptionTextTranslator(service, cache)


def _result():
    return {"choices": [{"finish_reason": "stop"}]}, '{"translation":"一只猫。","language":"zh-CN"}'


async def _until(condition):
    async def wait():
        while not condition():
            await asyncio.sleep(0.005)
    await asyncio.wait_for(wait(), timeout=3)


def test_configured_parameters_reach_provider_and_own_cache_identity(tmp_path, monkeypatch):
    store, service, cache, translator = _translator(tmp_path)
    payloads = []

    async def request(_self, _profile, payload):
        payloads.append(payload)
        return _result()

    monkeypatch.setattr(UnifiedLLMService, "_request", request)
    source = "A cat on a windowsill."
    profile = service.resolve("text", language="zh-CN")
    source_hash = hashlib.sha256(source.encode()).hexdigest()
    cache.put_translation(source_hash, config_revision(profile, PROMPT_REVISION), "zh-CN", "已有默认译文。")
    assert asyncio.run(translator.translate(source))["translation"] == "已有默认译文。"
    assert payloads == []
    store.save({"caption_translation": {"concurrency": 1, "max_tokens": 2048, "temperature": 0}})
    assert asyncio.run(translator.translate(source))["cached"] and payloads == []
    store.save({"caption_translation": {"concurrency": 1, "max_tokens": 4096, "temperature": 0.7}})
    assert not asyncio.run(translator.translate(source))["cached"]
    assert payloads[-1]["max_tokens"] == 4096 and payloads[-1]["temperature"] == 0.7
    assert asyncio.run(translator.translate(source))["cached"] and len(payloads) == 1
    store.save({"caption_translation": {"concurrency": 4, "max_tokens": 4096, "temperature": 0.7}})
    assert asyncio.run(translator.translate(source))["cached"] and len(payloads) == 1
    store.save({"caption_translation": {"concurrency": 4, "max_tokens": 4096, "temperature": 0.8}})
    assert not asyncio.run(translator.translate(source))["cached"] and len(payloads) == 2
    store.save({"caption_translation": {"concurrency": 3, "max_tokens": 2048, "temperature": 0}})
    assert asyncio.run(translator.translate(source))["translation"] == "已有默认译文。"


def test_new_default_temperature_does_not_replay_legacy_zero_cache(tmp_path, monkeypatch):
    from mikazuki.llm.secrets import read_configuration, write_configuration

    store, service, cache, translator = _translator(tmp_path)
    source = "A cat on a windowsill."
    profile = service.resolve("text", language="zh-CN")
    source_hash = hashlib.sha256(source.encode()).hexdigest()
    cache.put_translation(source_hash, config_revision(profile, PROMPT_REVISION), "zh-CN", "旧零温译文。")
    # An older configuration has no translation parameter section. Its new
    # default changes to 0.7, while an explicitly stored zero remains valid.
    document = read_configuration(store.path)
    document["llm"].pop("caption_translation")
    write_configuration(store.path, document)
    payloads = []

    async def request(_self, _profile, payload):
        payloads.append(payload)
        return _result()

    monkeypatch.setattr(UnifiedLLMService, "_request", request)
    first = asyncio.run(translator.translate(source))
    assert not first["cached"] and first["translation"] == "一只猫。"
    assert len(payloads) == 1 and payloads[0]["temperature"] == 0.7 and payloads[0]["max_tokens"] == 2048
    assert asyncio.run(translator.translate(source))["cached"] and len(payloads) == 1
    store.save({"caption_translation": {"concurrency": 3, "max_tokens": 2048, "temperature": 0}})
    restored = asyncio.run(translator.translate(source))
    assert restored["cached"] and restored["translation"] == "旧零温译文。" and len(payloads) == 1


def test_provider_limit_queue_cancellation_and_shortcuts(tmp_path, monkeypatch):
    _store, service, cache, translator = _translator(tmp_path)
    gate = translation_gate(service)

    async def verify():
        release = asyncio.Event()
        calls, active, maximum = [], 0, 0

        async def request(_self, _profile, payload):
            nonlocal active, maximum
            active += 1
            maximum = max(maximum, active)
            calls.append(payload)
            try:
                await release.wait()
                return _result()
            finally:
                active -= 1

        monkeypatch.setattr(UnifiedLLMService, "_request", request)
        cached_source = "A cached cat."
        profile = service.resolve("text", language="zh-CN")
        cache.put_translation(hashlib.sha256(cached_source.encode()).hexdigest(), config_revision(profile, PROMPT_REVISION), "zh-CN", "缓存猫。")
        operations = [asyncio.create_task(translator.translate(f"A cat number {index}.", use_cache=False)) for index in range(7)]
        await _until(lambda: gate.snapshot()["waiting"] == 4)
        assert len(calls) == 3 and gate.snapshot()["active"] == 3
        assert (await asyncio.wait_for(translator.translate("中文描述。"), timeout=0.2))["skipped"]
        assert (await asyncio.wait_for(translator.translate(cached_source), timeout=0.2))["cached"]
        operations[-1].cancel()
        with pytest.raises(asyncio.CancelledError):
            await operations[-1]
        assert len(calls) == 3 and gate.snapshot()["waiting"] == 3
        operations[0].cancel()
        with pytest.raises(asyncio.CancelledError):
            await operations[0]
        await _until(lambda: len(calls) == 4)
        assert gate.snapshot()["active"] == 3 and maximum == 3
        release.set()
        await asyncio.wait_for(asyncio.gather(*operations[1:-1]), timeout=3)
        assert len(calls) == 6 and maximum == 3
        assert gate.snapshot()["active"] == gate.snapshot()["waiting"] == 0

    asyncio.run(verify())


def test_dynamic_limit_increase_and_decrease_drains_existing_queue(tmp_path, monkeypatch):
    store, service, _cache, translator = _translator(tmp_path, concurrency=1)
    gate = translation_gate(service)

    async def verify():
        calls = []
        releases = [asyncio.Event() for _ in range(5)]

        async def request(_self, _profile, _payload):
            index = len(calls)
            calls.append(index)
            await releases[index].wait()
            return _result()

        monkeypatch.setattr(UnifiedLLMService, "_request", request)
        tasks = [asyncio.create_task(translator.translate(f"A cat {index}.", use_cache=False)) for index in range(5)]
        await _until(lambda: gate.snapshot()["waiting"] == 4)
        store.save({"caption_translation": {"concurrency": 3, "max_tokens": 2048, "temperature": 0}})
        refresh_translation_gate(service)
        await _until(lambda: len(calls) == 3)
        store.save({"caption_translation": {"concurrency": 1, "max_tokens": 2048, "temperature": 0}})
        refresh_translation_gate(service)
        releases[0].set()
        releases[1].set()
        await _until(lambda: gate.snapshot()["active"] == 1)
        assert len(calls) == 3 and gate.snapshot()["waiting"] == 2
        releases[2].set()
        await _until(lambda: len(calls) == 4)
        assert gate.snapshot()["active"] == 1
        releases[3].set()
        await _until(lambda: len(calls) == 5)
        releases[4].set()
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=3)
        assert gate.snapshot()["active"] == gate.snapshot()["waiting"] == 0

    asyncio.run(verify())


def test_multiple_testclient_threads_share_provider_limit_without_loop_deadlock(tmp_path, monkeypatch):
    _store, service, cache, _translator_instance = _translator(tmp_path, concurrency=2)
    mutex, barrier = threading.Lock(), threading.Barrier(6)
    active, maximum, calls = 0, 0, 0

    async def request(_self, _profile, _payload):
        nonlocal active, maximum, calls
        with mutex:
            active += 1
            calls += 1
            maximum = max(maximum, active)
        try:
            await asyncio.sleep(0.08)
            return _result()
        finally:
            with mutex:
                active -= 1

    monkeypatch.setattr(UnifiedLLMService, "_request", request)
    monkeypatch.setattr(api, "llm_service", service)
    monkeypatch.setattr(api, "caption_cache", cache)
    app = FastAPI()
    app.include_router(api.router, prefix="/api")

    def translate(index):
        barrier.wait(timeout=3)
        with TestClient(app) as client:
            return client.post("/api/llm/caption-translation", json={"text": f"A cat {index}.", "use_cache": False})

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = [executor.submit(translate, index) for index in range(6)]
        assert all(future.result(timeout=6).status_code == 200 for future in futures)
    assert maximum == 2 and calls == 6 and active == 0
    assert translation_gate(service).snapshot()["waiting"] == 0


def test_suppressed_provider_cancellation_cannot_persist_late_translation(tmp_path, monkeypatch):
    _store, service, cache, translator = _translator(tmp_path, concurrency=1)

    async def verify():
        started = asyncio.Event()

        async def request(*_args):
            started.set()
            try:
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                return _result()

        monkeypatch.setattr(UnifiedLLMService, "_request", request)
        task = asyncio.create_task(translator.translate("A cat."))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cache.translation_count() == 0
        assert translation_gate(service).snapshot()["active"] == 0

    asyncio.run(verify())


def test_disconnected_queued_http_request_never_contacts_provider(tmp_path, monkeypatch):
    _store, service, cache, translator = _translator(tmp_path, concurrency=1)
    gate = translation_gate(service)
    monkeypatch.setattr(api, "llm_service", service)
    monkeypatch.setattr(api, "caption_cache", cache)

    async def verify():
        started, release = asyncio.Event(), asyncio.Event()
        calls = []

        async def request(*_args):
            calls.append(True)
            started.set()
            await release.wait()
            return _result()

        class DisconnectedWhileQueued:
            async def is_disconnected(self):
                return gate.snapshot()["waiting"] > 0

        monkeypatch.setattr(UnifiedLLMService, "_request", request)
        running = asyncio.create_task(translator.translate("A running cat.", use_cache=False))
        await started.wait()
        with pytest.raises(HTTPException) as raised:
            await api.translate_caption_text(api.CaptionTranslationRequest(text="A queued cat."), DisconnectedWhileQueued())
        assert raised.value.status_code == 499
        assert calls == [True] and gate.snapshot()["active"] == 1 and gate.snapshot()["waiting"] == 0
        release.set()
        await running
        assert cache.translation_count() == 0 and gate.snapshot()["active"] == 0

    asyncio.run(verify())


def test_managed_local_translation_still_uses_shared_local_scheduler(tmp_path, monkeypatch):
    _store, service, _cache, translator = _translator(tmp_path, concurrency=3, source="managed-local")
    from mikazuki.llm import service as service_module
    from mikazuki.llm.scheduler import shared_local_scheduler

    async def verify():
        release = asyncio.Event()
        calls = []

        async def request(_profile, _payload, **_options):
            calls.append(True)
            await release.wait()
            return _result()

        monkeypatch.setattr(service_module, "chat_completion", request)
        tasks = [asyncio.create_task(translator.translate(f"A cat {index}.", use_cache=False, allow_local_fallback=True)) for index in range(3)]
        await _until(lambda: shared_local_scheduler.snapshot()["waiting"] == 2)
        assert len(calls) == 1
        assert translation_gate(service).snapshot()["active"] == 3
        tasks[1].cancel()
        with pytest.raises(asyncio.CancelledError):
            await tasks[1]
        assert shared_local_scheduler.snapshot()["waiting"] == 1
        release.set()
        await asyncio.wait_for(asyncio.gather(tasks[0], tasks[2]), timeout=3)
        assert len(calls) == 2 and not shared_local_scheduler.is_busy()
        assert translation_gate(service).snapshot()["active"] == 0

    asyncio.run(verify())
