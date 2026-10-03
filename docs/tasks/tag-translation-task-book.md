## 计划元数据
- Plan ID: DATASET-MODULE-20260930
- Version: v5-review-hardening-complete-pending-user-review
- Last updated: 2026-10-02 Asia/Shanghai
- Canonical progress file: `docs/tasks/tag-translation-task-book.md`
- Latest acceptance report: `docs/tasks/tag-translation-installation-acceptance-report.md`
- Related handoff file: none
- Current branch: `feat/tag-translation`
- Current active phase: R6 自动化与隔离验收
- Execution readiness: complete pending user review
- Active Goal: `01a0c916-e274-7412-9950-a0d41c633bdf`
- V5 review/design: `docs/design/tag-translation-v5-review-and-hardening.md`
- V5 acceptance report: `docs/tasks/tag-translation-v5-acceptance-report.md`

## 目标
在 Next Trainer 中完成数据集模块状态保持和编辑器恢复。标签中文释义作为 Dataset Editor 的一个资源缓存域继续建设：优先使用 Danbooru 词库，支持免费网络翻译和 OpenAI 兼容 LLM 兜底；同时记忆上次打开的数据集，保留编辑草稿、当前图片、筛选和翻译状态。原始英文标签、caption、打标结果、训练配置和导出内容保持不变。

## 范围与约束
- In scope:
  - 所有翻译配置与词库/小模型下载、安装、启停、失败重试统一放在“翻译设置”入口。
  - 修复 locale/profile/cache epoch、自动回退结果合并、失败永久屏蔽和粗粒度进度缺口。
  - 修复从 Dataset Editor 切换到 Tasks/Settings/Training 后返回，数据集和编辑内容被清空的老 BUG。
  - 建立 Dataset Editor session 状态，记忆上次数据集路径、当前图片、未保存 caption 草稿、选择、筛选和翻译展示状态。
  - 按数据集根路径隔离草稿和资源，支持浏览器刷新后的路径恢复与重新扫描。
  - 按全局缓存生命周期设计迁移资源缓存、请求取消和持久化 key 的边界。
  - 迁移并适配 Aaalice 的词库下载、SQLite 查询、翻译调度、缓存和 LLM 响应校验。
  - 接入 Next Trainer FastAPI 和 Dataset Editor Vue 页面。
  - 支持 Danbooru 词库、MyMemory 可选 provider、本地 Qwen OpenAI 兼容服务和远程 LLM API。
  - 建立下载校验、隐私、失败回退、原文保护和测试证据。
- Out of scope:
  - 修改打标模型输出或 caption 文件。
  - 把中文释义写入训练数据。
  - 独立翻译数据库管理后台。
  - 将所有前端页面改造成全局 KeepAlive；页面临时 UI 状态仍按页面语义清理。
  - 直接迁移 ComfyUI 页面和 DOM 监听。
  - 直接复制 WeiLin GPL-2.0-only 实现。
- Constraints:
  - 只在 `project/.runtime/tag-translation-wt` worktree 和 `feat/tag-translation` 分支施工。
  - 主工作目录保持不变；不得把词库二进制提交进仓库。
  - Aaalice 迁移文件保留 MIT 版权与来源说明。
  - 网络 provider 和 LLM 必须可选，默认不向外部发送标签。
  - 所有翻译结果只进入 UI 辅助状态。
  - 每个阶段完成后更新本任务书和验证证据。

## 执行阶段
### Phase 1: 迁移审计与探针
- Purpose: 固定可迁移来源、许可证、模块依赖和 Next Trainer 适配边界，避免重复造轮子或把 ComfyUI 耦合带进来。
- Outputs: 迁移清单、来源快照、第三方说明、词库探针结果、阶段决策。
- Completion criteria: 已确认 Aaalice 模块依赖；已确认 ffdkj SQLite schema/下载方式；已完成至少一个本地词库查询探针；迁移清单中每个源文件都有“直接迁移/改写/不迁移”结论。
- Validation: 运行源码依赖扫描、SQLite schema 查询、固定 tag 样本查询、许可证和 git 状态检查。
- Evidence: `docs/tasks/tag-translation-migration-inventory.md`、探针输出和本任务书进度更新。

