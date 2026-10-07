# 数据集模型打标与自然语言 Caption 长程任务书（Issue #409 对齐版）

## 计划元数据

- Plan ID：`DATASET-NL-TAGGING-20261006`
- Version：`v3.0-issue-409-aligned`
- Last updated：2026-10-07 Asia/Shanghai
- Canonical progress file：本文
- Design source：`docs/design/natural-language-captioning-tagging-design.md`
- Construction plan：`docs/tasks/natural-language-captioning-plan/`
- Contract：[#409 模型打标界面与自然语言标注](https://github.com/wochenlong/lora-scripts-next/issues/409)
- Related issues：#365 数据集工作区、#405 user_data/任务契约
- Current branch：`feat/NL-Captioning`
- Current active phase：重新规划后的 Phase 0 — 契约收敛与差异修复
- Execution readiness：`executing`（用户已于2026-10-07明确建立goal并全面执行）
- Scale：Full

## 总目标

在既有 Dataset Tagger 页面内完成 Issue #409 约定的模型打标体验：用户按“数据集 → 运行方式 → 具体模型 → 模型专属参数/提示词 → 单图试标 → 批量打标”执行 Tag 或自然语言 Caption。WD/CL Tag 行为继续兼容；视觉模型按 capability 生成自然语言；翻译与 Caption 共用统一 LLM 管理；远程 Profile 可用时始终优先，本地视觉模型只在用户明确启用且远程失败后兜底。

首版不实现、不展示组合打标或混合输出。已有 mixed provenance 代码只用于读取历史/外部文件的安全兼容，不得成为新任务的输出模式或验收门。

## 范围与约束

### In scope

- TaggerPage 的模型/运行方式优先信息架构。
- WD/CL Tag 旧 API、旧配置、阈值和输出兼容。
- 本地视觉 Caption 模型和已配置远程视觉 Profile。
- 模型系列折叠、搜索、具体型号、下载/就绪状态和 capability 驱动参数。
- Caption 默认提示词、编辑、保存、另存为、恢复默认、未保存修改保护。
- `user_data/presets/` 中 `kind=caption_prompt` 的预设 CRUD，与训练预设隔离。
- 单图预览、持久批量任务、底部进度、取消、失败项重试、跳过/明确覆盖。
- 共享 LLM Profile、asset、runtime、cache、revision、密钥掩码和连接测试。
- strict JSON/语言/长度/不臆测校验，受限 JPEG data URL，原子写回和 before hash 冲突保护。
- Dataset Editor 的 tag/natural/unknown 安全；历史 mixed 只读兼容。
- Unit、Contract、Integration、Gray、Frontend、Real、EDD、Zero-Short 和 Phase4 隔离重建。

### Out of scope

- `combined`、`mixed`、`tags_then_caption`、`caption_then_tags` 的新建、UI 入口和首版验收。
- WD + Caption 双模型串联、本地 + API 联合流水线。
- 不可用 API 的空入口或虚假“即将可用”模型。
- Agent、sidecar、provider、plugin marketplace 及其旧真实接口测试。
- 让 LLM 替代 WD/CL 生成训练 Tag。
- 独立进程/独立端口、多任务并发调度、自动上传数据集。
- API Key、用户图片、原始响应、模型二进制进入 Git 或证据公开目录。

### 不可违反的边界

- API Key 只在后端运行时注入；配置、响应、预设、任务档案、日志和报告只允许掩码或布尔状态。
- 翻译 Profile 只需 `text`；Caption Profile 必须声明 `vision` 和 `caption`；后端能力校验是最终依据。
- API 运行方式只有在存在真实可用 Profile 时才显示；没有 API 配置不构成空入口。
- 远程视觉请求只发送受限 JPEG data URL，不发送本地路径、文件名、数据集名或 EXIF。
- Natural caption 不经 Tag 拆分、排序、去重、下划线转换；旧 Tag 继续按原逻辑处理。
- 已有标注默认跳过；覆盖必须明确；停止不写空文件；外部 hash 变化触发 conflict。
- 隔离重建必须重新建立目录、venv、node_modules、配置、数据库、缓存、样本和模型资产，禁止复用旧产物。
- 所有失败、跳过和不适用项必须记录实际原因、替代证据和批准人，不能口头核销。

## 执行阶段

### Phase 0：契约收敛与差异修复

**目的**：把现有实现和文档从旧的 mode-first/combined 设计收敛到 Issue #409。

**任务**：

1. 更新设计书、任务书、goal、manifest、总控索引和目标计划，统一声明 #409。
2. 从首版 UI 和 API contract 移除 combined/mixed 创建入口、布局参数和双模型流水线。
3. 设计 runtime-first/model-first 页面信息架构和 capability schema。
4. 盘点现有 `prompt_presets` 配置，设计迁移到 `user_data/presets/` 的兼容方案。
5. 明确 API 动态入口：已配置可用才显示；无配置不显示空入口。
6. 清除 Agent/plugin 计划、验收和非本任务依赖。

**输出**：对齐后的设计书、任务书、goal、manifest、差异清单、迁移说明。

**完成标准**：所有 canonical 计划文档无首版 combined 硬门、无 Agent 范围；关键代码差异已逐项登记；无未授权 P0/P1。

**验证**：文档一致性搜索、API/UI contract review、git diff review。

**证据**：`docs/evidence/natural-language-captioning/phase-0-contract-alignment/`。

### Phase 1：统一 LLM 与模型能力契约

**目的**：确保翻译和打标共用管理层，模型 capability、运行方式、专属参数和远程优先行为可验证。

**任务**：

1. 保持 v5 Profile/旧翻译配置迁移和密钥掩码兼容。
2. 为模型注册表补齐 `supports_tag`、`supports_caption`、`supports_vision`、transport、下载状态和参数 schema。
3. 将 Caption prompt preset 接入 `user_data/presets/`，与训练 preset 按 kind 隔离；保留旧配置读取迁移。
4. 让翻译 Profile 可以 text-only，Caption 请求拒绝无 vision Profile 和不适用参数。
5. 保持 remote-first；local fallback 必须显式启用；API 未配置时不产生空入口。
6. 保持连接测试、cache revision、资产/运行时状态和日志脱敏。

**输出**：统一 Profile/model/preset contract、迁移器、API schema、缓存 revision 规则。

**完成标准**：旧翻译和旧 Tag contract 通过；preset 跨进程可读；不适用参数前后端均拒绝；密钥永不落盘明文。

**验证**：Unit、Contract、Gray、fake text/vision endpoint、配置迁移回归。

**证据**：`docs/evidence/natural-language-captioning/phase-1-llm-contract/`。

### Phase 2：模型打标后端任务链路

**目的**：实现 Tag 和自然语言 Caption 两条独立、可恢复、安全写回的任务链路。

**任务**：

1. 保持旧 `/api/interrogate` 映射 Tag；新增或调整 job contract 为 `runtime + model + capability + output`。
2. 实现受限图片预处理、data URL、严格 JSON、语言/长度/不臆测检查。
3. 实现 Caption prompt snapshot、cache、任务持久化、报告、取消、失败项重试和恢复。
4. 保持 Tag formatter 与 natural formatter 分离；首版拒绝 `output=combined`，不新建 mixed。
5. 实现已有 caption 默认跳过、明确覆盖、in-use 锁、before hash、原子写回、rollback/clear。
6. 保持单文件失败隔离和只重试失败项。

**输出**：后端 API、job store、vision adapter、writer、report、错误码和回归测试。

**完成标准**：fake endpoint 可覆盖成功、非法 JSON、超时、429、取消、部分失败、冲突、恢复和重试；natural 文本逐字节安全写回；旧 Tag 逐文件兼容。

**验证**：Unit、Contract、Integration、Gray、低限额真实本地视觉模型；已配置远程时执行 remote-first。

**证据**：`docs/evidence/natural-language-captioning/phase-2-caption-job/`。

### Phase 3：前端、编辑器与用户数据联动

**目的**：按 Issue #409 重做页面结构和预设交互，确保旧用户流程清晰、窄屏可用、自然语言安全。

**任务**：

1. 将页面顺序改为数据集、运行方式、模型、专属参数/提示词、输出、底部任务进度。
2. 实现系列折叠、搜索、具体型号显示、下载状态和能力过滤。
3. 只为 Caption 模型显示 prompt editor；实现保存、另存为、恢复默认、未保存修改保护。
4. 预设使用 user_data CRUD；训练预设列表不得读取 Caption 预设。
5. 实现单图试标、批量、取消、失败重试、历史和隐私提示；移除 combined/mixed UI。
6. Dataset Editor 继续保护 natural/unknown 和历史 mixed，Tag 操作不得破坏自然语言。

**输出**：Vue 页面/API/composable/components/i18n/CSS、Dataset Editor 安全和手工验收记录。

**完成标准**：旧 Tag 表单回归；模型切换不携带错误参数；无 API/无视觉模型时页面有可操作提示；桌面、390px、Tab/Escape、错误和空配置通过；底部无常驻右侧进度栏。

**验证**：Node 22 check、typecheck、lint、Vitest、build、浏览器手测和 Dataset Editor 端到端。

**证据**：`docs/evidence/natural-language-captioning/phase-3-frontend-editor/`。

### Phase 4：真实资源、EDD 与发布前审计

**目的**：在首版范围内完成真实本地 Caption、可选远程优先、Tag 灰度、质量评测、隐私和维护验收。

**任务**：

1. 冻结公开/脱敏样本、来源 URL、SHA、许可证、模型和 prompt revision。
2. 完成 Qwen3-VL-2B 本地视觉模型真实三样本 Caption；如已配置远程 Profile，再完成远程优先与显式 fallback。
3. 完成 ONNX/WD Tag 真实灰度，确认旧输出兼容；不执行 combined 作为本版验收。
4. 完成 EDD 规则和人工评分；评分必须绑定准确的模型、prompt、revision 和输出文本。
5. 完成 Zero-Short、rollback/clear、缓存隔离、隐私扫描和用户文档。

**输出**：真实资源报告、EDD 评测、Zero-Short、隐私/清理报告、发布前审计。

**完成标准**：本地 Caption 真实路径通过；远程若可用则 remote-first 通过；质量、资源、取消、写回、Editor safety 证据齐全；无秘密进入 Git。

**验证**：Real、EDD、Zero-Short、manual acceptance、privacy scan。

**证据**：`docs/evidence/natural-language-captioning/phase-4-real-evaluation/`。

### Phase 5：隔离重建与从零真实验收

**目的**：证明首版交付不依赖旧工作树、旧配置、旧缓存或旧模型资产。

**任务**：

1. 从最新提交创建全新 worktree/干净源码 checkout。
2. 创建全新 Python 3.11 venv、Node 22 依赖和 frontend dist。
3. 重新下载公开样本、Qwen3-VL 资产/runtime 和 ONNX Tag 资产，逐项记录 URL/SHA/revision。
4. 创建全新配置、SQLite、cache、queue、output；不复制旧 sandbox、旧数据库、旧模型或旧输出。
5. 完成正式 lifespan 启动、空配置 Zero-Short、本地 Tag、本地 natural Caption、取消/重试/冲突/编辑器安全。
6. 若有远程 Profile，完成 remote-first 和显式 fallback；无远程凭据则记录为可选路径未配置，不伪造通过。
7. 运行前后端测试矩阵、构建检查、隐私扫描和清理，并保留隔离日志。

**输出**：`phase-5-isolated-rebuild/` 全套日志、hash、环境清单、测试报告、清理报告和最终签字。

**完成标准**：隔离环境关键链路通过；失败后必须修复并重新建立全新环境；没有任何旧产物复用证明；最终 GATE 全部通过。

**验证**：Zero-Short、真实本地、可选远程、完整测试、人工验收、privacy/cleanup。

**证据**：`docs/evidence/natural-language-captioning/phase-5-isolated-rebuild/`。

## 决策记录

### Verified facts

- Issue #409 是当前模型打标界面、参数、预设和首版范围的维护者契约。
- TagUI 是 RPA 流程工具，不能作为视觉 Caption 实现直接移植。
- 统一 LLM、自然语言任务、Dataset Editor 来源保护和部分真实模型证据已经存在，但之前的计划把 combined 误列为首版能力。
- 当前分支没有 Agent/plugin 源码改动；越界 Agent 计划和工具已清理。

### Locked decisions

- 页面一级分类按本地模型/API 服务；Tag/Caption 按模型能力显示。
- 首版不实现、不展示、不验收 combined/mixed 新建流程。
- Caption prompt preset 使用 `user_data/presets/` 的 `kind=caption_prompt`，与训练预设隔离。
- 翻译和 Caption 共用 LLM 管理；翻译不要求 vision，Caption 必须 vision。
- 已配置远程 Profile 时始终 remote-first；本地 fallback 必须显式启用。
- API 未配置时不展示空入口；远程真实验收是可选配置路径，不能伪造为已通过。
- Agent、plugin、sidecar、marketplace 不属于本任务。
- 完成必须包含前后端、完整测试、人工验收和隔离重建；不能用历史 combined 证据替代本版门禁。

### Active assumptions

- 现有 LLM 配置可通过一次兼容迁移映射到 user_data prompt preset，而不破坏翻译配置。
- 当前 Qwen3-VL-2B Q4_K_M + Q8 mmproj 仍是个人电脑可用的本地视觉候选；Phase 4/5 需重新核对资源。
- #405 的 user_data CRUD/任务目录契约可以被自然语言预设和任务记录复用。

### Open questions

- user_data preset 的最终字段和 CRUD 路由需以当前 #405 实际实现为准。
- 本地视觉模型可展示的温度、长度等参数必须按模型注册表实际支持范围冻结。
- Windows 符号链接测试所需权限环境仍需在最终完整矩阵中解决或记录明确环境阻塞。

## 关键制品和环境

- Design：`docs/design/natural-language-captioning-tagging-design.md`
- Canonical task book：本文
- Construction manifest：`docs/tasks/natural-language-captioning-plan/plan-manifest.md`
- Goal：`docs/tasks/natural-language-captioning-plan/03_goal提示词/自然语言打标全程执行_goal提示词.md`
- Issue #409：`https://github.com/wochenlong/lora-scripts-next/issues/409`
- Branch：`feat/NL-Captioning`
- Frontend：Node 22，`npm --prefix frontend run check`
- Backend：Python 3.11 隔离环境，相关 `pytest` 和完整矩阵按阶段记录
- Evidence root：`docs/evidence/natural-language-captioning/`
- 禁止复用：旧 `.venv`、`node_modules`、模型缓存、配置、SQLite、output、P1 sandbox 作为 Phase 5 资产

## 进度台账

| 阶段 | 状态 | 说明 |
|---|---|---|
| Phase 0 契约收敛 | in progress | 差异表已归档；预设及组合入口首批修复，模型能力目录待实现 |
| Phase 1 LLM/模型能力契约 | pending | 需先完成 Phase 0 完成门 |
| Phase 2 后端 Caption/Tag 任务 | pending | 既有实现需按新 contract 复核 |
| Phase 3 前端/Editor/user_data | pending | 既有 UI 需移除 combined 并改为 model-first |
| Phase 4 真实资源/EDD | pending | 历史证据保留但按新门重新归类 |
| Phase 5 隔离重建 | pending | 最终完成门 |

### 当前验证状态

历史证据显示：Node 22 前端和相关后端已有大量通过项，远程/本地 Caption、Tag 灰度、缓存、取消、冲突、Zero-Short 和人工评分曾有验证；这些证据需要按新契约重新审计。完整矩阵曾有 Windows symlink 权限失败和未核销 skip，不能直接宣告完成。历史 combined 证据不再作为本版验收依据。

### 下一步动作

实现后端模型能力目录、TaggerPage 一级运行方式与模型系列选择器，再补前后端参数隔离；Phase0差异表已归档。

## 失败与变更处理

- 发现任何 combined/mixed 新入口、Agent 依赖、空 API 入口、能力绕过、明文凭据或自然语言被 Tag 清理，立即生成 failure report，禁止进入下一阶段。
- 发现数据写回风险先停止任务，保留 before hash 和备份，修复后重新运行受影响矩阵。
- 远程资源不可用时可以执行本地路径并明确标记远程未配置/未运行；不得把未运行写成通过。
- 隔离重建任一步失败时回到对应阶段修复，然后建立新的全新隔离根目录重跑；不能在失败环境上补丁式宣告完成。
- 任何重大范围变化必须同步设计书、任务书、goal、manifest、阶段计划和 change-control 记录。

## 阶段完成证据索引

旧阶段证据仍保留在 `docs/evidence/natural-language-captioning/`，但需要在 Phase 0/4 重新标记适用性。新增证据必须绑定：Issue #409、commit、模型/资产 revision、prompt/preset revision、样本 SHA、实际命令、结果、资源占用和清理状态。

## 2026-10-08 执行增量

用户明确全面施工，Goal active。本轮完成user_data Caption预设存储/API、版本/备份/修订冲突、类型隔离/其他设置保留、显式旧预设导入；Vue内置/用户预设、另存为/恢复默认/未保存保护；单图与批量读取预设及system prompt、缓存revision；combined UI移除/API拒绝；底部进度和1100px布局。后端44 passed，前端331/51、type/lint/build通过。详情及未完成项见phase-0-contract-alignment/2026-10-08-presets-and-delta.md。

当前唯一下一步：实现后端模型能力目录及运行方式/模型系列选择器，然后补前后端参数隔离。尚无新契约最终验收，Phase0/1 in progress，其余pending；历史combined记录不用于本版完成门。全局user_data基础尚未合入本checkout，多文件事务/跨进程并发需继续验证；不实施#405的端口仲裁或Agent迁移。
