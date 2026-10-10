# U6 完成门（AC-U6）

日期：2026-10-11
状态：`ready_for_manual_acceptance`

## 沙盒

- 路径：`E:/OpenSourceTeamWork/workspace/sandboxes/nl-caption-u6-manual-20261011`
- 源码：独立 worktree，`70ae1c0f`
- 前端：独立 `node_modules`，Node 22.17.1 构建 `frontend/dist`
- 状态根：`runtime-state`（独立 app config、translation SQLite、user-data、queue、cache、HF、marketplace 和 tag-models）
- 本地模型：Qwen3.5-2B GGUF + F16 mmproj，llama.cpp b11327；本地服务已 `ready=true`，能力 `text`、`vision`
- 远程 Key：未注入、未写入

## 启动证据

- 后端 PID：203924
- 监听：`127.0.0.1:28767`
- `GET /`：HTTP 200
- `GET /dataset/tagger`：HTTP 200，浏览器标题“数据集 | Next Trainer”
- 浏览器检查：Dataset Tagger 可切换 Tag/自然语言 Caption；自然语言模式显示 Qwen3.5-2B、英文提示词预设和本地兜底开关
- 启停脚本：沙盒内 `start-u6.ps1`、`stop-u6.ps1`

## 边界

- 该门证明独立项目已构建、启动并可交给用户手测；用户人工验收仍为 `pending_followup`，不冒充人工通过
- 启动日志记录 `torch` 未安装；这只影响训练侧可选模块，Caption/翻译 FastAPI 与 llama.cpp 视觉服务已验证可用
- U1 候选比较探针仍是 `waived_by_user`，不由 U6 推导质量比较结论