### Phase 2: 后端翻译服务迁移
- Purpose: 在 Next Trainer 后端形成统一的词库、网络和 LLM provider 服务。
- Outputs: `mikazuki/tag_translation/` 模块、FastAPI 路由、用户数据路径和配置接口。
- Completion criteria: Danbooru provider 可查询；MyMemory 可选 provider 可处理成功/失败/超时；OpenAI 兼容 LLM 可返回严格校验结果；自动回退顺序稳定。
- Validation: Python 单元测试、provider mock 测试、真实词库下载/查询探针、网络接口最小验收。
- Evidence: 测试报告、provider 响应样例、错误码和接口契约。

### Phase 3: Dataset Editor 前端迁移
- Purpose: 在现有英文 tag chip 上增加非持久化中文释义展示。
- Outputs: API client、翻译 composable、chip/tooltip 展示、设置入口和 i18n 文案。
- Completion criteria: 原始 caption 保存前后不变；切换图片不会串入旧请求；provider 状态、loading、missing、error 可见；可关闭外部 provider。
- Validation: Vue 单元测试、组件测试、`npm run check`、生产构建和人工页面验收。
- Evidence: 测试输出、页面截图或验收记录、caption 原文对比。

### Phase 4: 端到端验证与质量收口
- Purpose: 验证迁移代码在真实项目路径中不会影响打标、编辑、训练和发布包。
- Outputs: 端到端验收记录、性能/失败回退数据、敏感信息扫描和第三方说明。
- Completion criteria: 本地词库断网可用；所有 provider 失败仍可编辑和训练；原始 caption 完整保留；无 Key/路径泄露；构建和相关测试通过。
- Validation: Python/前端相关测试、断网模拟、LLM 错误响应模拟、git diff 检查和敏感信息扫描。
- Evidence: `docs/tasks/tag-translation-validation.md`、最终测试命令和结果。

### Phase 5: 发布准备与维护交接
- Purpose: 让后续版本能更新词库、provider 和迁移代码而不丢失上下文。
- Outputs: 用户配置说明、词库更新说明、维护者文档、发布边界和 handoff 信息。
- Completion criteria: 第三方许可、词库来源、配置迁移、回滚方式和后续维护动作都有文档；任务书标记 complete。
- Validation: 干净 worktree、文档链接检查、安装/升级路径检查。
- Evidence: 发布说明、维护手册和最终任务书。

## 决策记录
- Verified facts:
  - 当前专用 worktree 为 `project/.runtime/tag-translation-wt`，分支为 `feat/tag-translation`。
  - 最新远端 dev 基线为 `fb997d4`；设计书已提交为 `2dd0d31` 和 `29fcea0`。
  - Aaalice 快照 `37cabccf9b4d799b7b53a1e2d74f2cd214fe91d0` 使用 MIT License，已有词库、翻译服务、缓存和 API 模块。
  - WeiLin 参考仓库的 LICENSE 为 GPL-2.0-only，不直接复制其实现。
  - Next Trainer 当前 Dataset Editor 在 `mikazuki/dataset_editor.py` 和 `frontend/src/pages/DatasetEditorPage.vue`。
  - 当前主工作目录存在既有未跟踪 `mikazuki/dataset-tag-editor/`，不属于本分支施工内容。
- Active assumptions:
  - ffdkj `tag.sqlite` 可以按需下载到用户数据目录，并允许用户侧使用；正式再分发前仍需审计许可。
  - Qwen 0.8B 采用当前官方 `Qwen3.5-0.8B` OpenAI 兼容服务作为实验目标。
  - 首版 provider 配置独立于 Agent 插件，后续再评估 provider 复用。
