"""Public cache clearing includes Caption results and rejects old inference writes."""
from __future__ import annotations

import asyncio
import hashlib
import json
import sqlite3
import threading

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from mikazuki.llm import runtime
from mikazuki.llm.cache import CaptionCache
from mikazuki.llm.config import UnifiedConfigStore, config_revision
from mikazuki.llm.http import LLMRequestError
from mikazuki.llm.service import UnifiedLLMService
from mikazuki.tag_translation import api
from mikazuki.tag_translation.translation_store import TranslationStore
from mikazuki.tagger.caption_job import CaptionJobManager, caption_sha256
from mikazuki.tagger.caption_store import CaptionJobStore


CAPTION_KEY = ("image-sha", "profile-v1", "prompt-v1", "en", "jpeg-v1")


def _public_cache(tmp_path, monkeypatch):
    database = tmp_path / "shared.sqlite3"
    translations = TranslationStore(str(database))
    captions = CaptionCache(database)
    jobs = CaptionJobStore(database)
    monkeypatch.setattr(api, "translation_store", translations)
    monkeypatch.setattr(runtime, "caption_cache", captions)
    application = FastAPI()
    application.include_router(api.router, prefix="/api")
    return TestClient(application), translations, captions, jobs


def _seed_results(translations, captions):
    item = {"name": "cat", "category": 0, "post_count": 1}
    for provider in ("mymemory", "llm"):
        translations.save_results("zh", provider, "revision", [item], {"cat": "猫"})
    captions.put(*CAPTION_KEY, "A cat.")
    captions.put_translation("source-sha", "profile-v1", "zh-CN", "一只猫。")


@pytest.mark.parametrize("provider", [None, "llm", "mymemory"])
def test_public_clear_counts_all_results_and_respects_provider(tmp_path, monkeypatch, provider):
    client, translations, captions, _jobs = _public_cache(tmp_path, monkeypatch)
    _seed_results(translations, captions)
    before = client.get("/api/tag-translation/cache")
    assert before.status_code == 200
    assert before.json()["data"]["total"] == 4

    response = client.delete("/api/tag-translation/cache", params={"provider": provider} if provider else {})
    assert response.status_code == 200
    expected = 0 if provider is None else (1 if provider == "llm" else 3)
    assert response.json()["data"] == {"provider": provider, "total": expected}
    assert client.get("/api/tag-translation/cache").json()["data"]["total"] == expected
    assert translations.result_count("mymemory") == (1 if provider == "llm" else 0)
    assert translations.result_count("llm") == (1 if provider == "mymemory" else 0)
    assert captions.count() == (1 if provider == "mymemory" else 0)
    assert captions.translation_count() == (1 if provider == "mymemory" else 0)
    assert captions.get(*CAPTION_KEY) == ("A cat." if provider == "mymemory" else None)


def test_clear_preserves_dictionary_files_captions_and_task_recovery(tmp_path, monkeypatch):
    client, translations, captions, jobs = _public_cache(tmp_path, monkeypatch)
    _seed_results(translations, captions)
    dictionary = tmp_path / "dictionary.sqlite3"
    with sqlite3.connect(dictionary) as connection:
        connection.execute("CREATE TABLE dictionary (tag TEXT, text TEXT)")
        connection.execute("INSERT INTO dictionary VALUES ('cat', '猫')")
    image = tmp_path / "cat.png"
    Image.new("RGB", (16, 16), "white").save(image)
    target = image.with_suffix(".txt")
    target.write_text("A preserved cat.\n", encoding="utf-8")
    current_hash = caption_sha256(target)
    state = {"job_id": "existing-job", "updated_at": 1.0, "phase": "done", "report": {"items": []}}
    jobs.save(state, {"path": str(tmp_path)}, [str(image)], [0], [])
    jobs.backup("existing-job", 0, b"previous caption", "old-hash")
    jobs.remember_format(target, current_hash, "natural", writer_job_id="existing-job")
    jobs.prepare_write_intent(target, target.read_bytes(), current_hash, "pending-hash")
    preserved = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in (dictionary, image, target)}
    history, backup = jobs.history(), jobs.get_backup("existing-job", 0)
    recovery, intent = jobs.get("existing-job"), jobs.get_write_intent(target)
    provenance = jobs.format_record(target)

    assert client.delete("/api/tag-translation/cache").json()["data"]["total"] == 0
    assert {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in preserved} == preserved
    assert jobs.history() == history
    assert jobs.get("existing-job") == recovery
    assert jobs.get_backup("existing-job", 0) == backup
    assert jobs.get_write_intent(target) == intent
    assert jobs.format_record(target) == provenance


