"""Verify Caption batch concurrency through the API and real loopback HTTP.

The provider is deliberately synthetic: these tests establish scheduling and
cancellation, not model output quality. No user endpoint or credential is used.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import aiohttp
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from mikazuki.llm.config import UnifiedConfigStore, config_revision
from mikazuki.llm.service import UnifiedLLMService
from mikazuki.tagger import caption_api
from mikazuki.tagger.caption_job import CaptionJobManager
from mikazuki.tagger.caption_store import CaptionJobStore
from mikazuki.tagger.progress import tagger_progress


@pytest.fixture
def http_batch(tmp_path, monkeypatch):
    monkeypatch.setenv("MIKAZUKI_USER_DATA_ROOT", str(tmp_path / "user_data"))
    lock = threading.Lock()
    release = threading.Event()
    reached = threading.Event()
    state = {"active": 0, "maximum": 0, "requests": [], "target": 3}

    class Provider(BaseHTTPRequestHandler):
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            with lock:
                state["requests"].append(payload)
                state["active"] += 1
                state["maximum"] = max(state["maximum"], state["active"])
                if state["active"] >= state["target"]:
                    reached.set()
            try:
                if not release.wait(timeout=10):
                    self.send_error(504)
                    return
                content = json.dumps({"caption": "A colored square on a plain background.", "language": "en"})
                body = json.dumps({"choices": [{"message": {"content": content}, "finish_reason": "stop"}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
            finally:
                with lock:
                    state["active"] -= 1

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    manager = None
    try:
        store = UnifiedConfigStore(tmp_path / "llm.json")
        store.save({"profiles": [{"id": "loopback", "name": "Synthetic HTTP", "model": "synthetic-vision",
                                  "endpoint": f"http://127.0.0.1:{server.server_port}/v1/chat/completions",
                                  "source": "remote", "capabilities": ["vision"], "languages": ["en"]}]})
        profile = store.load()["profiles"][0]
        store.record_verification(profile["id"], config_revision(profile), "vision")

        def sessions(**kwargs):
            return aiohttp.ClientSession(**{**kwargs, "trust_env": False})

        service = UnifiedLLMService(store, session_factory=sessions)
        manager = CaptionJobManager(service, job_store=CaptionJobStore(tmp_path / "jobs.sqlite3"))
        monkeypatch.setattr(caption_api, "llm_service", service)
        monkeypatch.setattr(caption_api, "caption_job_manager", manager)
        app = FastAPI()
        app.include_router(caption_api.router, prefix="/api")
        images = tmp_path / "images"
        images.mkdir()
        for index in range(6):
            Image.new("RGB", (24, 24), (30 + index * 30, 80, 100)).save(images / f"{index}.png")
        tagger_progress.reset_idle()
        yield TestClient(app), manager, images, state, reached, release
    finally:
        release.set()
        if manager and manager._thread:
            manager.cancel()
            manager._thread.join(timeout=5)
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        tagger_progress.reset_idle()


@pytest.mark.parametrize("requested", [None, 1, 5])
def test_batch_api_honors_concurrency_through_real_http(http_batch, requested):
    client, manager, images, state, reached, release = http_batch
    expected = 3 if requested is None else requested
    state["target"] = expected
    payload = {"path": str(images), "language": "en", "use_cache": False}
    if requested is not None:
        payload["concurrency"] = requested
    response = client.post("/api/tagger/jobs", json=payload)
    try:
        assert response.status_code == 200, response.text
        assert reached.wait(timeout=5), "The provider did not observe the requested concurrent requests"
        assert state["maximum"] == expected
        assert len(state["requests"]) == expected
    finally:
        release.set()
    manager._thread.join(timeout=10)
    assert not manager._thread.is_alive()
    status = client.get("/api/tagger/jobs").json()["data"]
    assert status["phase"] == "done", status
    assert status["snapshot"]["concurrency"] == expected
    assert status["succeeded"] == status["current"] == 6
    assert status["failed"] == 0
    assert state["maximum"] <= expected
    assert len(state["requests"]) == 6
    assert [item["index"] for item in status["report"]["items"]] == list(range(6))
    for path in images.glob("*.png"):
        assert path.with_suffix(".txt").read_text(encoding="utf-8").strip() == "A colored square on a plain background."
    for body in state["requests"]:
        assert "concurrency" not in body  # Scheduler setting is not an LLM generation parameter.
        serialized = json.dumps(body)
        assert str(images) not in serialized
        assert "data:image/jpeg;base64," in serialized


def test_api_cancellation_aborts_all_inflight_http_without_late_writes(http_batch):
    client, manager, images, state, reached, release = http_batch
    response = client.post("/api/tagger/jobs", json={"path": str(images), "language": "en", "use_cache": False})
    assert response.status_code == 200, response.text
    assert reached.wait(timeout=5)
    assert len(state["requests"]) == 3
    cancelled = client.post("/api/tagger/jobs/cancel")
    assert cancelled.status_code == 200
    manager._thread.join(timeout=5)
    assert not manager._thread.is_alive()
    status = manager.status()
    assert status["phase"] == "cancelled"
    assert status["cancelled"] == 6
    assert status["succeeded"] == status["failed"] == 0
    assert not list(images.glob("*.txt"))
    release.set()
    assert len(state["requests"]) == 3  # Queued images never reach the provider.
    assert not list(images.glob("*.txt"))