- Locked decisions:
  - 采用迁移优先，不从零实现翻译调度、重试和 LLM 结果校验。
  - 优先迁移 MIT 许可的 Aaalice 模块；WeiLin 只作行为参考。
  - 原始英文 caption 永远是唯一可写入训练数据的内容。
  - 默认只使用本地 Danbooru 词库；外部网络和 LLM 必须显式启用。
- Open questions:
  - ffdkj 词库最终许可和现场下载 URL 是否长期稳定。
  - Aaalice `translation_store.py` 是否完整迁移，还是首版只用内存缓存。
  - MyMemory 和本地/远程 LLM 的默认 UI 位置与额度提示。
  - Qwen 0.8B 的实际标签翻译质量、吞吐和资源占用。

## 关键制品与环境
- Canonical docs:
  - `docs/design/tag-translation-design.md`: 审计设计与迁移边界。
  - `docs/tasks/tag-translation-task-book.md`: 本任务的唯一进度台账。
  - `docs/tasks/tag-translation-goal-prompt.md`: 新会话续接和执行提示。
  - `development-docs/research/references/ComfyUI-Autocomplete-Aaalice`: Aaalice 参考快照。
  - `development-docs/research/references/WeiLin-Comfyui-Tools`: WeiLin 行为参考快照。
- Important code or output artifacts:
  - `mikazuki/dataset_editor.py`: 后端 caption/tag 数据边界。
  - `frontend/src/pages/DatasetEditorPage.vue`: 前端 chip 展示和原文编辑边界。
  - `mikazuki/app/api.py`: FastAPI 路由入口。
- Required commands:
  - `git -C project/.runtime/tag-translation-wt status --short --branch`: 检查专用 worktree。
  - `python -m pytest -q`: 后端全量基线（阶段收口使用）。
  - `cd frontend; npm run check`: 前端类型和 lint 检查。
  - `cd frontend; npm run test -- --run`: 前端测试。
- Environment baseline:
  - Windows PowerShell；GitHub HTTPS 网络命令必须使用 `127.0.0.1:11809` 代理。
  - 施工只允许在 `feat/tag-translation` worktree。
  - 词库下载、缓存和模型不进入 Git 提交。

## v2.1 优化审计（历史）

- 用户要求：先审核设计，再优化切图持久化、统一 UI、明确免费翻译接口；随后明确指出前端缓存清空是全局生命周期问题，不能只修 tag 翻译。
- 设计制品：[v2 优化设计书](../design/tag-translation-v2-ux-persistence-design.md)。
- 横向设计制品：[前端缓存生命周期治理设计书](../design/frontend-cache-lifecycle-design.md)。
- 核查事实：choose() 关闭显示且清前端缓存；MyMemory 未持久化；只有 MyMemory 免费 provider 已接入。
- 全局核查事实：生产前端未发现无范围的 `localStorage.clear()` 或 `sessionStorage.clear()`；当前主要问题是页面状态、资源缓存、请求取消和持久数据删除没有统一边界。
- 新发现：LLM 行对象未经 text 抽取直接进入字符串字段；原测试缺少非空 LLM 响应覆盖。
- 早期规划中的最长匹配尚未实现；现有词库只做精确查询。需保留原范围缺项，不能由 UI 优化完成声明覆盖。
- 本轮交付：全局缓存生命周期设计文档、tag v2 设计书联动修订；功能代码与正在运行的服务未修改。
- v2.1 implementation: pending，等待用户审阅横向缓存设计和 tag v2 设计；不继承下方 v1 完成记录作为 v2 验收证据。

## v3 数据集模块施工范围（已验收历史，受 v4 缺口审计修正）

