from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image

from mikazuki.llm.config import UnifiedConfigStore
from mikazuki.llm.service import UnifiedLLMService


class _FakeVisionHandler(BaseHTTPRequestHandler):
    requests: list[dict] = []
    fail_remote = False

    def do_POST(self):
        size = int(self.headers.get("content-length", "0"))
        body = json.loads(self.rfile.read(size) or b"{}")
        self.__class__.requests.append(body)
        if self.__class__.fail_remote and body.get("model") == "remote-vision":
            self.send_response(503)
            self.end_headers()
            return
        response = {
            "choices": [{
                "message": {"content": '{"caption":"一只猫坐在窗边。","language":"zh-CN"}'},
                "finish_reason": "stop",
            }]
        }
        raw = json.dumps(response, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *_args):
        return


def _server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeVisionHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def test_fake_openai_vision_server_data_url_and_remote_first_fallback(tmp_path: Path):
    image_path = tmp_path / "cat.png"
    Image.new("RGB", (16, 12), (220, 180, 160)).save(image_path)
    server = _server()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        store = UnifiedConfigStore(tmp_path / "translation.json")
        store.save({
            "profiles": [
                {
                    "id": "remote",
                    "name": "Remote",
                    "endpoint": base + "/v1/chat/completions",
                    "model": "remote-vision",
                    "source": "remote",
                    "capabilities": ["text", "vision"],
                    "languages": ["zh-CN"],
                },
                {
                    "id": "local",
                    "name": "Local",
                    "endpoint": base + "/v1/chat/completions",
                    "model": "local-vision",
                    "source": "managed-local",
                    "capabilities": ["text", "vision"],
                    "languages": ["zh-CN"],
                },
            ],
        })
        service = UnifiedLLMService(store)
        profile, _envelope, content, _image = asyncio.run(
            service.complete_vision(image_path, "describe {{language}}", language="zh-CN")
        )
        assert profile.id == "remote"
        assert "一只猫" in content
        assert _FakeVisionHandler.requests[-1]["messages"][0]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
        assert str(image_path) not in json.dumps(_FakeVisionHandler.requests[-1], ensure_ascii=False)

        _FakeVisionHandler.fail_remote = True
        store.save({
            "profiles": [
                {
                    "id": "remote",
                    "name": "Remote",
                    "endpoint": base + "/v1/chat/completions",
                    "model": "remote-vision",
                    "source": "remote",
                    "capabilities": ["text", "vision"],
                    "languages": ["zh-CN"],
                },
                {
                    "id": "local",
                    "name": "Local",
                    "endpoint": base + "/v1/chat/completions",
                    "model": "local-vision",
                    "source": "managed-local",
                    "capabilities": ["text", "vision"],
                    "languages": ["zh-CN"],
                },
            ],
        })
        fallback, _envelope, content, _image = asyncio.run(
            service.complete_vision(image_path, "describe {{language}}", language="zh-CN")
        )
        assert fallback.id == "local"
        assert "一只猫" in content
    finally:
        server.shutdown()
