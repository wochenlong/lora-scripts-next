import asyncio

import httpx
import pytest

from next_trainer_mcp import server as server_module
from next_trainer_mcp.server import create_server


def run(coro):
    return asyncio.run(coro)


def patch_backend(monkeypatch, handler):
    """Swap the BackendClient constructor for a MockTransport-backed one."""
    from next_trainer_mcp.backend import BackendClient

    def factory(base_url, timeout=10.0):
        backend = BackendClient(base_url, timeout=timeout)
        backend._client = httpx.Client(
            base_url=base_url,
            transport=httpx.MockTransport(handler),
        )
        return backend

    monkeypatch.setattr(server_module, "BackendClient", factory)


def tool_names(mcp) -> set[str]:
    return {t.name for t in run(mcp.list_tools())}


class TestDiscoveryTools:
    def test_discovery_tools_registered(self, monkeypatch):
        patch_backend(monkeypatch, lambda req: httpx.Response(200, json={"status": "success", "data": {}}))
        mcp = create_server()
        names = tool_names(mcp)
        assert {"get_schemas", "list_presets", "list_gpus", "get_version", "list_saved_params"} <= names

    def test_get_version_calls_backend(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/version"
            return httpx.Response(200, json={"status": "success", "data": {"version": "9.9.9"}})

        patch_backend(monkeypatch, handler)
        mcp = create_server()
        result = run(mcp.call_tool("get_version", {}))
        assert "9.9.9" in result[0].text

    def test_backend_fail_surfaces_as_tool_error(self, monkeypatch):
        from mcp.server.fastmcp.exceptions import ToolError

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"status": "fail", "message": "boom"})

        patch_backend(monkeypatch, handler)
        mcp = create_server()
        with pytest.raises(ToolError, match="boom"):
            run(mcp.call_tool("get_version", {}))


class TestReadOnlyMode:
    def test_read_only_excludes_training_tools(self, monkeypatch):
        patch_backend(monkeypatch, lambda req: httpx.Response(200, json={"status": "success", "data": {}}))
        mcp = create_server(read_only=True)
        names = tool_names(mcp)
        assert "submit_training" not in names
        assert "terminate_task" not in names
        assert "get_schemas" in names