- 用户新增要求：任务正式从 tag 翻译上升到数据集模块；查看四张截图后确认，Dataset Editor 从任务模块返回会丢失已打开数据集和编辑状态。
- 复现证据：[01.png](C:/Users/25454/Desktop/新建文件夹/01.png)、[02.png](C:/Users/25454/Desktop/新建文件夹/02.png)、[03.png](C:/Users/25454/Desktop/新建文件夹/03.png)、[04.png](C:/Users/25454/Desktop/新建文件夹/04.png)。
- 设计制品：[数据集模块状态保持与编辑器恢复设计](../design/dataset-module-state-retention-design.md)。
- 施工边界：优先修复 Dataset Editor 的跨路由恢复和草稿隔离，再回收 tag 翻译缓存；不通过全局 KeepAlive 掩盖页面状态问题。
- 当前实现策略：应用级 session 状态 + 版本化持久化 key；数据集内容刷新后重新 scan，未保存 caption 按数据集根路径和相对路径恢复。
- 验收重点：任务页往返、数据集页签往返、浏览器刷新、数据集切换隔离、旧请求竞态和原文保护。
- 已完成实现：`useDatasetEditorSession` 保存数据集路径、根目录、选中项、草稿、翻译偏好、分页和面板状态；`useTagTranslations` 改为应用级 provider/locale/tag 缓存；Dataset Editor scan/choose/save 流程已接入恢复和草稿隔离。
- 已增加验证：session 单元测试、Dataset Editor 卸载后重新挂载的草稿恢复测试；前端类型检查和相关 8 项测试通过。
- 已完成补充：v2 翻译结果 SQLite v2 表、MyMemory/LLM provider profile 隔离、LLM 行对象字符串适配、MyMemory 缓存清理 API、最长规范化查询、统一翻译工具栏与设置弹窗、浏览器翻译缓存恢复。
- 最新修正：中文释义开关现在以整个数据集的唯一 tag 集合为翻译输入，按 500 条分批请求并写入缓存；切换图片只读取缓存，不再出现每张图片逐个补翻译的情况。
- 已完成验证：前端类型检查、Lint、41 个测试文件 253 项测试、生产构建；后端标签翻译/API/词库/缓存专项 8 项通过；Python 语法编译通过。
- 环境限制：后端全量 pytest 在当前 Python 3.14 环境受既有依赖缺失（toml、torch、accelerate）及旧 Pydantic root_validator 兼容错误影响，不能作为本次功能失败证据；专项测试已独立通过。
- 待实机验证：真实浏览器从 Tasks 返回 Dataset、浏览器刷新后翻译缓存、真实 MyMemory/LLM 额度和 Qwen 0.8B 质量；代码和自动化验收已完成，需在目标运行环境进行最后体验验收。

## v4 翻译设置与运行管理（执行中）

- 用户已验收 v3 数据集恢复、全量翻译、UI、进度和筛选译文；已推送 `029d30ab4fe63a8f8aaa7630d1d73f7c498399c3`，未创建 PR。
- 最新要求：编写新设计书补齐词库下载管理、本地小模型安装、自动回退和失败处理；全部相关 UI 位于“翻译设置”。
- 设计制品：[标签翻译 v3：统一设置、下载与本地模型管理设计书](../design/tag-translation-v3-settings-and-runtime-design.md)。文档 v3 与任务书 v4 是不同编号序列。
- Verified facts：目前下载无 UI/日志/重试入口；本地 LLM 仅已有服务接入；locale `zh-CN` 与 `zh` 不统一；LLM 映射替换而非合并；失败状态混同未命中；旧失败表永久阻止同模型重试；前端 N/N 按500项整批更新。
- Active assumptions：受管 llama.cpp+Qwen3.5-0.8B GGUF 作为轻量路线；具体平台发布包、量化文件、版本、资源占用与翻译质量需技术探针锁定。
- Locked decisions：沿用既有分支和台账；UI统一在翻译设置；全数据集翻译；英文原文不改；逻辑词库→MyMemory→LLM，允许缓存先于外部调用；下载和模型资产只进入用户数据目录，不进入 Git。
- Open questions：没有要求用户额外选择的实施项；模型/运行时版本和量化适配由探针确定。设计仍待用户审核。
- 用户已确认采用全部设计建议；Goal `01a0c916-e274-7412-9950-a0d41c633bdf` 已建立并进入全面执行。
- 整体状态：V4-A 至 V4-E 执行中；v3 UI 验收保留为历史证据，新阶段必须补充下载、模型、错误和任务级证据。