def test_caption_generation_is_persistent_independent_and_blocks_stale_reads_and_writes(tmp_path):
    database = tmp_path / "caption.sqlite3"
    cache = CaptionCache(database)
    generation = cache.generation()
    translation_generation = cache.translation_generation()
    cache.put(*CAPTION_KEY, "Old result.", expected_generation=generation)
    cache.put_translation("source", "revision", "zh-CN", "译文")
    cache.clear()
    assert cache.generation() == generation + 1
    assert cache.translation_generation() == translation_generation
    assert cache.translation_count() == 1
    reopened = CaptionCache(database)
    assert reopened.generation() == generation + 1
    reopened.put(*CAPTION_KEY, "Fresh result.", expected_generation=reopened.generation())
    assert cache.get(*CAPTION_KEY, expected_generation=generation) is None
    assert cache.get(*CAPTION_KEY, expected_generation=reopened.generation()) == "Fresh result."
    cache.put(*CAPTION_KEY, "Late result.", expected_generation=generation)
    assert cache.get(*CAPTION_KEY) == "Fresh result."
    cache.clear_translations()
    assert cache.generation() == generation + 1
    assert cache.get(*CAPTION_KEY) == "Fresh result."


def test_generation_upgrade_preserves_existing_caption_and_translation_rows(tmp_path):
    database = tmp_path / "caption.sqlite3"
    original = CaptionCache(database)
    original.put(*CAPTION_KEY, "Existing result.")
    original.put_translation("source", "revision", "zh-CN", "现有译文。")
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE caption_cache_generation")
    upgraded = CaptionCache(database)
    assert upgraded.generation() == 0
    assert upgraded.get(*CAPTION_KEY) == "Existing result."
    assert upgraded.get_translation("source", "revision", "zh-CN") == "现有译文。"


def _vision_service(tmp_path):
    store = UnifiedConfigStore(tmp_path / "config.json")
    store.save({"profiles": [{
        "id": "remote", "name": "Remote", "source": "remote", "model": "fixture",
        "api_key": "fixture", "endpoint": "https://remote.example.test/v1/chat/completions",
        "capabilities": ["vision"], "languages": ["en"],
    }], "local_fallback_enabled": False, "routes": {"caption": "remote"}})
    profile = store.load()["profiles"][0]
    store.record_verification(profile["id"], config_revision(profile), "vision")
    return UnifiedLLMService(store)


