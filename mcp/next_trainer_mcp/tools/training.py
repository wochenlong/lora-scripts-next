"""Training control tools: validate, submit, task lifecycle.

Dangerous tools (submit_training / terminate_task / resume_task /
retry_task) carry explicit confirmation wording in their descriptions;
enforcement relies on the MCP client's approval mechanism plus the
running-task gate inside submit_training.
"""

from __future__ import annotations

from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from ..backend import BackendClient, BackendError

BUSY_STATUSES = {"RUNNING", "QUEUED"}


def _busy_tasks(backend: BackendClient) -> list[dict]:
    """Compute-lane tasks that occupy (or will occupy) the GPU.

    Tagger/install tasks live on other lanes and must not block submission.
    """
    data = backend.request("GET", "/api/tasks")
    tasks = data.get("tasks") if isinstance(data, dict) else None
    if not isinstance(tasks, list):
        return []
    return [
        t
        for t in tasks
        if isinstance(t, dict)
        and t.get("status") in BUSY_STATUSES
        and t.get("lane", "compute") == "compute"
    ]


def register(mcp: FastMCP, backend: BackendClient) -> None:

    @mcp.tool()
    def validate_config(page_train_type: str, config: dict) -> dict:
        """校验训练配置（提交前必走）。

        参数：
        - page_train_type: 训练页类型，如 "sd-lora" / "sdxl-lora" / "anima-lora"（见 get_schemas）
        - config: 完整训练配置字典

        返回校验结果（错误/警告列表）。有错误时修正后重新校验，不要直接提交。
        """
        return backend.request(
            "POST",
            "/api/config/validate-import",
            json_body={"page_train_type": page_train_type, "config": config},
        )

    @mcp.tool()
    def submit_training(config: dict, confirm_queue: bool = False) -> dict:
        """提交训练任务。⚠️ 需要用户确认：会启动训练进程并占用 GPU。

        参数：
        - config: 完整训练配置字典，必须包含 model_train_type（如 "sd-lora"），
          GPU 选择放在 config["gpu_ids"]。务必先经 validate_config 校验通过。
        - confirm_queue: 当已有任务在跑/排队时，设为 true 表示用户已确认排队意图。

        已有运行中/排队任务且未 confirm_queue 时，本工具拒绝提交并返回说明。
        """
        if not isinstance(config, dict) or not config.get("model_train_type"):
            raise BackendError("config 必须是包含 model_train_type 的字典；先用 get_schemas 查字段、validate_config 校验")

        busy = _busy_tasks(backend)
        if busy and not confirm_queue:
            summary = [
                {"id": t.get("id"), "status": t.get("status"), "metadata": t.get("metadata")}
                for t in busy
            ]
            raise BackendError(
                f"已有 {len(busy)} 个任务在运行/排队: {summary}。"
                "请向用户确认排队意图后，以 confirm_queue=true 重新调用。"
            )

        return backend.request("POST", "/api/run", json_body=config)

    @mcp.tool()
    def list_tasks() -> dict:
        """列出全部训练任务（含状态 RUNNING/QUEUED/FINISHED/FAILED/TERMINATED 与 metadata）。"""
        return backend.request("GET", "/api/tasks")

    @mcp.tool()
    def terminate_task(task_id: str) -> dict:
        """终止训练任务。⚠️ 需要用户确认：会杀掉训练子进程，未保存的进度丢失。"""
        return backend.request("GET", f"/api/tasks/terminate/{task_id}")

    @mcp.tool()
    def resume_task(task_id: str) -> dict:
        """放行一个待确认的排队任务（恢复运行）。⚠️ 会开始占用 GPU，需用户确认。"""
        return backend.request("GET", f"/api/tasks/resume/{task_id}")

    @mcp.tool()
    def retry_task(task_id: str) -> dict:
        """重跑一个已结束（完成/失败/终止）的训练任务。⚠️ 会开始占用 GPU，需用户确认。

        返回新任务的 task_id。
        """
        return backend.request("GET", f"/api/tasks/retry/{task_id}")
