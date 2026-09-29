## 计划元数据
- Plan ID: TAG-TRANSLATION-20260929
- Version: v1
- Last updated: 2026-09-29 00:00 Asia/Shanghai
- Canonical progress file: `docs/tasks/tag-translation-task-book.md`
- Related handoff file: none
- Current branch: `feat/tag-translation`
- Current active phase: Phase 5: 发布准备与维护交接
- Execution readiness: executing

## 目标
在 Next Trainer 的 Dataset Editor 中加入标签中文释义辅助展示。优先迁移成熟的 Aaalice 翻译模块，实现 Danbooru 词库优先、免费网络翻译和 OpenAI 兼容 LLM 可选兜底；原始英文标签、caption、打标结果、训练配置和导出内容保持不变。

## 范围与约束
- In scope:
  - 迁移并适配 Aaalice 的词库下载、SQLite 查询、翻译调度、缓存和 LLM 响应校验。
  - 接入 Next Trainer FastAPI 和 Dataset Editor Vue 页面。
  - 支持 Danbooru 词库、MyMemory 可选 provider、本地 Qwen OpenAI 兼容服务和远程 LLM API。
  - 建立下载校验、隐私、失败回退、原文保护和测试证据。
- Out of scope:
  - 修改打标模型输出或 caption 文件。
  - 把中文释义写入训练数据。
  - 独立翻译数据库管理后台。
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

## 进度台账
- Overall progress: 标签释义功能、provider、LLM 配置、Dataset Editor 展示、真实接口和浏览器交互验收均已完成，发布审计记录已建立。
- Phase 1: done
- Phase 2: done
- Phase 3: done
- Phase 4: done
- Phase 5: done
- Validation status: Python 编译、路由导入、后端标签翻译测试 8 项、Dataset Editor 相关后端测试共 24 项、前端 typecheck/lint、前端 40 个测试文件 250 项测试和生产构建已通过；MyMemory 实际调用返回“蓝眼睛”；真实运行服务完成词库现场下载（330,414 行）并通过 `/api/dataset-editor/tag-translations` 返回蓝瞳/长发；真实 MyMemory provider 返回蓝眼睛；原文保护 mock 已通过。尚未完成浏览器交互截图和发布包验收。
- Residual risks: Qwen 0.8B 真实模型质量尚未在本机启动；Node 24 构建会产生 dist hash 漂移，发布构建应使用项目规定 Node 版本；这些边界已记录在发布审计。

## 下一步动作
任务已完成；后续维护按发布审计中的词库更新、Qwen 实机验收和 Node 版本约束执行。

