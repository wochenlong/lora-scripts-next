"""FastMCP server assembly for the Next Trainer sidecar."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import __version__
from .backend import BackendClient
from .tools import dataset, discovery, docs, monitor, training, workflows

SERVER_INSTRUCTIONS = """\
Next Trainer（lora-scripts-next）训练管理器的 agent 操控面。

标准训练流程：get_schemas 查参数体系 → 构造配置 → validate_config 校验 \
→ submit_training 提交（需用户确认）→ list_tasks / get_task_metrics / \
get_task_log_tail 轮询进度。

硬性规则：
- GPU 资源宝贵。submit_training / resume_task / retry_task 会占用 GPU 跑训练，\
terminate_task 会杀掉训练进程；这四个工具必须先获得用户明确确认再调用。
- 所有工具都是快照式返回，没有流式接口；监控用轮询（get_task_metrics / \
get_task_log_tail），不要高频刷（建议间隔 >= 30 秒）。
- 数据集文件投递不在本服务范围内：大文件走 ssh/rsync 到服务器路径，再用 \
scan_dataset 让后端扫描。
- 训练参数含义不清时，先用 list_docs / get_doc 查内置文档，再向用户提问。
"""


def create_server(
    base_url: str = "http://127.0.0.1:28000",
    read_only: bool = False,
    timeout: float = 10.0,
) -> FastMCP:
    """Build the MCP server. Pure assembly; no network I/O happens here."""
    backend = BackendClient(base_url, timeout=timeout)
    mcp = FastMCP(
        "next-trainer",
        instructions=SERVER_INSTRUCTIONS,
    )

    discovery.register(mcp, backend)
    monitor.register(mcp, backend)
    workflows.register(mcp, backend)
    docs.register(mcp)
    if not read_only:
        training.register(mcp, backend)
        dataset.register(mcp, backend)

    return mcp
