# MCP 客户端接入指南（agent 操控面）

Next Trainer 自带一个 MCP sidecar（`mcp/` 目录），让 AI agent（opencode / Claude Desktop / Cursor 等）通过 MCP 协议操控本地训练服务：查参数 schema → 校验配置 → 提交训练 → 轮询进度。

sidecar 是**独立进程 + 独立虚拟环境**，主程序代码零改动；不用时删掉 `mcp/` 并加 `--disable-mcp` 即可。

## 1. 安装与启动

### 随主程序启动（默认）

主程序（`gui.py`）启动时会自动拉起 sidecar（和 TensorBoard 同级管理，退出时自动回收）：

- 前提：`mcp/.venv` 已安装（见下）；没装则打一行 info 日志跳过，不影响主程序
- 默认端口 **28002**，**始终绑 127.0.0.1**（无鉴权，即使 `--listen` 也不对外；远程用 `ssh -L 28002:127.0.0.1:28002`）
- 关闭：`--disable-mcp`；改端口：`--mcp-port`

首次安装：

```bash
python3 -m venv mcp/.venv
mcp/.venv/bin/pip install -e "mcp[dev]"   # dev 仅跑测试需要
```

### 手动启动（调试/独立部署）

```bash
mcp/.venv/bin/python -m next_trainer_mcp --base-url http://127.0.0.1:28000 --port 28002
```

| 参数 | 默认 | 说明 |
|------|------|------|
| `--base-url` | `http://127.0.0.1:28000` | Next Trainer 后端地址 |
| `--transport` | `streamable-http` | `stdio` 用于本机单客户端（见下） |
| `--host` | `127.0.0.1` | **不要绑 0.0.0.0** |
| `--port` | `28001`（手动模式默认） | 随主程序启动时为 28002 |
| `--read-only` | 关 | 只注册发现/监控/文档工具，禁用训练提交与控制 |

### stdio 模式（本机单客户端，免驻留）

opencode.json 用 local 类型直接拉起，生命周期跟随 opencode 会话：

```json
{
  "mcp": {
    "next-trainer": {
      "type": "local",
      "command": ["/path/to/lora-scripts-next/mcp/.venv/bin/python", "-m", "next_trainer_mcp", "--transport", "stdio"],
      "enabled": true
    }
  }
}
```

## 2. 客户端配置（streamable-http）

opencode（`opencode.json`）：

```json
{
  "mcp": {
    "next-trainer": {
      "type": "remote",
      "url": "http://127.0.0.1:28002/mcp",
      "enabled": true
    }
  }
}
```

建议把危险工具的权限设为 `ask`：`next-trainer_submit_training`、`next-trainer_terminate_task`、`next-trainer_resume_task`、`next-trainer_retry_task`、`next-trainer_submit_from_preset`；其余 allow。

Claude Desktop / Cursor：在各自 MCP 配置中加入同样的 URL（streamable-http 传输）。支持 MCP resources 的客户端可直接浏览 `docs://index` 下的内置文档。

调试：`npx @modelcontextprotocol/inspector` 连 `http://127.0.0.1:28002/mcp` 手动点工具。

## 3. 工具面（29 个）

- 发现：`get_schemas` / `list_presets` / `list_gpus` / `get_version` / `list_saved_params`
- 配置：`validate_config`（提交前必走；仅查页面/类型匹配，通过 ≠ 能跑）
- 训练控制：`submit_training` ⚠️ / `submit_from_preset` ⚠️（预设+覆盖）/ `list_tasks`（紧凑裁剪，支持 status/limit 过滤）/ `get_task_status` / `terminate_task` ⚠️ / `resume_task` ⚠️ / `retry_task` ⚠️
- 监控（快照式）：`get_task_metrics`（`max_points` 降采样）/ `get_task_log_tail` / `list_task_previews`
- 组合工作流：`get_task_overview`（状态+loss+日志尾+预览数一次拿全）/ `grep_task_log`（关键词搜日志）/ `get_task_config`（任务 autosave 配置）/ `get_last_task` / `wait_task`（有界等待终态）
- 数据集：`scan_dataset` / `interrogate` / `get_tagger_status` / `browse_server_path` / `list_files`
- 文档：`list_docs` / `get_doc` / `get_training_cookbook`（首次使用必读，含实战坑位清单）

安全闸门：

- 四个 ⚠️ 工具的描述均标注需用户确认，依赖客户端审批机制兜底。
- `submit_training` 在已有任务 RUNNING/QUEUED 时拒绝提交，除非带 `confirm_queue=true`。
- 无鉴权：sidecar 默认绑 `127.0.0.1`；要远程用请 `ssh -L 28001:127.0.0.1:28001`，**不要** `--host 0.0.0.0`。

## 4. 测试

```bash
mcp/.venv/bin/python -m pytest mcp/tests -q
```

单测用 httpx MockTransport 模拟后端，断言每个工具的请求路径/参数与错误转换；集成冒烟见 `tests/test_integration_smoke.py`（真实 streamable-http 起停 + 工具调用）。
