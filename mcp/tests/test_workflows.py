import json

import httpx
import pytest
from mcp.server.fastmcp.exceptions import ToolError

from conftest import patch_backend, run, tool_names, tool_text

from next_trainer_mcp.server import create_server

TASKS = {
    "status": "success",
    "data": {
        "tasks": [
            {"id": "t-old", "status": "FINISHED", "lane": "compute", "returncode": 0,
             "created_at": 1.0, "metadata": {"train_type": "sd-lora"}},
            {"id": "t-run", "status": "RUNNING", "lane": "compute",
             "created_at": 2.0, "metadata": {"train_type": "anima-lora"}},
        ]
    },
}

METRICS = {
    "status": "success",
    "data": {
        "tags": {"loss/average": [{"step": 1, "value": 0.5}, {"step": 2, "value": 0.4}]},
        "progress": {"percent": 50, "step": 2},
    },
}

LOGS = {
    "status": "success",
    "data": {"lines": ["info: boot", "Traceback (most recent call last):", "RuntimeError: boom"], "total": 3, "done": False},
}

PREVIEWS = {"status": "success", "data": {"images": [{"name": "a.png"}, {"name": "b.png"}]}}

PRESETS = {
    "status": "success",
    "data": {
        "presets": [
            {"metadata": {"name": "base-preset", "train_type": "sd-lora"},
             "data": {"model_train_type": "sd-lora", "learning_rate": 1e-4, "output_name": "preset-default"}},
        ]
    },
}


def make_handler(extra=None):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/tasks":
            return httpx.Response(200, json=TASKS)
        if path.endswith("/metrics"):
            return httpx.Response(200, json=METRICS)
        if "/train/log/tail/" in path:
            return httpx.Response(200, json=LOGS)
        if path.endswith("/previews"):
            return httpx.Response(200, json=PREVIEWS)
        if path.endswith("/config"):
            return httpx.Response(200, json={"status": "success", "data": {"config": {"lr": 1e-4}}})
        if path == "/api/presets":
            return httpx.Response(200, json=PRESETS)
        if extra:
            return extra(request)
        if path == "/api/run":
            return httpx.Response(200, json={"status": "success", "data": {"task_id": "from-preset"}})
        return httpx.Response(404, json={"detail": "unexpected"})

    return handler


@pytest.fixture
def mcp(monkeypatch):
    patch_backend(monkeypatch, make_handler())
    return create_server()


def test_workflow_tools_registered(mcp):
    names = tool_names(mcp)
    assert {"get_task_overview", "grep_task_log", "get_task_config", "get_last_task", "submit_from_preset"} <= names
    assert "wait_task" not in names


def test_overview_bundles_status_metrics_logs_previews(mcp):
    data = json.loads(tool_text(run(mcp.call_tool("get_task_overview", {"task_id": "t-run"}))))
    assert data["task"]["status"] == "RUNNING"
    assert data["latest_metrics"]["loss/average"] == {"step": 2, "value": 0.4}
    assert data["progress"]["percent"] == 50
    assert data["log_tail"][-1] == "RuntimeError: boom"
    assert data["preview_count"] == 2


def test_overview_unknown_task(mcp):
    with pytest.raises(ToolError, match="未知任务"):
        run(mcp.call_tool("get_task_overview", {"task_id": "nope"}))


def test_grep_task_log_matches_with_line_numbers(mcp):
    data = json.loads(tool_text(run(mcp.call_tool("grep_task_log", {"task_id": "t-run", "pattern": "error"}))))
    assert data["total_matches"] == 1
    assert data["matches"][0]["line"] == 2
    assert "RuntimeError" in data["matches"][0]["text"]


def test_grep_task_log_case_insensitive(mcp):
    data = json.loads(tool_text(run(mcp.call_tool("grep_task_log", {"task_id": "t-run", "pattern": "traceback"}))))
    assert data["total_matches"] == 1


def test_get_task_config(mcp):
    data = json.loads(tool_text(run(mcp.call_tool("get_task_config", {"task_id": "t-run"}))))
    assert data["config"]["lr"] == 1e-4


def test_get_last_task_picks_most_recent(mcp):
    data = json.loads(tool_text(run(mcp.call_tool("get_last_task", {}))))
    assert data["id"] == "t-run"


def test_get_last_task_falls_back_to_list_order_without_created_at(monkeypatch):
    tasks_no_ts = {
        "status": "success",
        "data": {"tasks": [
            {"id": "restored-old", "status": "FINISHED", "lane": "compute"},
            {"id": "restored-new", "status": "FINISHED", "lane": "compute"},
        ]},
    }
    patch_backend(monkeypatch, lambda req: httpx.Response(200, json=tasks_no_ts))
    mcp = create_server()
    data = json.loads(tool_text(run(mcp.call_tool("get_last_task", {}))))
    assert data["id"] == "restored-new"


def test_submit_from_preset_merges_overrides(monkeypatch):
    seen = {}

    def extra(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"status": "success", "data": {"task_id": "from-preset"}})

    patch_backend(monkeypatch, make_handler(extra=extra))
    mcp = create_server()
    result = run(mcp.call_tool("submit_from_preset", {
        "preset_name": "base-preset",
        "overrides": {"output_name": "override-name"},
        "confirm_queue": True,  # fixture 里有 RUNNING 任务，走排队确认路径
    }))
    assert "from-preset" in tool_text(result)
    body = json.loads(seen["body"])
    assert body["output_name"] == "override-name"
    assert body["learning_rate"] == 1e-4  # preset base kept


def test_submit_from_preset_unknown_name(mcp):
    with pytest.raises(ToolError, match="未找到预设"):
        run(mcp.call_tool("submit_from_preset", {"preset_name": "nope"}))