### 当前执行阶段（替代新增工作的旧实施阶段，保留历史阶段记录）

| 阶段 | 目的与产物 | 完成条件与验证 | 状态/证据 |
| --- | --- | --- | --- |
| V4-A 契约与缓存修复 | 统一 locale/revision/合并、失败冷却和回退顺序 | 模型切换、重启、缓存优先不联网、迁移幂等测试 | done；v2 SQLite 结果表、profile/in-flight 隔离、locale 规范化、refresh 重试已实现 |
| V4-B 词库与下载管理 | 后台下载任务、终端日志、设置页签、查询解耦 | 首次/失败/取消/重试/旧库保护真实探针 | done；状态/检查/更新/取消/重试 API、设置页轮询、原子安装和 SHA/SQLite 校验 |
| V4-C 本地小模型 | 固定清单、受管运行时/模型安装、启停/健康检查 | Windows CPU真实Qwen标签翻译、进程退出、端口冲突 | done（管理面）；Qwen3.5-0.8B GGUF 与 llama.cpp 自动安装、loopback 启停/健康检查、状态 API/UI 已完成；真实推理需用户在设置页主动安装约 563 MB 模型 |
| V4-D 翻译任务与设置UI | 全量任务、增量N/N、错误汇总、统一设置 | 1586标签混合来源、取消/重试/切图、窄屏 | done；全数据集 500 分批、N/N 进度、缓存持久化、设置中词库/本地模型/LLM 管理 |
| V4-E 统一验收与文档 | 维护说明、发布边界、验收清单 | 原文保护、草稿恢复、相关Python/前端检查、真实服务 | done（代码交付）；验证记录见 docs/tasks/tag-translation-validation.md；Qwen 实机质量验证作为用户安装模型后的可选验收步骤 |

- 本轮改动：补齐下载/取消/重试管理、本地 Qwen GGUF 与 llama-server 管理、配置契约、自动回退错误码和设置页 UI；未把词库或模型二进制提交到 Git。
- 后续缺陷修复：词库下载改用 GitHub API 原始内容入口并保留 raw 备用路径，规避 raw.githubusercontent.com 网络不可达；本地模型改为 Qwen GGUF + llama.cpp 一键安装，运行时自动保存在用户数据目录；LLM 设置改为远程多配置卡片与本地模型统一卡片，远程/本地只能启用一个；本地请求统一代理到主应用的数据集翻译 API，不再让用户填写接口或可执行文件路径。
- 最新回归修复：检查词库后在设置页显示“已是最新/有新版本”；更新下载增加 ghfast/ghproxy 镜像并优先使用，避免多个 GitHub 域名同时不可达；本地模型页签允许进入安装，但未运行前禁止保存启用。
- 端口治理修复：本地模型设置不再显示接口地址或 llama-server 路径；主应用代理地址运行时读取实际 GUI 端口，llama-server 每次启动从操作系统申请空闲 loopback 端口，配置文件不再持久化 28000 或固定内部端口。

## V4 安装与下载专项验收（当前执行）

- 测试计划：[标签翻译下载与安装系统全面测试验收计划](tag-translation-installation-acceptance-plan.md)。
- 初始已知缺陷及结果：
  - 词库已是最新时更新按钮仍可点击，且 API 仍接受无必要的更新任务：已修复并在隔离
    浏览器中确认按钮禁用，API no-op。
  - Qwen 模型只尝试 Hugging Face 主站：已改为 hf-mirror.com 优先、主站备用。
  - llama.cpp v0.5.0 无可用 Windows server 资产：已改为 b11327 Windows CPU x64，
    并完整解压 DLL 依赖。
  - 进程重启后再次安装会长期停留 installing：已修复并加入回归测试。
