import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import aiohttp
import pytest

from mikazuki.llm.config import UnifiedConfigStore
from mikazuki.llm.service import UnifiedLLMService
from mikazuki.tag_translation.translation_config import OnlineServiceConfig
from mikazuki.tag_translation.translation_service import DeepSeekClient, TranslationManager


class TextProvider(BaseHTTPRequestHandler):
    def do_POST(self):
        self.server.requests = getattr(self.server, "requests", 0) + 1
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        assert body["model"] == "text-model"
        content = json.dumps({"translations": [{"tag": "cat", "translation": "猫"}]}, ensure_ascii=False)
        response = json.dumps({"choices": [{"message": {"content": content}, "finish_reason": "stop"}]}, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, *_args):
        pass


def test_legacy_translation_and_unified_text_path_share_migrated_route_and_result(tmp_path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), TextProvider)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        path = tmp_path / "translation.json"
        legacy_store = OnlineServiceConfig(path)
        legacy_store.save({"deepseek": {
            "endpoint": f"http://127.0.0.1:{server.server_port}/v1/chat/completions",
            "model": "text-model", "api_key": "fixture-runtime-key",
        }})
        manager = TranslationManager(path, store=None)
        before = manager._active_llm_config(legacy_store.load())
        shared = UnifiedConfigStore(path)
        migrated = shared.load()
        shared.save(migrated)
        after = manager._active_llm_config(legacy_store.load())
        unified = UnifiedLLMService(shared)
        selected = unified.resolve("text")
        assert all(before[field] == after[field] == getattr(selected, field) for field in ["endpoint", "model", "api_key"])
        assert selected.capabilities == ("text",)

        async def verify():
            async with aiohttp.ClientSession() as session:
                old = await DeepSeekClient(session, before).translate([{"name": "cat", "category": 0}], "zh")
                migrated_result = await DeepSeekClient(session, after).translate([{"name": "cat", "category": 0}], "zh")
            _profile, _envelope, content = await unified.complete_text("Translate cat to Chinese using translations JSON")
            assert old.translations == migrated_result.translations == {"cat": "猫"}
            assert json.loads(content)["translations"][0]["translation"] == "猫"

        asyncio.run(verify())
        assert "fixture-runtime-key" not in path.read_text(encoding="utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize("local_enabled", [False, True])
def test_translation_fallback_requires_explicit_local_enable(tmp_path, local_enabled):
    path = tmp_path / "translation.json"
    legacy = OnlineServiceConfig(path)
    legacy.save({"llm_mode": "local" if local_enabled else "remote"})
    shared = UnifiedConfigStore(path)
    profiles = shared.load()["profiles"]
    profiles.append({"id": "local", "name": "local", "source": "managed-local",
                     "endpoint": "http://127.0.0.1:8080/v1/chat/completions", "model": "local",
                     "capabilities": ["text"], "languages": ["zh"]})
    shared.save({"profiles": profiles})
    manager = TranslationManager(path, store=None)
    section = manager._active_llm_config(legacy.load())
    assert section["endpoint"].startswith("https://")  # Remote always wins, including legacy local mode.
    assert bool(section["_fallbacks"]) is local_enabled


def test_translation_cache_disable_skips_existing_results_failures_and_writes(tmp_path):
    from mikazuki.tag_translation.translation_store import TranslationStore
    server = ThreadingHTTPServer(("127.0.0.1", 0), TextProvider)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        path = tmp_path / "translation.json"
        legacy = OnlineServiceConfig(path)
        legacy.save({"deepseek": {"endpoint": f"http://127.0.0.1:{server.server_port}/v1/chat/completions", "model": "text-model", "api_key": "fixture-runtime-key"}})
        shared = UnifiedConfigStore(path)
        shared.save({"cache": {"translation": False, "caption": True}})
        store = TranslationStore(str(tmp_path / "translations.sqlite3"))
        manager = TranslationManager(path, store)
        config = manager._active_llm_config(legacy.load())
        item = {"name": "cat", "category": 0, "post_count": 0, "origin": "fixture"}
        store.save_results("zh", "llm", manager.profile_revision(config), [item], {"cat": "旧缓存译文"})
        import hashlib
        prompt_hash = hashlib.sha256(config["system_prompt"].encode()).hexdigest()
        store.save_failures("zh", [item], ["cat"], config["model"], prompt_hash)
        async def verify():
            for _ in range(2):
                result = await manager.resolve("zh-CN", [item])
                assert result["cat"]["text"] == "猫"
        asyncio.run(verify())
        assert server.requests == 2
        assert store.get_results("zh", ["cat"], "llm", manager.profile_revision(config))["cat"]["text"] == "旧缓存译文"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
