# 自然语言打标执行检查点

更新：2026-10-07。此文件用于续接，canonical progress 始终是 `docs/tasks/natural-language-captioning-task-book.md`。完整目标是后端、前端、共享 LLM、编辑器安全、完整测试、真实/人工验收和最后从零隔离重建；不能降级为局部实现。

## 当前状态

- 工作树：`E:\OpenSourceTeamWork\workspace\branches\feat-NL-Captioning`；分支 `feat/NL-Captioning`；本批修复前 HEAD：397581cb82dd0f714a4e15997847db8e9c27c409。本文件随代码一起提交，提交号读取 `git log`。
- Phase 0 完成门复审中；Phase 1/2 有代码但仍 in progress；Phase 3/4 pending。不得倒推完成门通过。
- 当前用户完整 goal 位于 `C:\Users\25454\.codex\attachments\33329a36-8e01-4211-b79c-a080571cde4b\goal-objective.md`，每次自动续接先读。
- 实际验证：相关后端 136 passed / 4 warnings / 5.35s；Node 22 check 304 tests / 48 files passed，typecheck/lint/build 通过，lint 2 个已有 warning。具体命令见 evidence 增量报告。
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

## 待办与风险

1. Phase 0：逐项核销完整 facade 灰度、迁移幂等、所有错误契约和兼容完成门；当前相关回归通过不等于完整完成门。
2. Phase 1：真实受管 Qwen 启停/调用/取消，组合预览，prompt preset/snapshot 校验，报告持久化/恢复，完整 timeout/429/部分失败/retry/in-use/cache matrix。
3. Phase 2：翻译和打标实际复用同一设置组件，profile CRUD/连接测试、语言过滤、编辑取消回滚和 prompt 预设，preview busy、防重叠轮询；浏览器桌面/窄屏/键盘/空配置/错误/隐私验收。
4. Phase 3：冻结 3–5 个公共样本及 hash/rubric、远程中文和本地中文真实路径、人工评分（不得伪造评分）、Zero-Short、隐私/回滚和文档。
5. Phase 4：所有必要修复已提交后，全新 worktree/new venv/new Node22 ci/new config/cache/models/output，重新安装构建启动并真实复验整个关键链路；不复用旧缓存/未提交文件。
6. 恢复宽范围失败逐用例证据，补训练依赖或合法不适用审查及 dev 对照；Windows symlink 必须有实际适用验收，不能无授权跳过。

## 单一下一步动作

逐项核销 Phase 0 的统一 LLM 完成门，灰度已新增 3 场景并随翻译相关回归 58 passed；下一步审查配置/错误契约和迁移边界，未通过时继续在 Phase 0 修复。

## 续接提示词

```text
继续 DATASET-NL-TAGGING-20261006 的完整交付任务。先读当前 goal、canonical task book、manifest 和此续接记录，核对 git status 和最新提交。不要重复 TagUI/P1 探针或把 136 个相关测试当成完整验收。当前 Phase 0 完成门复审中，先补 legacy facade 与统一服务的灰度证据；再按 Phase 1→4 完成真实受管视觉、共享 UI、完整矩阵和隔离从零重建。严格遵守远程优先、显式本地兜底、vision 强制、凭据进程内注入/掩码持久化、Tag 与 natural 原文安全边界。普通修复自主继续，最终完成前不能更新 goal 为 complete。
```

Confidence：medium。当前源码、环境和相关测试已核对；宽范围失败详情和完整灰度/真实/人工/隔离验收仍不完整。Continuity degradation risk：宽范围运行缺逐用例日志，后续须恢复或定向复现。