- 已锁定修复方向：
  - 已是最新时 UI 禁用更新按钮，后端也拒绝无更新任务。
  - Qwen 下载使用 hf-mirror.com 优先、huggingface.co 备用。
  - llama.cpp 改用 b11327 Windows CPU x64 资产，并使用 ghfast/ghproxy/GitHub 备用入口。
  - 安装完成后自动启动、健康检查、动态端口分配和失败重试。
- 新阶段状态：

| 阶段 | 目的 | 状态 |
| --- | --- | --- |
| T1 测试计划与契约修复 | 建立测试矩阵、修复已知状态和资产契约 | done；计划与状态契约已落实 |
| T2 下载器模拟与故障注入 | 覆盖超时、镜像、校验、取消、重试、旧库保护 | done；专项测试 24 项通过，取消/重试/旧库保护有隔离证据 |
| T3 一键安装运行时 | 实际模型/runtime 安装、自动启动、健康检查、动态端口 | done；Qwen GGUF、b11327 runtime、健康检查和动态端口已实测 |
| T4 UI 全组件验收 | 翻译设置全部按钮、互斥模式、缓存、回退、进度 | done；Playwright 隔离浏览器逐项验收通过 |
| T5 隔离目录重装验收 | 全新 clone、全新 data、启动和真实翻译链路 | done；隔离 source/data 和 Dataset Editor 真实链路通过 |
| T6 交付收口 | 证据、任务书、测试报告、提交推送 | done pending user review；验证记录和证据路径已补齐 |

- 下一步动作：等待用户验收；如确认通过，再按发布流程创建 PR。当前不创建 PR。

## V5 Review 与用户体验/稳定性加固（当前 Goal）

- 用户已确认 V4 验收通过，要求再次 review 并自主完成前端体验和多模式稳定性加固。
- Review 结论与复现记录见：[V5 Review 与加固设计书](../design/tag-translation-v5-review-and-hardening.md)。
- 已确认的真实问题：
  - 新增未保存 tag 不会进入筛选标签列表；
  - 中文释义开关开启时新增 tag 不会自动补译；
  - 远程 profile 全部展开，多接口时操作成本高；
  - 停止本地服务后没有引导切换远程或重新启动；
  - 远程未配置时选择 LLM provider 没有前置提示；
  - 设置弹窗取消后可能残留未保存的模式/profile 草稿；
  - 多模式切换缺少统一的旧请求清理、状态提示和回归覆盖。

### V5 阶段与门禁

| 阶段 | 产物 | 完成条件 | 状态 |
| --- | --- | --- | --- |
| R1 Review 与任务拆解 | review 设计书、任务矩阵、Goal | 已复现已知问题并锁定验收标准 | done |
| R2 草稿标签索引 | 会话草稿 tag 合并索引 | 新增/删除/原文编辑后筛选即时同步，保存前不污染服务器 | done；新增 tag 可显示并命中筛选 |
| R3 新增 tag 自动补译 | 增量翻译调度与 debounce | 开关打开时新增未命中 tag 自动请求，显示正确 N/N，不重复请求 | done；实测 `2/2 → 3/3` |
| R4 设置 UX | 折叠 profile、单选、取消恢复、状态引导 | 远程多卡片易操作，本地停止/远程缺配置均可操作恢复 | done；浏览器实测通过 |
| R5 模式切换稳定性 | 配置快照、请求边界、错误提示 | Danbooru/MyMemory/LLM/本地/自动回退切换无旧响应串线 | done；快照、generation、provider cache 隔离保留 |
| R6 自动化与隔离验收 | 测试、报告、全新启动环境 | 相关测试通过；全新隔离目录只启动不额外安装，完成所有按钮和组件验收 | done pending user review；最终地址已启动 |

### V5 执行约束

