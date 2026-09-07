"""End-to-end smoke: real streamable-http transport + real MCP client.

The backend is still an httpx MockTransport (no GPU, no real training app),
but the MCP wire protocol runs for real over a local uvicorn instance.
"""

import asyncio
import socket
import threading
import time

import httpx
import pytest
import uvicorn
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from conftest import patch_backend

from next_trainer_mcp.server import create_server


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _backend_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/api/version":
        return httpx.Response(200, json={"status": "success", "data": {"version": "9.9.9-smoke"}})
    if request.url.path == "/api/tasks":
        return httpx.Response(200, json={"status": "success", "data": {"tasks": []}})
    return httpx.Response(404, json={"detail": "not found"})


def test_streamable_http_smoke(monkeypatch):
    patch_backend(monkeypatch, _backend_handler)
    mcp = create_server()
    port = _free_port()

    config = uvicorn.Config(
        mcp.streamable_http_app(),
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)
    assert server.started, "sidecar http server failed to start"

    async def client_flow():
        async with streamable_http_client(f"http://127.0.0.1:{port}/mcp/") as (read, write, _):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                assert "训练管理器" in (init.instructions or "")
                tools = await session.list_tools()
                names = {t.name for t in tools.tools}
                assert "get_version" in names
                assert "submit_training" in names
                result = await session.call_tool("get_version", {})
                assert "9.9.9-smoke" in result.content[0].text
                resources = await session.list_resources()
                assert any(str(r.uri).startswith("docs://") for r in resources.resources)

    try:
        asyncio.run(client_flow())
    finally:
        server.should_exit = True
        thread.join(timeout=10)
