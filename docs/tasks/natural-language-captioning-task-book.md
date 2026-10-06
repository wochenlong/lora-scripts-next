# 数据集自然语言打标长程任务书

## 计划元数据

- Plan ID: DATASET-NL-TAGGING-20261006
- Version: v2.0-preflight-audit
- Last updated: 2026-10-06 Asia/Shanghai
- Canonical progress file: 本文
- Construction plan: docs/tasks/natural-language-captioning-plan/
- Design source: docs/design/natural-language-captioning-tagging-design.md
- Current branch: feat/NL-Captioning
- Current active phase: Phase 0 — 预检与统一 LLM（等待 goal 解锁）
- Execution readiness: drafting（等待用户最终 goal 提示词）
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
  - API Key 只能存后端并以掩码返回。
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
- Runtime baseline: Node 22，Python 3.14 host probe，Windows 16-thread CPU，32 GiB RAM

## 进度台账

- Overall progress: Phase 0 统一 LLM 和 Phase 1/2 的首轮实现已进入工作树；后端共享配置、视觉任务 API、TaggerPage 三模式和 Dataset Editor 格式安全已有可执行代码与 focused evidence。
- Phase 0: in progress
- Phase 1: in progress
- Phase 2: in progress
- Phase 3: pending
- Phase 4: pending
- Validation status: P1 pass-with-boundary；后端 focused 57 tests 和前端 check 已通过，真实资源、完整灰度/人工验收和隔离重建尚未完成。
- Residual risks: 远程优先路由和旧配置迁移需要先建立 contract；本地 Qwen3-VL-2B 资源成本需在 UI 中可见。

## 下一步动作

继续完成 Phase 0–2 的缺口和完整后端/前端验收，然后进入 Phase 3 评测与 Phase 4 隔离重建；任何阶段未通过完成门都不得标记 complete。
