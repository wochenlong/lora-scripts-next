# MCP 客户端接入指南（agent 操控面）

Next Trainer 自带一个 MCP sidecar（`mcp/` 目录），让 AI agent（opencode / Claude Desktop / Cursor 等）通过 MCP 协议操控本地训练服务：查参数 schema → 校验配置 → 提交训练 → 轮询进度。

sidecar 是**独立进程 + 独立虚拟环境**，主程序零改动、零依赖侵入；不用时整体删掉 `mcp/` 即可。

## 1. 安装与启动

```bash
python3 -m venv mcp/.venv
mcp/.venv/bin/pip install -e "mcp[dev]"   # dev 仅测试需要，生产可去掉 [dev]
mcp/.venv/bin/python -m next_trainer_mcp --base-url http://127.0.0.1:28000 --port 28001
```

前提：Next Trainer 主程序已在 `http://127.0.0.1:28000` 运行（`--base-url` 可指向其他主机/端口）。

常用开关：

| 参数 | 默认 | 说明 |
|------|------|------|
| `--base-url` | `http://127.0.0.1:28000` | Next Trainer 后端地址 |
| `--transport` | `streamable-http` | `stdio` 用于本机单客户端 |
| `--host` | `127.0.0.1` | **不要绑 0.0.0.0**；远程访问走 ssh 端口转发 |
| `--port` | `28001` | sidecar 监听端口 |
| `--read-only` | 关 | 只注册发现/监控/文档工具，禁用训练提交与控制 |

## 2. 客户端配置

opencode（`opencode.json`）：

```json
{
  "mcp": {
    "next-trainer": {
      "type": "remote",
      "url": "http://127.0.0.1:28001/mcp",
      "enabled": true
    }
  }
}
```

建议把危险工具的权限设为 `ask`：`submit_training`、`terminate_task`、`resume_task`、`retry_task`；其余 allow。

Claude Desktop / Cursor：在各自 MCP 配置中加入同样的 URL（streamable-http 传输）。支持 MCP resources 的客户端可直接浏览 `docs://index` 下的内置文档。

调试：`npx @modelcontextprotocol/inspector` 连 `http://127.0.0.1:28001/mcp` 手动点工具。

## 3. 工具面（约 22 个）

- 发现：`get_schemas` / `list_presets` / `list_gpus` / `get_version` / `list_saved_params`
- 配置：`validate_config`（提交前必走）
- 训练控制：`submit_training` ⚠️ / `list_tasks` / `terminate_task` ⚠️ / `resume_task` ⚠️ / `retry_task` ⚠️
- 监控（快照式）：`get_task_metrics` / `get_task_log_tail` / `list_task_previews`
- 数据集：`scan_dataset` / `interrogate` / `get_tagger_status` / `browse_server_path` / `list_files`
- 文档：`list_docs` / `get_doc` / `get_training_cookbook`（首次使用必读）

安全闸门：

- 四个 ⚠️ 工具的描述均标注需用户确认，依赖客户端审批机制兜底。
- `submit_training` 在已有任务 RUNNING/QUEUED 时拒绝提交，除非带 `confirm_queue=true`。
- 无鉴权：sidecar 默认绑 `127.0.0.1`；要远程用请 `ssh -L 28001:127.0.0.1:28001`，**不要** `--host 0.0.0.0`。

## 4. 测试

```bash
mcp/.venv/bin/python -m pytest mcp/tests -q
```

单测用 httpx MockTransport 模拟后端，断言每个工具的请求路径/参数与错误转换；集成冒烟见 `tests/test_integration_smoke.py`（真实 streamable-http 起停 + 工具调用）。