def test_public_clear_during_caption_inference_cannot_refill_cache_and_next_job_is_cold(tmp_path, monkeypatch):
    client, _translations, captions, jobs = _public_cache(tmp_path, monkeypatch)
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    image = image_dir / "cat.png"
    Image.new("RGB", (16, 16), "white").save(image)
    image_hash = caption_sha256(image)
    started, release = threading.Event(), threading.Event()
    calls = []

    async def request(profile, _payload, **_options):
        calls.append(profile.id)
        if len(calls) == 1:
            started.set()
            while not release.is_set():
                await asyncio.sleep(0.01)
        return {"choices": [{"finish_reason": "stop"}]}, json.dumps({"caption": "A cat.", "language": "en"})

    monkeypatch.setattr("mikazuki.llm.service.chat_completion", request)
    manager = CaptionJobManager(_vision_service(tmp_path), cache=captions, job_store=jobs)
    payload = {"path": str(image_dir), "mode": "natural", "language": "en", "conflict_action": "copy"}
    manager.start(payload)
    try:
        assert started.wait(timeout=5)
        assert client.delete("/api/tag-translation/cache").status_code == 200
    finally:
        release.set()
        manager._thread.join(timeout=5)
    assert not manager._thread.is_alive()
    assert manager.status()["succeeded"] == 1
    assert captions.count() == 0
    assert image.with_suffix(".txt").read_text(encoding="utf-8") == "A cat.\n"
    assert caption_sha256(image) == image_hash

    manager.start(payload)
    manager._thread.join(timeout=5)
    assert not manager._thread.is_alive()
    assert manager.status()["succeeded"] == 1
    assert not manager.status()["report"]["items"][0]["cached"]
    assert calls == ["remote", "remote"]
    assert captions.count() == 1
    manager.start(payload)
    manager._thread.join(timeout=5)
    assert not manager._thread.is_alive()
    assert manager.status()["succeeded"] == 1
    assert manager.status()["report"]["items"][0]["cached"]
    assert calls == ["remote", "remote"]
    assert len(jobs.history()) == 3

    history = jobs.all_jobs()
    target_hash = caption_sha256(image.with_suffix(".txt"))
    assert client.delete("/api/tag-translation/cache").json()["data"]["total"] == 0
    assert jobs.all_jobs() == history
    assert caption_sha256(image.with_suffix(".txt")) == target_hash
    assert caption_sha256(image) == image_hash


def test_clear_during_remote_call_blocks_old_job_from_reading_new_local_candidate_cache(tmp_path, monkeypatch):
    client, _translations, captions, _jobs = _public_cache(tmp_path, monkeypatch)
    image_dir = tmp_path / "images"
    image_dir.mkdir()
    image = image_dir / "cat.png"
    Image.new("RGB", (16, 16), "white").save(image)
    service = _vision_service(tmp_path)
    config = service.config_store.load()
    service.config_store.save({"profiles": [*config["profiles"], {
        "id": "local", "name": "Local", "source": "local-endpoint", "model": "fixture-local",
        "endpoint": "http://127.0.0.1:9/v1/chat/completions",
        "capabilities": ["vision"], "languages": ["en"],
    }]})
    local = next(profile for profile in service.config_store.load()["profiles"] if profile["id"] == "local")
    service.config_store.record_verification("local", config_revision(local), "vision")
    started, release = threading.Event(), threading.Event()
    calls, lookups = [], []
    original_get = captions.get

    def get(*args, **kwargs):
        lookups.append(args)
        return original_get(*args, **kwargs)

    async def request(profile, _payload, **_options):
        calls.append(profile.id)
        if profile.id == "remote":
            started.set()
            while not release.is_set():
                await asyncio.sleep(0.01)
            raise LLMRequestError("fixture offline", "llm_unreachable")
        return {"choices": [{"finish_reason": "stop"}]}, json.dumps({"caption": "A generated cat.", "language": "en"})

    monkeypatch.setattr(captions, "get", get)
    monkeypatch.setattr("mikazuki.llm.service.chat_completion", request)
    manager = CaptionJobManager(service, cache=captions)
    manager.start({"path": str(image_dir), "language": "en", "allow_local_fallback": True})
    try:
        assert started.wait(timeout=5)
        assert len(lookups) == 1
        assert client.delete("/api/tag-translation/cache").status_code == 200
        key = (lookups[0][0], config_revision(local), *lookups[0][2:])
        captions.put(*key, "A new generation cache entry.", expected_generation=captions.generation())
    finally:
        release.set()
        manager._thread.join(timeout=5)
    assert not manager._thread.is_alive()
    assert manager.status()["succeeded"] == 1
    assert not manager.status()["report"]["items"][0]["cached"]
    assert calls == ["remote", "local"]
    assert image.with_suffix(".txt").read_text(encoding="utf-8") == "A generated cat.\n"
    assert original_get(*key) == "A new generation cache entry."
    assert captions.count() == 1
