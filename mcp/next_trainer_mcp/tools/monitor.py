"""Monitoring tools: snapshot-style polling, no SSE."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from ..backend import BackendClient


def _downsample(points: list, max_points: int) -> list:
    """Even-stride downsampling; always keeps the latest point."""
    if max_points <= 0 or len(points) <= max_points:
        return points
    stride = len(points) / max_points
    picked = [points[int(i * stride)] for i in range(max_points - 1)]
    picked.append(points[-1])
    return picked


def register(mcp: FastMCP, backend: BackendClient) -> None:

    @mcp.tool()
    def get_task_metrics(task_id: str, max_points: int = 50) -> dict:
        """获取任务 loss 曲线与训练进度（后端解析 TB event 文件）。

        参数：
        - max_points: 每条曲线最多返回的点数（等距降采样，必含最新点），默认 50。
          只看当前状态时用 1（返回最新值 + progress）。
        返回 {"tags": {...loss 标量...}, "progress": {...}}。轮询间隔建议 >= 30 秒。
        """
        data = backend.request("GET", f"/api/tasks/{task_id}/metrics")
        tags = data.get("tags") if isinstance(data, dict) else None
        if isinstance(tags, dict):
            data["tags"] = {
                k: _downsample(v, max_points) if isinstance(v, list) else v
                for k, v in tags.items()
            }
        return data

    @mcp.tool()
    def get_task_log_tail(task_id: str, limit: int = 200) -> dict:
        """获取训练日志尾部快照。

        参数：
        - limit: 行数，默认 200，上限 2000。用于排错时逐步加大。
        返回 {"lines": [...], "total": 总行数, "done": 是否结束}。
        """
        limit = max(1, min(int(limit), 2000))
        return backend.request("GET", f"/api/train/log/tail/{task_id}", params={"limit": limit})

    @mcp.tool()
    def list_task_previews(task_id: str) -> dict:
        """列出任务预览图清单（只返回文件名列表，不取图片二进制）。"""
        return backend.request("GET", f"/api/tasks/{task_id}/previews")
