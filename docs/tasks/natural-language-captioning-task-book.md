# 数据集自然语言打标长程任务书

## 计划元数据

- Plan ID: DATASET-NL-TAGGING-20261006
- Version: v2.2-executing
- Last updated: 2026-10-07 Asia/Shanghai
- Canonical progress file: 本文
- Construction plan: docs/tasks/natural-language-captioning-plan/
- Design source: docs/design/natural-language-captioning-tagging-design.md
- Current branch: feat/NL-Captioning
- Current active phase: Phase 3 — 评测、发布与维护；Phase 0/1/2 完成门通过
- Execution readiness: executing（已收到完整交付 goal；禁止以局部检查通过替代最终验收）
- Scale: Full

## 目标

在 Dataset Tagger 页面提供 Tag、自然语言 caption、组合打标三种模式。打标与标签翻译共用统一 LLM 管理、profile、Key、模型资产、运行时、缓存和连接测试。翻译 profile 不要求视觉能力；caption/组合 profile 强制声明 vision capability。远程 LLM 总是优先，本地 LLM 只作为用户主动启用的可选兜底。

## 范围与约束

- In scope:
  - 统一 LLM 配置、profile、asset、runtime、cache、revision。
  - 远程 OpenAI-compatible vision 与本地 Qwen3-VL-2B fallback。
  - Tagger job、提示词预设、预览、缓存、取消、重试、报告和安全写回。
  - TaggerPage UI、共享 LLM 设置、自然语言/组合模式。
  - Dataset Editor 的 tag/natural/mixed 格式安全。
  - 单元、契约、集成、灰度、真实资源、Zero-Short 和 LLM 评测。
  - 前后端完整验收、人工验收、发布前回归和隔离重建从零真实验收。
- Out of scope:
  - 让 LLM 直接替代 WD/CL 生成训练 Tag。
  - 自动上传用户数据集到远程服务。
  - 发布模型二进制到 Git。
  - 多任务并发调度。
- Constraints:
  - Node 22、npm、Python 项目现有依赖。
  - API Key 仅在后端进程内注入；配置文件只保存掩码，重启后重新注入。翻译与打标共用凭据，前端响应以掩码返回。
  - 远程图片使用受限 JPEG data URL，不发送本地路径。
  - 修改公开代码必须关联 GitHub Issue；实现应在 feature 分支。
  - 最终完成必须在全新目录/全新运行环境中从零安装、构建、启动并验收；真实远程请求只使用允许外发的脱敏样本，本地模型资产和凭据不进入 Git。
  - 隔离重建不得复用旧 worktree 的未提交文件、旧配置、旧模型缓存或旧测试产物。

## 执行阶段

### Phase 0: 预检与统一 LLM

- Purpose: 冻结兼容边界，建立统一 profile、revision、capability 和远程优先路由。
- Outputs: mikazuki/llm facade、配置迁移、fake client、profile contract。
- Completion criteria: 旧翻译测试通过；v4 配置可迁移；translation 不需要 vision；caption 选择 text-only profile 会被拒绝；remote-first 路由有测试。
- Validation: Python unit/contract/gray tests、旧 API regression。
- Evidence: 阶段任务书、测试日志、迁移样例、decision log。

### Phase 1: 后端视觉任务

- Purpose: 接入视觉请求、提示词、任务进度、缓存、写回和报告。
- Outputs: vision adapter、caption job、writer、错误码、retry/cancel。
- Completion criteria: Tag/natural/combined 三模式可由 fake endpoint 完成；写回原子化；训练占用和文件冲突受保护。
- Validation: unit/contract/integration、fake OpenAI-compatible server、低限额真实 Qwen3-VL。
- Evidence: job report、failure samples、before/after hash。

### Phase 2: 前端与编辑器安全

- Purpose: TaggerPage 具备远程优先、提示词、预览、进度和重试；Dataset Editor 能安全处理 mixed caption。
- Outputs: Vue API/types/composables/components、i18n、caption_format。
- Completion criteria: UI 不允许不具备 vision 的 profile 执行 caption；旧 Tag 表单回归；自然语言文本不被 Tag 清理破坏。
- Validation: typecheck/lint/Vitest/build、组件手测、窄屏和键盘验收。
- Evidence: frontend test report、manual acceptance record。

### Phase 3: 评测、发布与维护

