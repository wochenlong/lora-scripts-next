# 标签翻译下载与安装系统全面测试验收计划

更新时间：2026-10-02（Asia/Shanghai）

当前状态：T1～T6 已完成，等待用户验收；当前分支不创建 PR。

本计划用于 Goal 01a0c916-e274-7412-9950-a0d41c633bdf 的下载、安装、运行和 UI 验收。测试必须与当前用户
已经存在的 assets/tag_translation 数据隔离，不能把已有词库、缓存或模型文件当作全新安装证据。

## 验收目标

1. Danbooru 词库检查、更新、取消、重试、失败保留旧库和“已是最新”状态准确。
2. Qwen3.5-0.8B GGUF 与受管 llama.cpp 运行时可以一键安装，失败原因可诊断，成功后自动启动。
3. 主应用端口来自 GUI 启动环境，llama-server 内部端口由操作系统动态分配，任何端口冲突可恢复。
4. 远程多接口、本地模型、自动回退和缓存契约不互相污染。
5. 翻译设置中的每个按钮、开关、输入卡片、状态、取消和保存行为均有证据。
6. 在新的隔离目录中重新安装并启动项目后，完成真实 Dataset Editor 翻译链路验收。

## 测试隔离约束

- 源码验收目录：project/.runtime/tag-translation-isolated-acceptance-20261002/source
- 用户数据目录：project/.runtime/tag-translation-isolated-acceptance-20261002/data
- 隔离启动端口：由测试脚本预分配空闲端口，禁止假设 28000。
- 隔离目录禁止读取或复制当前 assets/tag_translation/danbooru、models、translations.sqlite3。
- 词库和 Qwen 模型下载只允许写入隔离 data 目录。
- 测试结束保留 manifest、日志、状态快照和失败响应；不把二进制加入 Git。

## 阶段和门禁

### A. 静态契约门

检查配置 schema、API 类型、状态枚举、错误码、端口分配和下载 URL 清单。

通过条件：

- internal://dataset-translation 是唯一持久化本地 endpoint 标识。
- 配置不保存固定公共端口。
- 本地状态未 running 时不能保存 llm_mode=local。
- 模型镜像、llama.cpp b11327 Windows CPU x64 资产和词库镜像均有可测试 URL。

### B. 后端模拟门

使用 mock HTTP 响应覆盖下载成功、404、超时、网络名不可用、校验失败、取消、重复点击和
旧库保护。

通过条件：

- 每个失败状态都有 state、error、可重试动作。
- 临时文件不会替换旧文件。
- 同一任务重复点击不会创建多个下载任务。
- 取消后任务可再次重试。
- 端口分配返回空闲 loopback 端口，不使用固定值。

### C. 前端组件门

逐项验证：

| 区域 | 操作 | 预期 |
| --- | --- | --- |
| 词库 | 检查更新 | 显示已是最新或有新版本 |
| 词库 | 已是最新时点击更新 | 按钮禁用，API 也不启动下载 |
| 词库 | 有新版本时更新 | 显示下载进度，完成后更新行数/SHA |
| 词库 | 取消 | 状态 cancelled，旧库仍可查询 |
| 词库 | 重试 | 新任务重新开始 |
| LLM | 添加远程接口 | 新卡片出现，未自动启用其他卡片 |
| LLM | 启用另一远程接口 | 同一时间只有一个 active |
| LLM | 删除接口 | 至少保留一个接口，active 自动迁移 |
| 本地模型 | 未安装时进入页签 | 可以进入并看到一键安装 |
| 本地模型 | 未 running 时保存 | 保存按钮禁用，后端返回 409 作为保护 |
| 本地模型 | 一键安装 | 模型和 runtime 分阶段显示进度 |
| 本地模型 | 自动启动 | 健康检查通过后显示 running |
| 本地模型 | 停止/启动 | 状态正确变化，端口可重新分配 |
| 翻译缓存 | 清理缓存 | 网络/LLM 缓存清除，Danbooru 不受影响 |
| 翻译显示 | 开关、provider、全数据集 | 进度 N/N，切图和刷新状态保留 |

### D. 隔离安装门

在新的隔离目录执行：

1. 从远端克隆 feat/tag-translation。
2. 安装前端依赖并执行生产构建。
3. 使用隔离数据根目录启动后端，动态申请 GUI 端口。
4. 打开翻译设置，执行词库检查、词库安装/取消/重试。
5. 执行 Qwen + llama.cpp 一键安装；如果受网络或磁盘限制失败，必须保存完整错误和
   重试证据，不能用旧目录资产替代。
6. 启动本地运行时，记录实际分配的 loopback 端口。
7. 执行 Danbooru、本地 only、MyMemory、远程 LLM、自动回退五条翻译路径。
8. 在 Dataset Editor 中翻译至少 20 个标签，验证中文显示、原始 caption 不变和缓存重启恢复。

### E. 发布门

通过条件：

- 后端专项测试和前端完整 npm run check 通过。
- 隔离启动日志、状态快照、端口清单和翻译响应已保存。
- 无 secrets、用户路径、模型二进制或缓存进入 Git。
- 任务书和验证记录更新到实际结果。
- 只有通过所有门禁后才提交推送。

## 必须保留的证据

- isolated-install-manifest.json
- backend-start.log
- frontend-check.log
- dictionary-status-before-after.json
- local-model-status-before-after.json
- port-allocation.json
- translation-path-matrix.json
- UI 手动验收清单和失败重试记录

本次隔离实测结果保存在：
`project/.runtime/tag-translation-isolated-acceptance-20261002/`，其中
`ui-manual-acceptance.json` 是按钮/组件验收矩阵，`local-dynamic-port-final.json`
记录动态端口，`failed-install-evidence.json` 保留了首轮运行时缺 DLL 的真实失败，
用于证明修复前后差异。
