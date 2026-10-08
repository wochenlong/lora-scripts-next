# 自然语言打标全程执行 Goal（Issue #409 对齐版）

你现在执行 `DATASET-NL-TAGGING-20261006` 的完整交付。最终目标是在现有 Dataset Tagger 页面中完成 Issue #409 约定的模型打标体验，并通过完整测试、真实资源验收、人工验收和一次全新隔离重建。工作范围必须收敛到数据集 Tag/自然语言 Caption、统一 LLM、user_data 预设、Dataset Editor 安全和相关验收。

## 立即读取的资料

当前分支固定为 `feat/NL-Captioning`。开工先记录 commit、git status、工作树、Python/Node 版本，然后依次读取：

1. `docs/tasks/natural-language-captioning-task-book.md`
2. `docs/design/natural-language-captioning-tagging-design.md`
3. `docs/tasks/natural-language-captioning-plan/plan-manifest.md`
4. `docs/tasks/natural-language-captioning-plan/00_总控目标索引.md`
5. `docs/tasks/natural-language-captioning-plan/00_预检证据/`
6. `docs/tasks/natural-language-captioning-plan/01_目标计划书/`
7. `docs/tasks/natural-language-captioning-plan/02_长程任务书/`
8. `docs/tasks/natural-language-captioning-plan/04_阶段开工清单/`
9. `docs/tasks/natural-language-captioning-plan/05_最小可行性验证/minimal-feasibility-probe-plan.md`
10. `docs/tasks/natural-language-captioning-plan/07_设计与任务书审计及开工准备报告.md`
11. Issue #409 原文或其已归档的审计摘录。

历史 TagUI、P1 Qwen 探针、已完成人工评分和已完成真实资源报告可以复用其事实、SHA、revision 和边界；不要重复执行没有新问题的相同实验。历史 combined 证据只能作为旧契约记录，不能当作本版完成门。

## 当前契约和产品边界

- 页面一级分类按运行方式：本地模型 / API 服务；Tag 和自然语言 Caption 是模型能力。
- 主流程是：选择数据集 → 选择模型 → 模型专属参数/提示词 → 单图试标 → 批量打标 → 结果/编辑器。
- 模型按系列折叠、可搜索、收起后显示具体型号并显示下载/就绪状态。
- 参数随模型 capability 展示和校验；请求不能携带不适用参数，后端必须再次拒绝。
- Caption prompt 预设存放在 `user_data/presets/`，使用 `kind=caption_prompt`，与训练预设隔离；模板保存、另存为、恢复默认和未保存修改保护必须完整。
- 首版不实现、不展示、不验收 combined/mixed、Tag+Caption 串联、WD+Caption 双模型或本地+API 联合流水线。
- 已有 mixed provenance 只允许兼容读取和安全编辑；首版新任务不得生成 mixed。
- 没有可用 API Profile 时不显示空 API 入口；API 后端能力可以保留，但 UI 必须由实际可用 capability 驱动。
- Agent、sidecar、provider、plugin marketplace 及其测试不属于本任务，禁止修改或纳入完成门。

## 统一 LLM 和安全边界

- 翻译和自然语言打标共用 Profile、asset、runtime、cache、revision、connection test 和密钥掩码。
- 翻译Profile只需text；Caption模型目录必须有vision/caption，所引用共享Profile必须有vision，保持既有text/vision Profile schema。逻辑supports_*能力在线上目录使用capabilities数组与runtime表达；后端目录/模型选择、Profile与实际响应均需校验。
- 已配置远程视觉 Profile 时生产路由始终 remote-first；本地模型只在用户明确启用 fallback 且远程失败时使用。
- API Key 只能在后端运行时注入；不得写入配置明文、前端、预设、任务档案、日志、报告、截图、Git 或环境文件。
- 远程请求只传受限 JPEG data URL，不传本地路径、文件名、数据集名称、EXIF 或原始响应。
- Tag 使用既有逗号清理/排序逻辑；自然语言按整段文本保存，不能被拆 Tag、排序、去重或下划线转换。
- 写回必须 atomic + before hash；外部变化必须报告 conflict；已有 caption 默认跳过，覆盖必须明确。

## 阶段执行顺序

