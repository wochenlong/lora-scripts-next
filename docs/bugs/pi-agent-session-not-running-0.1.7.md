# Pi Agent `SESSION_NOT_RUNNING` 回归修复记录

- 日期：2026-08-25
- 版本：next-trainer-pi-agent 0.1.7
- 路径：Lite bugfix；BDD + TDD + browser real smoke
- 状态：closed

## 问题摘要

Agent 第一轮回答结束后，UI 仍可能显示“停止”。用户发送第二条普通消息时，前端把它误判为 `followUp`，Sidecar 已处于 idle，因此返回 `followUp requires an active Agent run. (SESSION_NOT_RUNNING)`。

## 复现步骤

1. 打开已安装并启用的 Agent 浮窗。
2. 进入新会话或恢复历史会话。
3. 发送第一条消息并等待模型完成。
4. 在 UI 仍显示 running/settling 时发送第二条消息。

期望：第二条消息在上一轮已结束时启动新 prompt；运行中时才作为 follow-up。

实际：本地 reducer 与 Sidecar 权威状态发生竞态，第二条消息被错误发送为 follow-up 并得到 `SESSION_NOT_RUNNING`。

## 根因

1. 插件 Transport 发出首条 prompt 前没有等待 `session.subscribe` 真正连接到 Sidecar，快速回答可能丢失终态事件。
2. `SessionRegistry.history()` / `thinking()` 无条件释放 wrapper，恢复会话时会把刚建立的订阅从当前 record 上移除。
3. UI 只依赖事件流，没有在 `running/settling` 长时间未收敛时读取 `session.getState` 和权威历史。
4. 历史 JSONL 中的旧 Pi 消息可能没有 UI `id`，权威回填会触发 React key 警告。

## 最小修复

- Host 仅在 Sidecar 内层 stream 发出 connected state 后确认 `session.subscribe`。
- `BridgeAgentTransport` 在订阅确认前不发送 prompt。
- `useAgentConversation.send()` 用权威 session state 校准普通 prompt/follow-up，并只对未入队的 `SESSION_NOT_RUNNING` 安全重试一次普通 prompt。
- running/settling 期间以 500ms 低频只读 reconcile 作为事件流容错；权威状态 idle/failed 时加载历史并恢复 UI。
- Sidecar listener 改为 session 级持久集合；临时 read access 只在无现存 wrapper、无 listener 且 idle 时释放，10 分钟 wrapper release 后 listener 仍可在 resume 时继续接收事件。
- 历史投影为 legacy message 补充确定性稳定 ID。

## 修改文件

- `frontend/src/extensions/pluginFrameBridge.ts`
- `frontend/src/extensions/pluginFrameBridge.test.ts`
- `plugin-packages/next-trainer-pi-agent/ui/src/bridge/bridge-transport.ts`
- `plugin-packages/next-trainer-pi-agent/ui/src/hooks/useAgentConversation.ts`
- `plugin-packages/next-trainer-pi-agent/ui/src/events/conversation-reducer.ts`
- `plugin-packages/next-trainer-pi-agent/ui/tests/bridge-transport.dom.test.tsx`
- `plugin-packages/next-trainer-pi-agent/ui/tests/agent-chat-panel.dom.test.tsx`
- `plugin-packages/next-trainer-pi-agent/sidecar/src/pi/session-registry.ts`
- `plugin-packages/next-trainer-pi-agent/sidecar/src/server.ts`
- 对应 unit/DOM regression tests 与 0.1.7 package/catalog 元数据。

## 回归证据

- 首次失败证据：Host stream admission test `startPluginEventStream is not a function`；Transport test 在 subscribe ack 前已出现 `session.prompt`；Sidecar history test 未观察到 terminal events。
- 前端全量：28 files / 158 passed；typecheck/build 通过；lint 0 errors（2 个既有 warnings）。
- 插件全量：22 unit + 8 contract + 8 integration + 18 logic + 22 DOM = 78 passed；typecheck、UI/EXE build、standalone probe 通过。
- Qwen Real：0.1.6 中同一显式 Qwen session 连续返回 `ROUND_ONE_OK`、`ROUND_TWO_OK`；第二轮无 `SESSION_NOT_RUNNING`，每轮结束均恢复“发送”。
- 0.1.7 恢复上述会话：两轮内容完整、错误区为空、浏览器 console 0 errors / 0 warnings；该复测不产生新的模型请求。
- Package：`next-trainer-pi-agent-0.1.7.zip`，SHA-256 `a019f5408d9cf3e9f0ce224e1c01e87b9da356205cd0b6fc2e0aec737939809a`。

## 结论

该回归可关闭。修复保持 follow-up/steer 能力、单模型会话、10 分钟 idle release 和 Host 安全边界不变。

Next action：无；若再次出现会话终态不收敛，保留对应 session id、Host stream console 和 Sidecar JSONL 作为新的独立问题证据。
