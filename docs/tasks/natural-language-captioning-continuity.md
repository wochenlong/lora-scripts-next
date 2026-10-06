# 自然语言打标执行检查点

更新：2026-10-07。此文件用于续接，canonical progress 始终是 `docs/tasks/natural-language-captioning-task-book.md`。完整目标是后端、前端、共享 LLM、编辑器安全、完整测试、真实/人工验收和最后从零隔离重建；不能降级为局部实现。

## 当前状态

- 工作树：`E:\OpenSourceTeamWork\workspace\branches\feat-NL-Captioning`；分支 `feat/NL-Captioning`；本批修复前 HEAD：397581cb82dd0f714a4e15997847db8e9c27c409。本文件随代码一起提交，提交号读取 `git log`。
- Phase 0 done（phase-0-gate-review 逐项核销）；当前正式 Phase 1，Phase 1/2 仍 in progress；Phase 3/4 pending。完整 GATE-09/10 未通过。
- 当前用户完整 goal 位于 `C:\Users\25454\.codex\attachments\33329a36-8e01-4211-b79c-a080571cde4b\goal-objective.md`，每次自动续接先读。
- 实际验证：最新相关后端 168 passed / 4 warnings / 5.58s；Node 22 check 307 tests / 48 files passed，typecheck/lint/build 通过，lint 2 个已有 warning。命令见 Phase 0 gate-review 和 Phase 1 contract-prompt-safety 报告。
- 宽范围测试仍有 11 failed / 21 skipped，根目录 pytest 另有 31 项 collection errors；缺失逐用例失败输出，详见 failure report，不能称完整验收通过。

## 环境和重要路径

- Python：`E:\OpenSourceTeamWork\workspace\sandboxes\nl-caption-runtime-20261006\.venv\Scripts\python.exe`（3.11.15，requirements 和 pytest 已安装）。宿主 Python 3.14 不适合当前依赖 TestClient，曾恢复宿主 httpx 0.28.1，不应再次降级宿主。
- 前端：Node 22.17.1 可由 `npm exec --yes --package=node@22.17.1 -- node ...` 调用；npm CLI 位于 `I:\NdoeJS\node_modules\npm\bin\npm-cli.js`。当前 npm ci 已完成。不要使用宿主 Node 24 验收。
- P1 公共样本和二文件 GGUF 已在 `workspace\sandboxes\nl-caption-p1-20261006\.sandbox-data\`；可用于中间开发验证，Phase 4 禁止复用。
- 固定视觉模型：Qwen3-VL-2B Q4_K_M + Q8 mmproj，revision/SHA/size 在 `mikazuki/llm/local_vision.py`；runtime b11327，旧 probe 和本次受管进程均已停止。`tools/verify_managed_caption_runtime.py` 三样本开发验证已通过（复用资产，不是 Phase 4），开发目录 `E:\OpenSourceTeamWork\workspace\sandboxes\nl-caption-managed-20261007`。
- 旧 worktree 不删除；不要把旧工作树未提交状态当作隔离验收来源。禁止凭据、模型、图片、SQLite、环境或 node_modules 入 Git。

## 关键实现及决策

- `mikazuki/llm/config.py` 与旧 translation config 共用配置锁和文件；`secrets.py` 只在进程内持有 Key，磁盘只有掩码，旧明文首次读原子迁移；重启须重新注入。测试覆盖排序/删除/清除/重启及写失败。
- `service.py` 生产默认关闭 local fallback；显式启用仍 remote-first；连接测试只访问指定 profile，校验成功 JSON，不返回原始响应。该诊断特例不改变生产路由。
- `local_vision.py` 复用翻译模型目录的 llama.cpp runtime，校验模型和 mmproj 二文件 SHA；有安装/取消/启停 API 和 UI。受管开发验证启动 4.835s、3 张严格 JSON 中文、RSS 峰值 3107680256 bytes，取消 0.195s 后再次请求通过，停止进程通过；HTTP API/下载/浏览器/真实写回仍待验证。
- caption job 有快照、revision SQLite 缓存、可取消 in-flight request、Tagger 单任务占用、冲突哈希和原子写回；Dataset Editor 和前端禁止 natural/mixed 经过 Tag 清理，保留原文空白。
- Tag 继续由 WD/CL 生成，LLM 只写 natural；caption 强制 vision，translation 只需 text。远程仅发送受限 JPEG data URL。
- 受跟踪 dist 曾被旧提交误删，本批以 Git restore 恢复 1cfa947 的生成基线；最终必须重新从源码 build，禁止手工编辑 dist。
- 426396f 已提交第一批共享 LLM/受管视觉修复和证据；第二批新增配置 HTTP 契约（包括损坏读取不覆盖）、严格 JSON 重复键/非有限值拒绝、预览截断/错误脱敏、原图变更冲突、预处理 v2 与提示词预设 UI。最新相关 suite 168 和 Node 22 check 307 覆盖本批。旧翻译 remote 选择只关闭兜底，保留其他模块共享的 runtime；旧 local 选择可复用已 ready 的共享 text 模型，不强迫安装独立翻译模型。

## 待办与风险

1. Phase 0 已核销：迁移/掩码/修订/路由/精确连接测试/旧 API/实际 fake HTTP 灰度等证据见 gate-review；不需要反复重新运行已通过的同一 suite，除非有新改动或失败。
2. Phase 1：真实受管 Qwen 启停/调用/取消，组合预览，prompt preset/snapshot 校验，报告持久化/恢复，完整 timeout/429/部分失败/retry/in-use/cache matrix。
3. Phase 2：翻译和打标实际复用同一设置组件，profile CRUD/连接测试、设置编辑取消回滚、防重叠轮询；语言过滤、提示词预设保存/选择/删除/撤销、preview busy 已实现及组件验证，但浏览器桌面/窄屏/键盘/空配置/错误/隐私验收仍待完成。
4. Phase 3：冻结 3–5 个公共样本及 hash/rubric、远程中文和本地中文真实路径、人工评分（不得伪造评分）、Zero-Short、隐私/回滚和文档。
5. Phase 4：所有必要修复已提交后，全新 worktree/new venv/new Node22 ci/new config/cache/models/output，重新安装构建启动并真实复验整个关键链路；不复用旧缓存/未提交文件。
6. 恢复宽范围失败逐用例证据，补训练依赖或合法不适用审查及 dev 对照；Windows symlink 必须有实际适用验收，不能无授权跳过。

## 单一下一步动作

实现并验证 Phase 1 的持久任务快照/报告以及服务重启后的恢复边界；先读 Phase 1 开工清单与长程任务书，再检查 caption_job 现有内存报告/失败重试结构。

## 续接提示词

```text
继续 DATASET-NL-TAGGING-20261006 的完整交付任务。先读当前 goal、canonical task book、manifest、此续接记录与 Phase 1 开工清单/长程任务书，核对 git status 和最新提交。Phase 0 已核销，当前 Phase 1。不要重复 TagUI/P1 探针或把 168 个相关后端测试与前端 307 个测试当成完整验收。先补持久任务快照/报告与重启恢复；再完成共享 UI、完整矩阵、EDD 和隔离从零重建。严格遵守远程优先、显式本地兜底、vision 强制、凭据进程内注入/掩码持久化、Tag 与 natural 原文安全边界。普通修复自主继续，最终完成前不能更新 goal 为 complete。
```

Confidence：medium。当前源码、环境和相关测试已核对；宽范围失败详情和完整灰度/真实/人工/隔离验收仍不完整。Continuity degradation risk：宽范围运行缺逐用例日志，后续须恢复或定向复现。
