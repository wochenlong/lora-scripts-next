import asyncio

import httpx
import pytest
from mcp.server.fastmcp.exceptions import ToolError

from next_trainer_mcp import server as server_module
from next_trainer_mcp.server import create_server


def run(coro):
    return asyncio.run(coro)


def patch_backend(monkeypatch, handler):
    from next_trainer_mcp.backend import BackendClient

    def factory(base_url, timeout=10.0):
        backend = BackendClient(base_url, timeout=timeout)
        backend._client = httpx.Client(
            base_url=base_url,
            transport=httpx.MockTransport(handler),
        )
        return backend

    monkeypatch.setattr(server_module, "BackendClient", factory)


def tool_names(mcp):
    return {t.name for t in run(mcp.list_tools())}


IDLE_TASKS = {"status": "success", "data": {"tasks": []}}
BUSY_TASKS = {"status": "success", "data": {"tasks": [{"id": "t1", "status": "RUNNING", "detail": {"name": "job-a"}}]}}


class TestToolRegistration:
    def test_training_and_monitor_tools_registered(self, monkeypatch):
        patch_backend(monkeypatch, lambda req: httpx.Response(200, json={"status": "success", "data": {}}))
        names = tool_names(create_server())
        assert {
            "validate_config", "submit_training", "list_tasks",
            "terminate_task", "resume_task", "retry_task",
            "get_task_metrics", "get_task_log_tail", "list_task_previews",
        } <= names


class TestValidateConfig:
    def test_posts_page_train_type_and_config(self, monkeypatch):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/config/validate-import":
                seen["body"] = request.content.decode()
                return httpx.Response(200, json={"status": "success", "data": {"errors": []}})
            return httpx.Response(404, json={"detail": "unexpected"})

        patch_backend(monkeypatch, handler)
        mcp = create_server()
        result = run(mcp.call_tool("validate_config", {"page_train_type": "sd-lora", "config": {"a": 1}}))
        assert '"errors": []' in result[0].text
        assert '"page_train_type": "sd-lora"' in seen["body"]


class TestSubmitTrainingGate:
    def _handler(self, tasks_payload, seen):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/tasks":
                return httpx.Response(200, json=tasks_payload)
            if request.url.path == "/api/run":
                seen["submitted"] = True
                return httpx.Response(200, json={"status": "success", "data": {"task_id": "new-1"}})
            return httpx.Response(404, json={"detail": "unexpected"})
        return handler

    def test_submit_when_idle(self, monkeypatch):
        seen = {}
        patch_backend(monkeypatch, self._handler(IDLE_TASKS, seen))
        mcp = create_server()
        result = run(mcp.call_tool("submit_training", {"config": {"model_train_type": "sd-lora"}}))
        assert seen.get("submitted") is True
        assert "new-1" in result[0].text

    def test_submit_blocked_when_busy_without_confirm(self, monkeypatch):
        seen = {}
        patch_backend(monkeypatch, self._handler(BUSY_TASKS, seen))
        mcp = create_server()
        with pytest.raises(ToolError, match="confirm_queue"):
            run(mcp.call_tool("submit_training", {"config": {"model_train_type": "sd-lora"}}))
        assert "submitted" not in seen

    def test_submit_passes_when_busy_with_confirm(self, monkeypatch):
        seen = {}
        patch_backend(monkeypatch, self._handler(BUSY_TASKS, seen))
        mcp = create_server()
        result = run(mcp.call_tool("submit_training", {"config": {"model_train_type": "sd-lora"}, "confirm_queue": True}))
        assert seen.get("submitted") is True

    def test_submit_rejects_missing_train_type(self, monkeypatch):
        seen = {}
        patch_backend(monkeypatch, self._handler(IDLE_TASKS, seen))
        mcp = create_server()
        with pytest.raises(ToolError, match="model_train_type"):
            run(mcp.call_tool("submit_training", {"config": {"learning_rate": 1e-4}}))
        assert "submitted" not in seen

    def test_non_compute_lane_running_task_does_not_block(self, monkeypatch):
        tagger_busy = {"status": "success", "data": {"tasks": [{"id": "tag-1", "status": "RUNNING", "lane": "tagger"}]}}
        seen = {}
        patch_backend(monkeypatch, self._handler(tagger_busy, seen))
        mcp = create_server()
        run(mcp.call_tool("submit_training", {"config": {"model_train_type": "sd-lora"}}))
        assert seen.get("submitted") is True


class TestMonitorTools:
    def test_log_tail_clamps_limit_and_passes_param(self, monkeypatch):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["query"] = request.url.query.decode()
            return httpx.Response(200, json={"status": "success", "data": {"lines": ["a"], "total": 1, "done": False}})

        patch_backend(monkeypatch, handler)
        mcp = create_server()
        run(mcp.call_tool("get_task_log_tail", {"task_id": "t1", "limit": 99999}))
        assert seen["query"] == "limit=2000"

    def test_metrics_calls_right_path(self, monkeypatch):
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/tasks/t1/metrics"
            return httpx.Response(200, json={"status": "success", "data": {"tags": {}, "progress": {}}})

        patch_backend(monkeypatch, handler)
        mcp = create_server()
        result = run(mcp.call_tool("get_task_metrics", {"task_id": "t1"}))
        assert "tags" in result[0].text
