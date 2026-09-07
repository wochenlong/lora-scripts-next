"""Built-in documentation tools + MCP resources.

Content is a snapshot copied from the repo's docs/ at sidecar release
time (docs_content/ inside this package) — never read from a repo path
at runtime, so the sidecar has no path coupling to the main app.
"""

from __future__ import annotations

from importlib import resources

from mcp.server.fastmcp import FastMCP

DOCS_PACKAGE = "next_trainer_mcp.docs_content"

_DOC_TITLES = {
    "cli-args.md": "训练 CLI 参数说明",
    "krea2-linux-multigpu.md": "Krea2 Linux 多卡训练指南",
    "portable-getting-started.md": "便携版上手指南",
    "task-detail-insights-api.md": "任务洞察 API（metrics/previews 返回结构）",
}

COOKBOOK = """\
# Next Trainer agent 标准操作流程

## 提交训练
1. `list_gpus` —— 确认可用 GPU，决定 config 里的 gpu_ids。
2. `get_schemas` —— 找到目标 page_train_type 的 schema，弄清必填字段与默认值。
3. 构造完整 config（必须含 model_train_type；训练数据/底模用服务器路径）。
4. `validate_config` —— 校验不通过就修正后重试，不要跳过。
5. **向用户确认后** `submit_training` —— 已有任务在跑时会被闸门拦下，
   确认排队意图后带 confirm_queue=true 重试。
6. 轮询：`list_tasks` 看状态，`get_task_metrics` 看 loss/进度，
   `get_task_log_tail` 看日志尾部（排错时加大 limit）。

## 排错（如复现用户 issue）
- `get_task_log_tail(task_id, limit=500+)` 拿 traceback。
- 配置类报错先用 `validate_config` 复现，比真跑训练快得多。
- 预览图相关：`list_task_previews` 看采样是否产出。

## 实战坑位（复现 issue 踩出，别再踩）
- `learning_rate` 传 JSON 数值（如 1e-6），**不要传字符串**——Automagic 对字符串 lr 直接 TypeError。
- `gpu_ids` 字段可能触发后端 500（非 JSON 响应）；单卡环境建议不传该字段，让后端默认分配。
- 数据集 toml 各引擎**不通用**：kohya 系（anima-lora 等）不收 `validation_split_num`、
  `subsets[].recursive`、`cache_dir`（这些是 anima-fast 字段），会直接 voluptuous 报错。
- kohya 数据集 subset 的 `image_dir` 必须直指含图片的目录（每目录一个 subset），
  不支持递归父目录。
- Anima 训练选 Automagic/CAME 时，后端会把 mixed_precision 从 fp16 静默翻转为 bf16
  （防 nan 护栏），任务 metadata 里以翻转后的值为准。

## 红线
- submit/terminate/resume/retry 必须先获得用户明确确认。
- 不要高频轮询（>= 30 秒间隔）。
- 数据集大文件走 ssh/rsync，不走本服务。
"""


def _read_doc(name: str) -> str:
    if name not in _DOC_TITLES:
        raise KeyError(name)
    return resources.files(DOCS_PACKAGE).joinpath(name).read_text(encoding="utf-8")


def _catalog() -> dict:
    return {
        "docs": [
            {"name": name, "title": title, "uri": f"docs://doc/{name}"}
            for name, title in _DOC_TITLES.items()
        ]
    }


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    def list_docs() -> dict:
        """列出可查的内置文档（训练参数/多卡/便携版等说明书）。"""
        return _catalog()

    @mcp.tool()
    def get_doc(name: str) -> str:
        """取一份内置文档全文（markdown）。name 从 list_docs 返回的清单里选。"""
        try:
            return _read_doc(name)
        except KeyError:
            available = ", ".join(sorted(_DOC_TITLES))
            raise ValueError(f"未知文档: {name}。可用: {available}")

    @mcp.tool()
    def get_training_cookbook() -> str:
        """获取 agent 标准操作流程（提交训练/排错/红线），首次使用本服务前必读。"""
        return COOKBOOK

    @mcp.resource("docs://index")
    def docs_index() -> str:
        """内置文档目录。"""
        lines = ["# Next Trainer 内置文档", ""]
        for name, title in _DOC_TITLES.items():
            lines.append(f"- [{title}](docs://doc/{name}) — `{name}`")
        return "\n".join(lines)

    @mcp.resource("docs://doc/{name}")
    def doc_content(name: str) -> str:
        """单篇内置文档全文。"""
        return _read_doc(name)