- Purpose: 用冻结评测集确认模型/提示词质量，补齐 Zero-Short、隐私、回滚和交付说明。
- Outputs: eval dataset、baseline report、release audit、user documentation。
- Completion criteria: P0/P1 无未授权问题；远程中文路径和 Qwen3-VL-2B fallback 都有证据；计划产物与代码状态一致。
- Validation: real resource test、EDD rubric、Zero-Short、review。
- Evidence: docs/tasks/natural-language-captioning-feasibility-probe.md、eval report、final review。

### Phase 4: 隔离重建与从零真实验收

- Purpose: 证明交付物不依赖开发机残留状态，用户可以从干净来源真实复现完整功能。
- Outputs: isolated rebuild log、依赖与配置清单、前后端启动记录、真实远程优先/本地兜底结果、写回前后 hash、清理报告和最终验收签字记录。
- Completion criteria:
  - 从全新 worktree 或干净源码包开始，不带旧 .venv、node_modules、模型缓存、配置、SQLite、测试输出和未提交文件；
  - 按文档重新安装依赖、构建前端、启动后端和前端，并通过健康检查；
  - 在受控脱敏样本上完成 Tag、natural、combined 三种路径，验证远程优先、远程失败后本地兜底、取消、失败重试、冲突保护和安全写回；
  - 运行完整测试矩阵并保存命令、commit、环境、样本 hash、profile/prompt revision 和输出摘要；
  - 清理临时模型、图片、Key、原始响应和缓存，确认无秘密或用户数据进入 Git。
- Validation: Zero-Short、isolated rebuild、backend/frontend build、real remote/local smoke、manual acceptance、privacy scan。
- Evidence: evidence/natural-language-captioning/phase-4-isolated-rebuild/ 下的可审计日志、hash 清单、测试报告和清理报告。

## 决策记录

### Verified facts

- TagUI 是 RPA 流程工具，不提供本项目所需视觉 caption 实现。
- SiliconFlow Qwen3.6-27B 三张样本均返回中文严格 JSON。
- Qwen3-VL-2B Q4_K_M + Q8 mmproj 本地 CPU-only 三张样本均返回中文严格 JSON。
- 当前翻译已有远程/本地 LLM 配置和受管 runtime。

### Locked decisions

- 翻译与打标共享 LLM 管理、profile、资产、runtime、cache 和测试。
- translation profile 不要求 vision；natural/combined profile 必须 vision。
- 远程 LLM 永远优先；本地 LLM 只作为显式启用的兜底。
- V1 Tag 继续使用 WD/CL；LLM 只生成自然语言 caption。
- Qwen3-VL-2B 是本地中文兜底候选；SmolVLM-256M 是英文低资源候选。
- 完整交付必须包含后端实现、前端实现、Dataset Editor 安全、完整测试与人工验收，以及最后一次隔离重建从零真实验收。

### Open questions

- Qwen3-VL-2B 在真实动漫数据集上的描述质量和显存/CPU体验。
- mixed caption 是否需要训练侧额外解析。
- 是否把 caption job 历史接入现有任务历史数据库。
- 真实验收使用的脱敏样本和本地模型资产下载源，需要在执行前由 goal 运行者记录；不得把凭据写入计划或证据。

## 关键制品与环境

- Design: docs/design/natural-language-captioning-tagging-design.md
- Feasibility: docs/tasks/natural-language-captioning-feasibility-probe.md
- Construction plan: docs/tasks/natural-language-captioning-plan/
- Probe worktree: E:\OpenSourceTeamWork\workspace\sandboxes\nl-caption-p1-20261006
- Required frontend command: npm --prefix frontend run check
- Required backend command: pytest tests/test_tag_translation_*.py tests/test_tagger_*.py
- Runtime baseline: Node 22.17.1，Python 3.11.15 隔离测试环境，Windows 16-thread CPU，32 GiB RAM；宿主 Python 3.14 不作为依赖兼容验收依据

## 进度台账

