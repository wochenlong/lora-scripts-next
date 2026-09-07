import asyncio

import httpx
import pytest
from mcp.server.fastmcp.exceptions import ToolError

from next_trainer_mcp.server import create_server

from conftest import patch_backend, run, tool_names, tool_text


class TestDatasetTools:
    def test_dataset_tools_registered(self, monkeypatch):
        patch_backend(monkeypatch, lambda req: httpx.Response(200, json={"status": "success", "data": {}}))
        names = tool_names(create_server())
        assert {"scan_dataset", "interrogate", "get_tagger_status", "browse_server_path", "list_files"} <= names

    def test_dataset_tools_hidden_in_read_only(self, monkeypatch):
        patch_backend(monkeypatch, lambda req: httpx.Response(200, json={"status": "success", "data": {}}))
        names = tool_names(create_server(read_only=True))
        assert "scan_dataset" not in names
        assert "interrogate" not in names

    def test_scan_posts_path(self, monkeypatch):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = request.content.decode()
            return httpx.Response(200, json={"status": "success", "data": {"images": 3}})

        patch_backend(monkeypatch, handler)
        mcp = create_server()
        result = run(mcp.call_tool("scan_dataset", {"path": "/data/train"}))
        assert '"path": "/data/train"' in seen["body"]
        assert '"images": 3' in tool_text(result)

    def test_interrogate_posts_model_and_threshold(self, monkeypatch):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["body"] = request.content.decode()
            return httpx.Response(200, json={"status": "success", "message": "打标任务已提交"})

        patch_backend(monkeypatch, handler)
        mcp = create_server()
        run(mcp.call_tool("interrogate", {"path": "/data/a.png", "threshold": 0.5}))
        assert '"threshold": 0.5' in seen["body"]
        assert "wd14-convnextv2-v2" in seen["body"]

    def test_browse_server_path_params(self, monkeypatch):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["query"] = request.url.query.decode()
            return httpx.Response(200, json={"status": "success", "data": {"entries": []}})

        patch_backend(monkeypatch, handler)
        mcp = create_server()
        run(mcp.call_tool("browse_server_path", {"path": "/data", "mode": "file", "name_filter": "png"}))
        assert "path=%2Fdata" in seen["query"] or "path=/data" in seen["query"]
        assert "mode=file" in seen["query"]


class TestDocsTools:
    def test_docs_tools_registered(self, monkeypatch):
        patch_backend(monkeypatch, lambda req: httpx.Response(200, json={"status": "success", "data": {}}))
        names = tool_names(create_server())
        assert {"list_docs", "get_doc", "get_training_cookbook"} <= names

    def test_docs_available_in_read_only(self, monkeypatch):
        patch_backend(monkeypatch, lambda req: httpx.Response(200, json={"status": "success", "data": {}}))
        names = tool_names(create_server(read_only=True))
        assert {"list_docs", "get_doc", "get_training_cookbook"} <= names

    def test_list_docs_and_get_doc_roundtrip(self, monkeypatch):
        patch_backend(monkeypatch, lambda req: httpx.Response(200, json={"status": "success", "data": {}}))
        mcp = create_server()
        listing = run(mcp.call_tool("list_docs", {}))
        assert "cli-args.md" in tool_text(listing)
        doc = run(mcp.call_tool("get_doc", {"name": "cli-args.md"}))
        assert len(tool_text(doc)) > 100

    def test_get_doc_unknown_name_lists_available(self, monkeypatch):
        patch_backend(monkeypatch, lambda req: httpx.Response(200, json={"status": "success", "data": {}}))
        mcp = create_server()
        with pytest.raises(ToolError, match="未知文档"):
            run(mcp.call_tool("get_doc", {"name": "nope.md"}))

    def test_cookbook_contains_workflow(self, monkeypatch):
        patch_backend(monkeypatch, lambda req: httpx.Response(200, json={"status": "success", "data": {}}))
        mcp = create_server()
        result = run(mcp.call_tool("get_training_cookbook", {}))
        assert "validate_config" in tool_text(result)

    def test_docs_resources(self, monkeypatch):
        patch_backend(monkeypatch, lambda req: httpx.Response(200, json={"status": "success", "data": {}}))
        mcp = create_server()

        async def read_index():
            return await mcp.read_resource("docs://index")

        content = run(read_index())
        text = content[0].content if hasattr(content[0], "content") else str(content[0])
        assert "cli-args.md" in text
