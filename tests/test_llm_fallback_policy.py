from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from PIL import Image

from mikazuki.llm.config import UnifiedConfigStore, config_revision
from mikazuki.llm.http import LLMRequestError
from mikazuki.llm.service import UnifiedLLMService


@pytest.mark.parametrize("capability", ["text", "vision"])
@pytest.mark.parametrize("shared_enabled", [False, True])
@pytest.mark.parametrize("explicit", [None, False, True])
def test_real_http_503_respects_explicit_and_inherited_fallback(
    tmp_path, capability, shared_enabled, explicit,
):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(payload["model"])
            if payload["model"] == "remote":
                self.send_response(503)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = json.dumps({"choices": [{
                "message": {"content": '{"caption":"A cat.","language":"en"}'},
                "finish_reason": "stop",
            }]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        endpoint = f"http://127.0.0.1:{server.server_port}/v1/chat/completions"
        store = UnifiedConfigStore(tmp_path / "config.json")
        store.save({"profiles": [
            {"id": "remote", "endpoint": endpoint, "model": "remote", "source": "remote",
             "capabilities": ["text", "vision"], "languages": ["en"]},
            {"id": "local", "endpoint": endpoint, "model": "local", "source": "managed-local",
             "capabilities": ["text", "vision"], "languages": ["en"]},
        ], "local_fallback_enabled": shared_enabled,
            "routes": {"caption": "remote", "translation": "remote"}})
        for profile in store.load()["profiles"]:
            for supported in ("text", "vision"):
                store.record_verification(profile["id"], config_revision(profile), supported)
        service = UnifiedLLMService(store)
        options = {"language": "en"}
        if explicit is not None:
            options["allow_local_fallback"] = explicit
        if capability == "vision":
            image = tmp_path / "cat.png"
            Image.new("RGB", (16, 16), "white").save(image)
            operation = service.complete_vision(image, "Describe the image.", **options)
        else:
            operation = service.complete_text("Describe a cat.", **options)
        allowed = shared_enabled if explicit is None else explicit
        if allowed:
            result = asyncio.run(operation)
            assert result[0].id == "local"
            assert requests == ["remote", "remote", "local"]
        else:
            with pytest.raises(LLMRequestError) as error:
                asyncio.run(operation)
            assert error.value.code == "llm_request_failed"
            assert requests == ["remote", "remote"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
