import base64
import io
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import aiohttp
import pytest
from PIL import Image

from mikazuki.llm.config import UnifiedConfigStore
from mikazuki.llm.service import UnifiedLLMService
from mikazuki.tagger.caption_job import CaptionJobManager
from mikazuki.tagger.caption_store import CaptionJobStore


@pytest.fixture
def provider():
    state = {"requests": [], "green_failure": True}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["content-length"])))
            state["requests"].append(body)
            mode = body["model"]
            status = 200
            content = '{"caption":"一个彩色方块。","language":"zh-CN"}'
            if mode == "rate-once" and len(state["requests"]) == 1:
                status = 429
            elif mode == "auth-failed":
                status = 401
            elif mode == "invalid-json":
                content = "not valid JSON (synthetic private provider text)"
            elif mode == "timeout":
                time.sleep(.3)
            elif mode == "partial":
                url = body["messages"][0]["content"][1]["image_url"]["url"]
                image = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1])))
                red, green, _blue = image.getpixel((0, 0))
                if green > red and state["green_failure"]:
                    status = 503
            response = json.dumps({"choices": [{"message": {"content": content}, "finish_reason": "stop"}]}).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            try:
                self.wfile.write(response)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}/v1/chat/completions", state
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def manager_for(tmp_path, endpoint, model):
    store = UnifiedConfigStore(tmp_path / "translation.json")
    store.save({"profiles": [{"id": "remote", "name": "remote", "model": model, "endpoint": endpoint,
                               "source": "remote", "capabilities": ["text", "vision"], "languages": ["zh-CN"],
                               "api_key": "fixture-runtime-key"}]})

    def sessions(**kwargs):
        return aiohttp.ClientSession(**{**kwargs, "timeout": aiohttp.ClientTimeout(total=.1 if model == "timeout" else 5), "trust_env": False})

    return CaptionJobManager(UnifiedLLMService(store, session_factory=sessions),
                             job_store=CaptionJobStore(tmp_path / "translations.sqlite3"))


@pytest.mark.parametrize("model,success,code,calls", [
    ("rate-once", 1, None, 2), ("auth-failed", 0, "llm_auth_failed", 1),
    ("invalid-json", 0, "llm_invalid_response", 2), ("timeout", 0, "llm_unreachable", 2),
])
def test_real_http_fake_error_matrix(tmp_path, provider, model, success, code, calls):
    endpoint, state = provider
    image = tmp_path / "private-image-name.png"
    Image.new("RGB", (32, 32), "red").save(image)
    manager = manager_for(tmp_path, endpoint, model)
    manager.start({"path": str(tmp_path), "mode": "natural", "prompt": "Describe {{image_name}} in {{language}}"})
    manager._thread.join(timeout=10)
    assert not manager._thread.is_alive()
    status = manager.status()
    assert status["succeeded"] == success
    if code:
        assert status["errors"][0]["code"] == code
        assert not image.with_suffix(".txt").exists()
    assert len(state["requests"]) == calls
    assert "synthetic private provider text" not in json.dumps(status)
    assert "fixture-runtime-key" not in json.dumps(status)
    for request in state["requests"]:
        serialized = json.dumps(request)
        assert str(tmp_path) not in serialized
        assert image.name not in serialized
        assert request["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_partial_http_failure_and_restart_retry_preserve_completed_file(tmp_path, provider):
    endpoint, state = provider
    Image.new("RGB", (32, 32), "red").save(tmp_path / "a.png")
    Image.new("RGB", (32, 32), "green").save(tmp_path / "b.png")
    manager = manager_for(tmp_path, endpoint, "partial")
    manager.start({"path": str(tmp_path), "mode": "natural"})
    manager._thread.join(timeout=10)
    assert manager.status()["succeeded"] == manager.status()["failed"] == 1
    completed = (tmp_path / "a.txt").read_bytes()
    state["green_failure"] = False
    restarted = manager_for(tmp_path, endpoint, "partial")
    restarted.retry_failed()
    restarted._thread.join(timeout=5)
    assert not restarted._thread.is_alive()
    assert restarted.status()["succeeded"] == 1
    assert (tmp_path / "a.txt").read_bytes() == completed
    assert (tmp_path / "b.txt").is_file()
    assert len(state["requests"]) == 4


@pytest.mark.parametrize("layout,expected", [
    ("tags_then_caption", "cat, red hair\n\n一个彩色方块。\n"),
    ("caption_then_tags", "一个彩色方块。\n\ncat, red hair\n"),
    ("caption_only", "一个彩色方块。\n"),
    ("tags_only", "cat, red hair\n"),
])
def test_combined_job_uses_separate_tag_output_and_real_http_caption(tmp_path, provider, monkeypatch, layout, expected):
    endpoint, state = provider
    Image.new("RGB", (32, 32), "red").save(tmp_path / "a.png")
    manager = manager_for(tmp_path, endpoint, "combined")
    monkeypatch.setattr(manager, "_prepare_tag_model", lambda request: None)
    monkeypatch.setattr(manager, "_generate_tags", lambda path, request: ["cat", "red hair"])
    manager.start({"path": str(tmp_path), "mode": "combined", "layout": layout})
    manager._thread.join(timeout=5)
    assert manager.status()["succeeded"] == 1
    assert (tmp_path / "a.txt").read_text(encoding="utf-8") == expected
    assert len(state["requests"]) == 1


def test_remote_failure_explicit_fallback_records_actual_local_profile(tmp_path, provider):
    endpoint, state = provider
    Image.new("RGB", (32, 32), "red").save(tmp_path / "a.png")
    manager = manager_for(tmp_path, endpoint, "auth-failed")
    store = manager.service.config_store
    config = store.load()
    config["profiles"].append({"id": "local", "name": "local", "model": "fallback-local", "endpoint": endpoint,
                               "source": "managed-local", "capabilities": ["text", "vision"], "languages": ["zh-CN"], "ready": True})
    store.save(config)
    manager.start({"path": str(tmp_path), "mode": "natural", "allow_local_fallback": True, "profile_id": "remote"})
    manager._thread.join(timeout=5)
    assert manager.status()["succeeded"] == 1
    assert [request["model"] for request in state["requests"]] == ["auth-failed", "fallback-local"]
    assert manager.status()["report"]["items"][0]["profile_id"] == "local"
    assert manager.status()["report"]["items"][0]["profile_revision"]