- Overall progress: Phase 0/1 完成门通过；后端持久任务、冻结预设、恢复、报告、组合预览、错误矩阵、Tag 灰度和低限额本地真实写回已有证据。Phase 2 已核销共享设置、历史报告 UI 和编辑器来源保护；不以相关测试代替最终完整验收。
- Phase 0: done（证据：phase-0-llm/2026-10-07-phase-0-gate-review.md）
- Phase 1: done（证据：phase-1-vision-job/2026-10-07-phase-1-gate-review.md）
- Phase 2: done（证据：phase-2-frontend-editor/2026-10-07-phase-2-gate-review.md）
- Phase 3: in progress
- Phase 4: pending
- Validation status: 2026-10-07 Python 3.11 相关后端回归 241 passed；Node 22 check 51 files / 329 tests passed，typecheck/lint/build 通过（lint 2 项已有 warning）。宽范围 GUI 回归 1139 passed / 11 failed / 21 skipped，另有训练子项目收集失败；失败未获得豁免，不能视为完整测试通过。详见 evidence 下本次增量报告和 failure report。
- Residual risks: 共享设置组件和编辑器来源保护已接入并回归；历史报告/恢复 UI、轮询治理、批量/undo/redo 冲突已验证；本地资源管理已共享，规定Phase2浏览器矩阵已验证，正式启动/真实模型仍待验；安全回滚/清理、真实远程/本地生产链路及 EDD 人工评分已验证；真实 ONNX 三模式、正式启动和最终验收仍待闭环。本地三样本开发验收复用 P1 模型，Phase 4 不得复用。
- Continuity source: docs/tasks/natural-language-captioning-continuity.md；记录环境、Git 和单一步骤，证据以阶段报告为准。

## 下一步动作

完成主测试矩阵复验并核销剩余失败、跳过和联网测试。

## 阶段完成证据

Phase2逐项追踪：API/types/composable/components、三模式/vision/language/remote排序、prompt/preview/progress/cancel/retry/report、共享设置/翻译兼容、Dataset Editor格式投影/原文/冲突、旧Tag灰度以及桌面/窄屏/键盘/错误/空配置/隐私/重启恢复均对应实际证据。详见Phase2 gate-review。lifespan=off和fake模型仅支持本阶段业务验收，未替代Phase3/4。

Phase3开工：三公开样本与SHA/URL/rubric已冻结，资源/预算/清理/Phase4输入已登记；初始冻结时评分为空；后续用户人工评分六条均 20/20，见独立 approval 记录。整体完整矩阵11失败/21跳过未核销，GATE09/10未通过。

Phase3回滚/清理已实现并测试，actual浏览器恢复2/冲突1、取消无变化、清理保留文件/来源通过。相关241后端/329前端。原11失败已恢复逐case：17项依赖/README/process复验通过，关闭其中7个；4个symlink仍因WinError1314等待用户权限环境，未豁免；完整矩阵/真实/EDD/正式启动/Phase4仍未完成。

## 2026-10-07 真实生产路径及人工评分同步

远程、本地和同时可用的 remote-first/显式 fallback 均通过当前生产路径验证；三样本严格 JSON、缓存零重复请求、预览不写盘通过。用户对最初 A/B 六条描述五维各给 4 分，每条 20/20，两组均满足冻结 rubric。精确文本哈希与评分范围见 phase-3-evaluation/human-evaluation-approval.json；路由后续不同文本不沿用评分。详见 2026-10-07-production-real-and-human-review.md。Phase3仍 in progress，Phase4 pending，完整矩阵及最终交付门未通过。

## 2026-10-07 Tag/combined、Zero-Short和矩阵增量

真实默认WD ONNX三图旧/新Tag逐字节相同（13/11/8 Tags、8.366s）；实际WD+Qwen combined三图3/3、24.208s，mixed来源和actualTags正确，缓存3命中零LLM请求、preview零写盘、模型已停止。正式FastAPI lifespan=on和新Node22 dist已通过空配置/无Key/无词库/无视觉模型启动；API健康与桌面/390px页面可用，安装/配置入口、默认禁用fallback/生成均核对。证据见phase-3-evaluation/2026-10-07-real-tag-combined-zero-short.md，不属于Phase4。

主tests收集1503项；分区运行1467 passed/11 failed/25 skipped/1 deselected/77 subtests/308.42s。排除的唯一联网ModelScope tokenizer测试实际下载整个模型仓库，已停止并保留pending，未豁免。11失败中的7项已修复：任务维护测试不再向sys.modules泄漏Tagger替身，LyCORIS fake工厂允许可选导入缺失；相关55 passed/7.50s。另4项Windows symlink权限未解决。完整分区复验正在运行，不能提前计通过；25项skip逐案审计/授权尚未核销。

DiffSynth Windows fixture改为稀疏标志+末字节seek/write，保留逻辑长度与模型header，13 passed/2.80s。初次truncate产生的测试文件清理被自动审批拒绝（仅blocked by policy），保留未复用，最终清理待核销。自建正式UI和模型进程停止，浏览器about:blank。

使用/维护说明已补充docs/natural-language-captioning-usage.md。Phase3仍in progress，Phase4 pending，goal未完成。当前唯一下一步：完成主测试矩阵复验并核销剩余失败、跳过和联网测试。