- 不改变训练 caption 原文保存规则；中文释义只进入 UI 和翻译缓存。
- 不把用户模型、词库、缓存或隔离数据提交到 Git。
- 远程 profile 的 API Key 保持掩码和原有持久化语义。
- 任务完成后新建全新隔离目录，从零启动项目；最终环境不执行依赖安装，只使用项目已有依赖，并把手动验收地址交给用户。已完成：`project/.runtime/tag-translation-v5-final-acceptance-20261003`。

## V5 验收后热修复（2026-10-03）

- 复现：保存远程 LLM 设置后，前端清空了全部翻译缓存，但没有重新触发全数据集翻译；开关仍开启，中文释义短时间或持续消失。
- 修复：设置保存和“清理网络/LLM缓存”现在只清理 MyMemory/LLM/自动回退结果，保留 Danbooru 词库结果；保存成功后自动重新查询当前数据集。
- 修复：进度显示增加未命中数量，例如 `1032/1032（未命中 1 条）`，避免把失败/未命中误读为所有标签都有中文释义。
- 真实验证：在 97 张数据集上保存 LLM 设置后，译文仍保留；`AellaStella`、`1girl` 等释义正常显示，未命中 tag 被明确统计。
- 自动化结果：前端 41 个测试文件、255 项通过；后端翻译专项 25 项通过；生产构建通过。

## v1 进度台账（历史记录，受上述审计修正）
- Overall progress: 标签释义功能、provider、LLM 配置、Dataset Editor 展示、真实接口和浏览器交互验收均已完成，发布审计记录已建立。
- Phase 1: done
- Phase 2: done
- Phase 3: done
- Phase 4: done
- Phase 5: done
- Validation status: Python 编译、路由导入、后端标签翻译测试 8 项、Dataset Editor 相关后端测试共 24 项、前端 typecheck/lint、前端 40 个测试文件 250 项测试和生产构建已通过；MyMemory 实际调用返回“蓝眼睛”；真实运行服务完成词库现场下载（330,414 行）并通过 `/api/dataset-editor/tag-translations` 返回蓝瞳/长发；真实 MyMemory provider 返回蓝眼睛；原文保护 mock 已通过。Edge CDP 浏览器交互验收已完成；发布构建产物保留既有 Node 版本约束，未在本分支提交本地 Node 24 hash 产物。
- Residual risks: Qwen 0.8B 真实模型质量尚未在本机启动；Node 24 构建会产生 dist hash 漂移，发布构建应使用项目规定 Node 版本；这些边界已记录在发布审计。

## 下一步动作
V5 R1～R6 及验收反馈热修复已完成，用户已验收通过；当前分支进入面向 `dev` 的 PR 收口流程。

## V5 验收反馈热修复（2026-10-03）

- 首次使用时，若 Danbooru 词库尚未安装且没有可用远程/本地 LLM，Dataset Editor 的“中文释义（全数据集）”开关现在会禁用，并显示先进入“翻译设置”下载词库或配置 LLM 的提示；已有会话残留的开启状态也会自动关闭。
- 本地 Qwen 安装卡片现在区分模型下载和 llama.cpp 运行环境安装，显示运行时自己的下载进度；运行环境安装未完成时不会误导用户点击启动服务。
- 本地服务健康检查从 10 秒延长到 60 秒，适配 CPU 首次加载 GGUF 的慢启动；启动失败会保留 llama-server 的错误尾日志，并将状态标记为 error，便于重试和排障。
- 本地启动 API 在安装尚未完成或资源不存在时返回明确的 409 提示，不再把“尚未安装”和“启动失败”混成普通成功响应。
- 验证：翻译相关后端测试 26 项通过；前端 typecheck、lint、289 项测试和生产构建通过；隔离实例 `tag-translation-zero-start-acceptance-20261003` 的空白数据目录状态为词库 missing、LLM 未配置、本地模型 missing，前端运行于 `http://127.0.0.1:5197`，后端运行于 `http://127.0.0.1:7946`。