严格按 Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 执行。每一阶段开始前读取对应开工清单，完成后更新 canonical task book、design、goal、manifest、阶段清单、证据和 progress ledger。硬门失败时生成 failure report，不能用口头说明跳过。

### Phase 0：契约收敛

- 建立 Issue #409 差异表，明确保留、迁移、删除和历史兼容项。
- 从设计、任务、goal、manifest、总控和目标计划中移除首版 combined/mixed 硬门和 Agent 范围。
- 审计 `TaggerPage`、`caption_api.py`、`caption_job.py`、模型注册表、LLM prompt preset 和现有 user_data CRUD。
- 冻结 runtime-first/model-first API schema、capability schema、preset schema 和 API 动态入口规则。
- 完成门：canonical 文档一致，代码差异表完整，无未授权 P0/P1。

### Phase 1：统一 LLM、模型和预设契约

- 保持旧翻译配置迁移、旧翻译 API、旧 Tag API 和密钥掩码。
- 实现/补齐模型 capability、系列/搜索/下载状态、模型专属参数 schema。
- 将 Caption 预设落到 `user_data/presets/`，按 `kind=caption_prompt` 隔离训练预设；提供兼容迁移和跨进程读取。
- 后端拒绝 text-only Profile 进行 Caption，拒绝不适用参数；缓存 revision 包含 prompt/model/asset/参数/输入 hash。
- 保持 remote-first 和显式 local fallback；无 API 不渲染空入口。
- 完成 Unit、Contract、Gray 和 fake text/vision 验证。

### Phase 2：Tag/Caption 后端任务链路

- 保持 `/api/interrogate` 的 Tag 兼容，Caption 使用 `runtime + model + capability + output` contract。
- 实现受限图片预处理、严格 JSON、语言/长度/不臆测、prompt snapshot、cache、持久任务、报告、取消、失败项重试。
- 保持 Tag formatter 与 natural formatter 分离；`output=combined` 必须拒绝，不得新建 mixed。
- 验证已有 caption 跳过/明确覆盖、训练占用、before hash、atomic write、rollback/clear、冲突和恢复。
- 用 fake endpoint 覆盖成功、非法 JSON、超时、429、取消、部分失败、重试和恢复；运行低限额本地视觉真实路径。

### Phase 3：前端、Dataset Editor 和 user_data

- 将 TaggerPage 调整为数据集、运行方式、模型、专属参数/提示词、输出、底部进度。
- 移除 combined/mixed 入口和布局选择；按 capability 展示 Tag 或 Caption。
- 实现模型系列折叠、搜索、具体型号、下载状态、参数隔离、API 动态入口。
- 实现 Caption 预设保存、另存为、恢复默认、未保存保护和训练预设隔离。
- 验证单图试标不写盘，批量/取消/失败重试/历史/隐私提示，桌面/390px/Tab/Escape/空配置/错误。
- Dataset Editor 对 natural/unknown/历史 mixed 保留原文安全，Tag 操作不能破坏自然语言。
- 完成 Node 22 check、typecheck、lint、Vitest、build 和浏览器手测。

### Phase 4：真实资源和发布前审计

- 冻结公开/脱敏样本、URL、SHA、许可证、模型 revision、prompt/preset revision。
- 完成本地 Qwen3-VL 视觉 Caption 三样本真实运行和资源记录。
- 若存在远程 Profile，完成 remote-first、strict JSON、缓存重放和显式 fallback；未配置则诚实记录未运行。
- 完成真实 WD/ONNX Tag 灰度；不执行 combined 作为本版验收。
- 完成 EDD 质量规则和人工评分，评分绑定实际输出；完成 Zero-Short、rollback/clear、隐私扫描和用户文档。

### Phase 5：全新隔离重建

- 从最新提交建立全新 worktree 或干净源码 checkout。
- 创建全新 Python 3.11 venv、Node 22 node_modules、frontend dist、配置、SQLite、cache、queue、output。
- 重新从公开 URL 下载样本、模型/runtime/mmproj 和 ONNX Tag 资产，记录 SHA；禁止复用旧 sandbox、旧模型、旧 DB、旧输出和未提交文件。
- 正式 lifespan 启动并完成空配置 Zero-Short；完成本地 Tag、自然语言 Caption、预览不写盘、取消、失败重试、冲突保护、原子写回和 Dataset Editor 安全。
- 如果存在远程 Profile，重复 remote-first 和显式 fallback；如果没有凭据，标记 remote real 为未配置，不伪造通过。
- 运行完整前后端测试、构建、隐私扫描、清理和人工验收。隔离环境任何失败都要回到对应阶段修复，然后建立新的 fresh root 重跑。

