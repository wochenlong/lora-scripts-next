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
TERMINAL_STATUSES = {"FINISHED", "FAILED", "TERMINATED"}

_TASK_KEEP_FIELDS = ("id", "status", "lane", "returncode", "created_at", "finished_at")


def _fetch_tasks(backend: BackendClient) -> list[dict]:
    data = backend.request("GET", "/api/tasks")
    tasks = data.get("tasks") if isinstance(data, dict) else None
    return tasks if isinstance(tasks, list) else []


def _compact_task(t: dict) -> dict:
    """Strip bulky fields (command/env/last_log_lines) agents never need."""
    out = {k: t.get(k) for k in _TASK_KEEP_FIELDS if t.get(k) is not None}
    metadata = t.get("metadata") or {}
    if metadata.get("train_type"):
        out["train_type"] = metadata["train_type"]
    if metadata.get("error"):
        out["error"] = metadata["error"]
    return out


def _busy_tasks(backend: BackendClient) -> list[dict]:
    """Compute-lane tasks that occupy (or will occupy) the GPU.

    Tagger/install tasks live on other lanes and must not block submission.
    """
    return [
        t
        for t in _fetch_tasks(backend)
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

        注意：校验只查训练页匹配与字段类型，不检查数据集 toml 内容、不试跑；
        校验通过 ≠ 训练能跑（数据集字段兼容性、优化器参数类型等问题仍可能在
        启动后暴露，启动失败时用 get_task_log_tail 看 traceback）。
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

        result = backend.request("POST", "/api/run", json_body=config)
        return {
            "task_id": result.get("task_id"),
            "queued": result.get("queued"),
            "hint": "用 get_task_log_tail / get_task_metrics 轮询进度（间隔 >= 30 秒）；排错加大 log limit",
        }

    @mcp.tool()
    def submit_from_preset(preset_name: str, overrides: Optional[dict] = None, confirm_queue: bool = False) -> dict:
        """以预设为底 + 覆盖字段提交训练。⚠️ 需要用户确认：占用 GPU。

        参数：
        - preset_name: 预设名（list_presets 返回的 metadata.name）
        - overrides: 要覆盖的字段字典，如 {"output_name": "x", "max_train_epochs": 1}
        - confirm_queue: 同 submit_training 的排队确认
        预设只提供参数底子；底模/数据集路径等仍需在预设或 overrides 里齐全。
        """
        data = backend.request("GET", "/api/presets")
        presets = data.get("presets") if isinstance(data, dict) else None
        if not isinstance(presets, list):
            raise BackendError("后端未返回预设列表")
        base = None
        for p in presets:
            if isinstance(p, dict) and (p.get("metadata") or {}).get("name") == preset_name:
                base = p
                break
        if base is None:
            names = [(p.get("metadata") or {}).get("name") for p in presets if isinstance(p, dict)]
            raise BackendError(f"未找到预设: {preset_name}。可用: {names}")
        config = dict(base.get("data") or {})
        config.update(overrides or {})
        return submit_training(config=config, confirm_queue=confirm_queue)

    @mcp.tool()
    def list_tasks(status: str = "", limit: int = 10) -> dict:
        """列出训练任务（紧凑版，剥掉 command/env/日志等大字段）。

        参数：
        - status: "active" = 只看 RUNNING/QUEUED；"finished" = 只看已结束
          （FINISHED/FAILED/TERMINATED）；"all" = 全部；默认 "" = active + 最近几条已结束。
        - limit: 最多返回条数（按创建时间取最新），默认 10。
        """
        tasks = [t for t in _fetch_tasks(backend) if isinstance(t, dict)]
        if status == "active":
            tasks = [t for t in tasks if t.get("status") not in TERMINAL_STATUSES]
        elif status == "finished":
            tasks = [t for t in tasks if t.get("status") in TERMINAL_STATUSES]
        elif not status:
            active = [t for t in tasks if t.get("status") not in TERMINAL_STATUSES]
            finished = [t for t in tasks if t.get("status") in TERMINAL_STATUSES]
            tasks = active + finished[-limit:]
        tasks = tasks[-limit:] if limit > 0 else tasks
        return {"tasks": [_compact_task(t) for t in tasks], "returned": len(tasks)}

    @mcp.tool()
    def get_task_status(task_id: str) -> dict:
        """查单个任务的紧凑状态（id/status/returncode/error），不用拉全量列表。"""
        for t in _fetch_tasks(backend):
            if isinstance(t, dict) and t.get("id") == task_id:
                return _compact_task(t)
        raise BackendError(f"未知任务: {task_id}（用 list_tasks 看现有任务）")

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
