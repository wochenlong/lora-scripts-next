"""Composite workflow tools: one call instead of many round-trips.

These bundle the sequences agents repeatedly hand-roll (status + metrics +
log tail + previews; log grepping; latest-task lookup).

No blocking waits here by design: MCP is request-response and clients time
out long before training finishes, so a sleeping tool only wedges the
session. Poll with get_task_status / get_task_overview between turns.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..backend import BackendClient, BackendError
from .training import _compact_task, _fetch_tasks

LOG_TAIL_CAP = 2000


def register(mcp: FastMCP, backend: BackendClient) -> None:

    @mcp.tool()
    def get_task_overview(task_id: str, log_lines: int = 30) -> dict:
        """一次拿全任务概览：状态 + 最新 loss + 进度 + 日志尾部 + 预览图数量。

        参数：
        - log_lines: 日志尾部行数，默认 30（排错时加大，或用 grep_task_log 搜关键词）。
        轮询间隔建议 >= 30 秒。
        """
        overview: dict = {}

        for t in _fetch_tasks(backend):
            if isinstance(t, dict) and t.get("id") == task_id:
                overview["task"] = _compact_task(t)
                break
        if "task" not in overview:
            raise BackendError(f"未知任务: {task_id}（用 list_tasks 看现有任务）")

        try:
            metrics = backend.request("GET", f"/api/tasks/{task_id}/metrics")
            tags = metrics.get("tags") or {}
            overview["progress"] = metrics.get("progress")
            overview["latest_metrics"] = {
                k: v[-1] for k, v in tags.items() if isinstance(v, list) and v
            }
        except BackendError as exc:
            overview["metrics_error"] = str(exc)

        tail = backend.request(
            "GET", f"/api/train/log/tail/{task_id}",
            params={"limit": max(1, min(int(log_lines), LOG_TAIL_CAP))},
        )
        overview["log_tail"] = tail.get("lines", [])
        overview["log_done"] = tail.get("done")

        try:
            previews = backend.request("GET", f"/api/tasks/{task_id}/previews")
            overview["preview_count"] = len(previews.get("images") or [])
        except BackendError:
            overview["preview_count"] = 0

        return overview

    @mcp.tool()
    def grep_task_log(task_id: str, pattern: str, limit: int = 2000, max_matches: int = 50) -> dict:
        """按关键词搜训练日志（大小写不敏感），返回匹配行及行号。

        参数：
        - pattern: 搜索子串，如 "Traceback" / "bfloat16" / "error"
        - limit: 向后端要的日志行数上限（<=2000），默认 2000 即全量快照
        - max_matches: 最多返回的匹配条数，默认 50
        """
        tail = backend.request(
            "GET", f"/api/train/log/tail/{task_id}",
            params={"limit": max(1, min(int(limit), LOG_TAIL_CAP))},
        )
        lines = tail.get("lines") or []
        needle = pattern.lower()
        matches = [
            {"line": i, "text": text}
            for i, text in enumerate(lines)
            if needle in text.lower()
        ]
        return {
            "matches": matches[: max(1, int(max_matches))],
            "total_matches": len(matches),
            "scanned_lines": len(lines),
            "done": tail.get("done"),
        }

    @mcp.tool()
    def get_task_config(task_id: str) -> dict:
        """获取任务的完整训练配置（autosave 内容），复现/对照参数用。"""
        return backend.request("GET", f"/api/tasks/{task_id}/config")

    @mcp.tool()
    def get_last_task() -> dict:
        """获取最近创建的任务（紧凑信息）。

        排序依据 created_at；app 重启后恢复的历史任务没有该字段，
        此时回退为任务列表顺序的最后一个（持久化顺序即时间顺序）。
        """

        def created(t: dict) -> float:
            try:
                return float(t.get("created_at") or 0)
            except (TypeError, ValueError):
                return 0.0

        tasks = [t for t in _fetch_tasks(backend) if isinstance(t, dict)]
        if not tasks:
            raise BackendError("当前没有任何任务")
        if any(created(t) > 0 for t in tasks):
             return _compact_task(max(tasks, key=created))
        return _compact_task(tasks[-1])