## 必测矩阵和证据

必须保存实际命令、commit、环境、输入样本 SHA、模型/prompt revision、结果、资源、错误和清理状态：

- Unit：配置迁移、preset schema、mask/revision、capability、图片压缩、formatter、cache、atomic writer。
- Contract：LLM/Tag/Caption API、错误码、任务状态、旧接口、掩码 Key、user_data preset CRUD。
- Integration：fake text/vision、remote-first/fallback、local readiness、cache、取消、重试、冲突和 Editor。
- Gray：旧 Tag 与新 Tag 逐文件比较；旧翻译 facade 与统一服务比较。
- Frontend：Node 22 check/typecheck/lint/Vitest/build、浏览器和窄屏/键盘验收。
- Real：本地 Qwen3-VL-2B 三张公开/脱敏样本；已配置远程时真实 remote-first。
- EDD：冻结样本、规则、人工评分、失败样本和 revision baseline。
- Zero-Short：无 Key、无词库、无视觉模型时可启动且有清晰可操作提示。
- Isolated rebuild：全新目录重复关键链路和清理。

某项不适用或未配置必须记录原因、替代检查和批准人；skip 不能自动等同 pass。Windows symlink 权限、真实 API 凭据和模型下载限制必须如实记录。

## 失败、权限和变更处理

- 发现 Agent/plugin 代码或计划重新进入范围，立即停止相关工作并删除越界内容。
- 发现 combined/mixed 新入口、空 API 入口、能力绕过、明文 Key、自然语言被 Tag 清理或无 hash 写回，生成 failure report，不得进入下一阶段。
- 普通实现取舍、测试修复、文档同步自主完成；仅未授权 P0/P1、不可逆数据操作、凭据边界、资源不可得且无替代路径时暂停报告。
- 重大变化必须同步 design、task book、goal、manifest、目标计划、阶段清单和 change-control；不得静默削弱完成门。

## 最终完成标准

只有同时满足以下条件才能把 task book、manifest 和最终复盘标记为 complete：

1. model-first 页面、Tag/Caption 能力、模型专属参数和动态 API 入口符合 Issue #409；
2. Caption 预设位于 user_data 并与训练预设隔离，保存/另存为/恢复默认/未保存保护通过；
3. 后端、前端、Dataset Editor 和共享 LLM 均实现并通过相应 contract；
4. 首版没有 combined/mixed 创建入口，历史 mixed 只做兼容保护；
5. remote-first 和显式 local fallback 在可用资源下可复现；
6. 完整矩阵、真实资源、EDD、人工、Zero-Short 和隐私清理都有实际证据；
7. Phase 5 fresh rebuild 从零通过，失败后没有在同一失败根目录修补式宣告完成；
8. Agent/plugin/sidecar 不在代码、计划、验收或交付范围；
9. 未授权 P0/P1 为零，所有失败/skip/未配置项有准确状态和证据。

最终报告必须列出实际变更文件、每条验证命令及结果、模型/样本边界、隔离路径、清理结果、剩余风险和维护动作。任何条件未满足都必须标记未完成并继续执行。

## 2026-10-08验收附记

2026-10-08当前验收：候选8986b9e功能/前后端/真实模型/人工评分/正式Zero-Short及第五次全新重建已通过。前端342/52，后端Windows512+Linux四原case覆盖516项/0skip，四项平台口径获用户批准；本轮远程未配置并如实记录。唯一剩余为Windows五个临时根清理，自动审批以blocked by policy拒绝递归删除，正在等待用户手动清理或明确保留例外。源码worktree、Linux根与自建进程已清理。整体goal未complete，GATE10/G-11 cleanup pending。详见phase-5-isolated-rebuild/2026-10-08-final-acceptance-audit.md。

公开OpenAPI不能声明首版不支持的combined或组合layout值；候选已补schema合同并在新环境复验。此前用户评分/平台批准不自动扩大为后续清理例外；当前只剩该处理结果。其余目标、完成标准与禁止事项保持完整。
