# 数据集模型打标与自然语言 Caption 长程任务书（Issue #409 对齐版）

2026-10-10 最新增量已交付：用户批准吸收参考项目选项组织与完整双语提示词，要求实施、简单测试后亲自测试。执行明细 `natural-language-captioning-reference-modification-task-book.md`；本文件保持唯一总进度。原 Phase0–5 闭门历史有效，本次 Standard 局部优化。完整语言模板/简短详细/默认后端模板选择完成；Caption133、前端348/53/type/lint/build和手测build/HTTP/浏览器通过；53个用户数据状态文件hash升级及启动后全一致。原文可见、中文译文0模型请求、390px通过。新模板真实质量/新远程生成未运行；人工验收待用户。证据 `docs/evidence/natural-language-captioning/2026-10-10-reference-delta/verification-report.md`，下一步用户按手测清单测试。

## 计划元数据

- Plan ID：`DATASET-NL-TAGGING-20261006`
- Version：`v3.0-issue-409-aligned`
- Last updated：2026-10-09 Asia/Shanghai
- Canonical progress file：本文
- Design source：`docs/design/natural-language-captioning-tagging-design.md`
- Construction plan：`docs/tasks/natural-language-captioning-plan/`
- Contract：[#409 模型打标界面与自然语言标注](https://github.com/wochenlong/lora-scripts-next/issues/409)
- Related issues：#365 数据集工作区、#405 user_data/任务契约
- Current branch：`feat/NL-Captioning`
- Current active phase：Phase0–5全部完成；清理门已核销
- Execution readiness：`complete-with-boundary`（所有硬门完成，批准的平台边界保留）
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
- 翻译Profile只需text；Caption模型目录必须有vision/caption，共享Profile必须声明vision；后端目录、Profile和实际响应校验是最终依据。
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
| Phase 0 契约收敛 | done | #409差异表、范围收敛、模型目录与user_data规则已实施；文档复盘已同步 |
| Phase 1 LLM/模型能力契约 | done | 共享配置/掩码/迁移、能力参数拒绝、预设进程事务和fake/gray回归通过 |
| Phase 2 后端 Caption/Tag 任务 | done | 假模型失败矩阵/持久化/预览/取消/恢复/写回/真实灰度通过，完成门复核完成 |
| Phase 3 前端/Editor/user_data | done | model-first/预设/任务联动/390px/键盘及前端342项通过；真实Editor安全复核完成 |
| Phase 4 真实资源/EDD | pass-with-boundary | 当前真实模型/UI/Zero-Short通过；511通过与四项Linux原case组合验收获用户批准，新火箭五维各4分；Windows原生symlink未验 |
| Phase 5 隔离重建 | pass-with-boundary | 候选8986b9e从零与全部功能验收通过；2026-10-09用户手动删除并实测核销清理 |

### 当前验证状态

最终候选8986b9e：前端342/52、typecheck/lint/build通过；后端516项，Windows512通过/四项权限失败/0skip，独立Linux同候选四个原case通过且用户批准组合验收。真实Qwen/ONNX/HTTP22项、浏览器、人工评分、正式Zero-Short及第五次fresh重建通过；清理已实测完成。远程本轮未配置，不标记通过；历史combined不纳入。

### 下一步动作

原goal已complete，之后新建的全新手动测试项目已就绪并保留；用户按中文README做最后手测，反馈实际问题后再处理。

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

## 2026-10-08 模型能力与浏览器增量

GET /api/tagger/models和本地/API一级选择已实现；系列折叠/原名搜索/下载状态/具体型号/每模型草稿、API空入口保护、前后端参数隔离；Caption生成参数进入cache/任务快照；manager/retry拒绝combined、worker不生成mixed；默认跳过和retry外部hash冲突保护。相关后端216通过，前端336/52及type/lint/build通过。实际新fake fixture完成preview不写盘、batch3写回/重复skip3零额外provider、390px无溢出/底部任务、Qwen缺失安装入口和禁用生成，修复KeepAlive初始目录请求丢弃。报告phase-0-contract-alignment/2026-10-08-model-catalog-browser.md。

不属于真实模型或Phase5。预设事务/跨进程、任务档案联动、Tag单图试标及最终验证未完成。唯一下一步：补预设多文件失败恢复/跨进程revision保护和显式legacy导入UI。全部自建browser fixture已停止，tracked dist恢复，不修改既有tests/test_diffsynth_review.py。

## 2026-10-08 预设存储与导入完成增量

本轮预设事务/journal恢复、OS跨进程锁、完整settings revision、上一版本备份、路径约束、明确确认的一次性导入、系统提示词编辑/全草稿撤销、保留草稿刷新已实现。专项真实进程并发和硬退出16通过；相关223通过，随后APIfocused37；前端340/52/check/build通过。实际fake browser取消导入0写入/确认导入保留旧源和草稿，另存默认模板跨独立BrowserContext及后端重启保留正文/系统提示词；非真实模型或Phase5。

证据2026-10-08-preset-transactions-import.md。单一下一步：既有TaskManager+user_data/tasks/dataset-tagger档案，任务页停止真正取消、重启状态和档案写入失败不开始。不要将Task.start_log_only简单注册后当完成：Task.terminate目前只杀process，Caption没有独立process，必须打通取消回调。既有tests/test_diffsynth_review.py保留未提交；全部自建进程停止、dist恢复。

## 2026-10-08 任务归档与任务页联动增量

自然语言任务已接入既有TaskManager maintenance lane和user_data/tasks/dataset-tagger归档；冻结配置先落盘再启动，取消回调实际取消推理，逐文件失败/只重试失败项/原参数恢复、任务报告链接和安全删除均已实施。后端相关296通过，API增量39、桥接专项10通过；前端340/52/check/build通过。实际fake浏览器取消零写盘、两图部分失败后仅重试1项/额外请求1，服务重启状态与完成时间保持/provider0、删除后再次重启不复活且图片/txt保留。证据2026-10-08-task-archives-bridge.md。不是Real、正式Zero-Short或全新隔离重建。

唯一下一步：将Tag页面批量操作接入同一持久化任务链路并完成Tag单图试标（相同配置、不写盘）。随后执行当前源码完整矩阵、真实模型、正式lifespan和全新隔离重建。Phase0/1仍in progress，goal active，Agent/plugin接口不纳入施工。

## 2026-10-08 Tag持久化与单图试标增量

Tag页面接入统一/tagger/jobs持久化、取消/仅失败重试、底部进度/历史；旧/interrogate保留兼容。单图Tag试标复用批量参数与后处理且零写盘，原生推理结束前不释放占用。快照按能力隔离、报告deep-link支持Tag，独立mount/KeepAlive初始化均验证。相关后端299、专项44、前端341/52/check/build通过；实际fake browser三图Tag/单图结果一致、provider0、任务报告和390px无溢出。证据2026-10-08-tag-preview-durable-ui.md。使用文档与真实验证工具同步本版边界。

唯一下一步：在当前提交源码上执行真实ONNX Tag/HTTP试标/旧输出灰度及本地Qwen自然语言/缓存/归档验证；随后正式lifespan、最终矩阵与Phase5全新重建。尚不宣告阶段/goal完成，不复用旧combined证据或把fake当Real。

## 2026-10-08 真实链路与完成门修复

当前真实ONNX新旧/HTTP预览三图相同，Tag13/11/8，默认跳过和档案通过；本地Qwen3/3、缓存3命中/零新请求、默认跳过零请求、预览不写盘，峰值3,068,416,000字节，运行时停止；正式lifespan空配置Zero-Short和390px通过。真实UI内置系统提示词三图3/3、任务页停止0写盘；编辑器单字natural/撤回/重做/409外部冲突/unknown保护通过。准确输出绑定旧B组相同文本；新UI火箭文本已请求单独人工评分，仍待用户回复。

完整功能矩阵506通过/4Windows symlink权限失败/0skip；独立新Linux/Python3.11环境四原始symlink case实际通过，不改测试。用户选择Windows开发者模式复验或批准跨平台组合覆盖仍待回复，不能擅自核销Windows失败。

验收修复：停止弹窗类型、支持语言过滤、取消模板切换的select显示、Tag下载事件取消与取消终态、模型旁下载/安装状态及目录刷新、损坏档案类型和时间戳隔离。专项50、前端342/52完整check通过。证据phase-4-real-evaluation最新三份报告。Phase5尚未开始。

唯一下一步：本批提交后完整功能矩阵复跑并核对Phase2/3完成门；同时保持两项用户问题待答，再解锁Phase5全新隔离重建。Agent/plugin不纳入施工，既有tests/test_diffsynth_review.py保留未提交。

f53582e提交后的完整复验：51文件/513 case，509 passed/4同样Windows权限失败/0skip，其他失败无新增。Phase2/3对应focused/真实路径/前端与Editor完成门已复核；整项目仍不complete。下一步：完成Phase4用户评分与Windows/跨平台环境口径核销、发布前审计；之后开始Phase5新源码/新依赖/新资产重建。

## 2026-10-08 发布前覆盖审计与重建输入准备

fbf28e6冻结Phase5输入，未创建重建环境。对照实际#405存储约定、Git生产变更与资源来源，确认Agent/plugin生产路径变更0；未实施#405端口仲裁。范围runner补入此前漏列的local_text_registry，两项单独及完整组合复验通过：最新52文件/515case，511passed/4Windows权限失败/0skip/17subtests。重建输入WD仓库名已修正，Qwen/WD revision由公开Hub API实核，runtime发布URL与SHA由GitHub API实核。前两项用户问题仍待答；没有核销Windows失败或代填新火箭评分。

唯一下一步：取得Phase4两项门禁答复后更新完成门并执行Phase5；若待答期间继续准备，限于当前发布审计/重建执行工具，不提前建立或运行Phase5环境。证据2026-10-08-pre-release-audit.md和phase5-frozen-inputs.json；goal保持active。

## 2026-10-08 阻塞门审计

同两项用户输入连续三个goal轮次未到；已完成可独立推进的实现/验证/发布审计与输入冻结。本轮原四Windows case仍WinError1314/4失败，未检测到开发者模式启用；新UI火箭评分仍缺。Phase5前置门不能跳过，不创建重建环境、不自动批准默认选项、不代填评分。当前执行状态blocked/等待用户输入，目标与交付标准保持完整；证据2026-10-08-blocked-gate-audit.md。唯一下一步是接收上述答复，核销Phase4后继续Phase5。

## 2026-10-08 用户验收门批准与Phase5开工

用户答复“4分 all，全部通过”。新UI火箭精确文本五维各4分/20分；四项Windows权限失败采用Linux原case真实symlink补验的组合口径获批准，保留Windows原生场景未验边界。独立事件见phase-4-real-evaluation/2026-10-08-user-gate-approval.json，既有冻结评分不改写。Phase4完成门pass-with-boundary，Phase5解锁；该批准不代替任何尚未执行的从零重建。

唯一下一步：冻结候选提交，在全新隔离root建立源码/依赖，按公开URL重新下载全部样本和模型/运行时，完成Phase5全矩阵及真实验收。既有DiffSynth测试修改保留在开发树，不进入候选。

## 2026-10-08 Phase5首次失败与全新第二次重建

候选25ef85b。首次fresh根前端341通过/1项5s超时，诊断限制worker后该原文件4通过；首次后端508通过/4批准的权限失败/3TaskInsights缺torch skip。首次根不接受，不补丁式宣告通过，资产下载已停止。正在另建r2 fresh worktree/Python/venv/Node依赖/公开URL资产；限制前端并行数且不延长时限，新增下载CPU torch用于三项日志测试，无业务源码修改。证据phase-5-isolated-rebuild/2026-10-08-rebuild-execution.md。

唯一下一步：完成r2环境与完整矩阵，然后正式lifespan Zero-Short、真实模型/HTTP和浏览器验收、隐私清理。Phase5 in progress，goal active。

## 2026-10-08 Phase5网络截断与第四次重建

r3首样本网络截断被SHA/size拒绝，根不接受；r2修正HTTP诊断22项通过但不核销失败。下载器增加有界整文件重试/不复用part/固定SHA，验证截断恢复及三次坏SHA仍拒绝。业务源码未变。唯一下一步：从最新工具提交建立r4全新根，完整重下/依赖/矩阵/真实验收；此前所有根只保留诊断。goal active，不能complete。

## 2026-10-08 Phase5第四根执行进度

当前候选b0a9eb2，r4 fresh源码/Python3.11.15/Node22已建立；全部公开样本、Qwen/mmproj、ONNX/CSV和runtime的新下载凭据passed，前端342/52、typecheck/lint/build全部通过。后端新依赖安装句柄99947及Linux四原case新依赖安装句柄48434确认live。前几次根均不接受，没有复用其二进制/依赖/模型。

唯一下一步：轮询同一安装句柄，完成当前根后端全矩阵、正式Zero-Short、真实Tag/natural/HTTP及浏览器验收，最后隐私清理和完成门审计。goal active，Phase5未完成。最小续接和实际命令见continuity顶部。

## 2026-10-08 首版OpenAPI完成门修复

r4全部功能矩阵/真实HTTP22checks/浏览器/新Linux四原case通过，但审计发现OpenAPI仍把combined和组合layout列为可选；运行时拒绝不等于声明正确。已收敛schema，保留400拒绝，专项41通过。r4不作为最终通过，唯一下一步：提交修复建立r5最新源码、全新依赖和公开URL资产，再完整重跑与清理。源修复仅Caption API，Agent/plugin不触碰；goal active。

## 2026-10-08 最新从零验收结果与唯一剩余门

候选8986b9e完整新r5验收：前端342/52/type/lint/build；后端52文件516项Windows512通过/四权限失败/0skip，独立新Linux同commit四原case真实symlink4通过且用户已批准组合口径。所有公共资产/依赖重新下载；真实Qwen3图/JSON/data URL/cache/资源、ONNX旧输出灰度、HTTP22项、formal Zero-Short、浏览器真实preview和batch3/3、预设跨Context/Esc/Tab/模型参数隔离、精确SHA人工评分绑定均通过。OpenAPI只有natural/tag和单模式layout。最终逐项证据2026-10-08-final-acceptance-audit.md及final-8986b9e包。

清理：所有自建模型/应用停止，五个临时Git源码树与三个Linux根已移除。Windows五个剩余根的组合/单目录递归删除均被自动审批拒绝blocked by policy；不改用其他工具绕过。已向用户请求手动删除或明确保留例外；此前评分与symlink批准不扩大到此次拒绝。唯一下一步：接收该处理结果，核销cleanup并更新最终GATE后才complete。其余工作完成，不继续重复已通过测试。

## 2026-10-08 清理门第二轮复核

五个Windows剩余根仍存在，源码树全部已移除，自建模型/服务无活动进程，清理选择尚无用户答复。本轮只读清单确认约27.27GiB逻辑文件长度（硬链接可能重复计数，不等同实际磁盘占用），跳过目录重解析点，不删除或绕过拒绝。证据2026-10-08-remaining-cleanup-inventory.json。功能证据不变，不重复测试。唯一下一步仍为用户手动清理或明确保留例外，goal active，清理门未核销。

## 2026-10-08 清理门连续第三轮阻塞审计

本轮确认五个Windows剩余根仍在，源码与自建进程均已清理，无live句柄待等。自动审批拒绝后的清理选择连续三轮没有答复；当前所有可独立完成的功能/验收/文档/隐私扫描已经完成，无可再推进的必要工作。不得重复失败删除或改工具绕过，不把此前评分/环境批准扩大到cleanup。依据goal三轮规则，本轮将goal设为blocked，整体目标和已通过证据完整保留。证据2026-10-08-cleanup-blocked-audit.json。唯一解除条件：用户手动删除剩余五根，或明确批准其保留例外；之后核销清理和最终GATE，才complete。


## 2026-10-09 用户手动清理与最终闭门

2026-10-09最终闭门：用户已手动清空sandboxes，实测五个剩余Windows根全部不存在，无自建模型/应用进程，Git过期worktree注册已清理。功能源码与候选8986b9e的Git内容一致（仅65项LF/CRLF checkout行尾差异）；此前全部验收证据有效。GATE10/G-11通过，Phase0–5完成，保留四项Windows原生symlink未验与本轮远程未配置的批准/可选边界。详见phase-5-isolated-rebuild/2026-10-09-cleanup-closure.json。用户要求在goal完成后另建全新手动测试项目，此为后续独立交付，不能复用已删除沙盒。


## 2026-10-09 goal完成后用户手测交付

新手测项目从c3b4a7f干净源码建立，重新安装解释器/依赖、源构建前端并下载冻结资产；12项真实就绪、新浏览器桌面/390px和重启持久性检查通过。数据集干净，应用运行、本地模型停止，不预填Key。保留项目供用户手测；证据2026-10-09-manual-test-delivery.md。用户最终手测仍待其执行，不将自动检查冒充用户验收。


## 2026-10-09 用户手测增量实施与验收

2026-10-09用户手测增量：默认自然语言打标改为英文，内置提示词和System prompt随输出语言切换；自定义草稿保留并提示恢复对应模板。en正文含中文即拒绝，旧错误cache重新生成。Editor修复scan空草稿遮蔽及重新进入刷新，原文展开/恢复磁盘文本；新增只读中文译文，复用共享LLM text路由/运行时/密钥和同SQLite独立表，中文正文零模型请求、remote-first、本地显式兜底，无Key外部API不联系，取消/旧响应隔离。自然语言Tag批量入口禁用，390px面板宽度修复。原goal完成历史保留，新增验收独立记录，不把旧报告当新功能通过。

前端53文件347项/type/lint/build通过（2既有warning）；后端完整矩阵528通过/四项既有Windows权限失败/0skip，新增旧错误缓存再生成场景专项21通过。真实Qwen英文三图3/3、整句中文译文/缓存命中/原文零写回/中文无运行模型短路均通过；浏览器16项/390px通过。代码候选将提交后同步手测项目，保留用户数据；追加的1项测试将在候选上完整矩阵重跑，结果与同步证据归档后完成该增量。原goal不重新创建。


2026-10-09增量完成：候选81e85d7；前端347/53/type/lint/build，后端529通过/四项既有平台失败/0skip，真实本地English3/3与译文/cache/中文短路、浏览器16项通过。已更新现有手测项目并源构建/重启，4目录21文件SHA不变。新远程译文实测及新英文人工评分未运行，不伪称通过。详情2026-10-09-manual-feedback-change.md。


## 2026-10-10 预设统一控制（取代独立语言/详略选项）

用户授权：移除重复的“输出语言”，让提示词预设成为语言和输出格式总控。本次一并将详略入口收敛为预设中的“详细/简短”，避免多个入口描述同一份模板。

- 默认内置英文详细预设；选择预设一次应用完整 user/system prompt、语言与最大字符数。内置中英、繁体、日文各有详细/简短模板。
- 页面仅显示只读预设语言与纯文本 `.txt` 落盘格式；内部严格 JSON 响应协议仍由后端校验，不引入 JSON 文件或组合打标。
- 自定义模板继承当前预设的语言；先选择对应语言的基底再编辑、保存或另存。已有用户默认预设保持，未保存修改在切换时仍需确认。
- 切换模型不再静默换语言或模板。模型不支持预设语言时明确提示、禁用预览和批量提交；用户可选兼容预设或模型。
- 试标/批量从同一份预设草稿派生请求；重试继续使用既有冻结快照。后端 language 字段保留作为校验与 API 兼容契约，没有第二个用户语言控制来源。

验证门：无独立语言/详略下拉；中英预设完整切换；自定义保存保留 language/plain_text；试标与批量配置一致；不兼容模型不会改预设且生成禁用；取消切换保留草稿。执行前端完整 check、Caption 后端组，更新现有手测源码/构建并保护数据 SHA。新真实模型生成质量交由用户亲测。

执行记录：实现与简单验收完成；专项26项、前端349项/53文件/typecheck/lint/build、Caption后端133项、手测项目自身build、HTTP/浏览器/390px通过。手测应用已启动，53个用户数据与配置文件SHA保持。用户真实模型生成与人工验收 pending。证据目录 `docs/evidence/natural-language-captioning/2026-10-10-preset-controls/`。本次风险 P2，范围只涉及打标预设交互，API/Agent/训练不扩展；原公开完成门历史保留，不把旧证据当本次验收。
