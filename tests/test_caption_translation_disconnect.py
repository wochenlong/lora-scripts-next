"""Real TCP disconnects through the same middleware style as the GUI app."""
import asyncio
import http.client
import json
import socket
import threading
import time

import pytest
import uvicorn
from fastapi import FastAPI

from mikazuki.llm import api
from mikazuki.llm.cache import CaptionCache
from mikazuki.llm.config import UnifiedConfigStore, config_revision
from mikazuki.llm.service import UnifiedLLMService


@pytest.mark.parametrize("late_failure", [False, True])
def test_tcp_disconnect_cancels_provider_behind_middleware(tmp_path, monkeypatch, late_failure):
    store = UnifiedConfigStore(tmp_path / "config.json")
    store.save({"profiles": [{"id": "text", "source": "remote", "model": "fixture",
                             "endpoint": "http://127.0.0.1:9/v1/chat/completions",
                             "capabilities": ["text"], "languages": ["zh-CN"]}]})
    profile = store.load()["profiles"][0]
    store.record_verification("text", config_revision(profile), "text")
    cache = CaptionCache(tmp_path / "cache.sqlite3")
    monkeypatch.setattr(api, "llm_service", UnifiedLLMService(store))
    monkeypatch.setattr(api, "caption_cache", cache)
    started, cancelled, finished, release = (threading.Event() for _ in range(4))

    async def request(*_args):
        started.set()
        try:
            while not release.is_set():
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            cancelled.set()
            # A provider's cancellation cleanup may return or raise late.
            await asyncio.sleep(0.05)
            if late_failure:
                raise RuntimeError("late provider failure")
        finally:
            finished.set()
        return {"choices": [{"finish_reason": "stop"}]}, '{"translation":"一只猫。","language":"zh-CN"}'

    monkeypatch.setattr(UnifiedLLMService, "_request", request)
    app = FastAPI()
    app.include_router(api.router, prefix="/api")
    for _ in range(3):
        @app.middleware("http")
        async def passthrough(request, call_next):
            return await call_next(request)

    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="off"))
    thread = threading.Thread(target=lambda: server.run(sockets=[listener]), daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", listener.getsockname()[1], timeout=3)
    try:
        end = time.monotonic() + 3
        while not server.started and time.monotonic() < end:
            time.sleep(0.01)
        assert server.started
        connection.request("POST", "/api/llm/caption-translation", json.dumps({"text": "A cat."}),
                           {"Content-Type": "application/json"})
        assert started.wait(3)
        connection.close()
        assert cancelled.wait(1), "TCP disconnect did not reach the provider through middleware"
        assert finished.wait(1)
        assert cache.translation_count() == 0
    finally:
        connection.close()
        release.set()
        server.should_exit = True
        thread.join(timeout=3)
        listener.close()
    assert not thread.is_alive()
