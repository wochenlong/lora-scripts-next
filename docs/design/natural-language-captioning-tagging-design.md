# 数据集模型打标与自然语言 Caption 设计书（Issue #409 对齐版）

2026-10-08当前验收：候选8986b9e功能/前后端/真实模型/人工评分/正式Zero-Short及第五次全新重建已通过。前端342/52，后端Windows512+Linux四原case覆盖516项/0skip，四项平台口径获用户批准；本轮远程未配置并如实记录。唯一剩余为Windows五个临时根清理，自动审批以blocked by policy拒绝递归删除，正在等待用户手动清理或明确保留例外。源码worktree、Linux根与自建进程已清理。整体goal未complete，GATE10/G-11 cleanup pending。详见phase-5-isolated-rebuild/2026-10-08-final-acceptance-audit.md。


2026-10-08实施补充：Tag与自然语言前端共用既有/tagger/jobs持久化任务、TaskManager maintenance lane及user_data/tasks/dataset-tagger日期/UUID档案；SQLite是执行/恢复权威，TaskManager与task.json是状态投影，不增加调度器。冻结config/task/SQLite成功后才启动推理。任务页停止通过协作回调实际取消，历史失败项重试读取原配置，重启仅恢复状态。Tag单图试标复用批量模型与后处理，原生调用结束并卸载前保持共享占用；预览不写盘。新API请求和公开快照按Tag/Caption能力隔离。删除任务页记录隐藏投影且重启不复活，保留数据集/模型/档案；打标页历史清理另删除SQLite备份并保留图片/当前标注。实现与当前验证见2026-10-08-task-archives-bridge.md和2026-10-08-tag-preview-durable-ui.md；真实模型与浏览器已通过当前实现验证；最终完成门以隔离重建证据为准。

## 1. 文档状态与契约来源

- 计划 ID：`DATASET-NL-TAGGING-20261006`
- 版本：`v3.0-issue-409-aligned`
- 更新时间：2026-10-07 Asia/Shanghai
- 当前分支：`feat/NL-Captioning`
- 维护者契约：[Issue #409](https://github.com/wochenlong/lora-scripts-next/issues/409)
- 相关总单：#365 数据集工作区；任务存储契约与 #405 对齐
- Canonical progress：`docs/tasks/natural-language-captioning-task-book.md`
- 本版性质：在保留已验证实现证据的基础上重新冻结首版范围；Issue #409 优先于此前把组合打标列为首版交付的旧设计。

Issue #409 的产品原则是：沿用目录、模型、参数、开始打标的老流程；一级分类按运行方式（本地模型/API 服务）；Tag 与自然语言 Caption 是模型能力；模型参数按能力显示；提示词预设存储在 `user_data/presets/`；首版不实现混合标注，也不展示不可用的 API 入口。

## 2. 产品目标

在现有 Dataset Tagger 页面中提供可验证的模型打标流程：用户先选择数据集、运行方式和具体模型，再根据模型声明的能力执行 Tag 或自然语言 Caption。WD/CL Tagger 的既有行为保持兼容；Qwen3-VL 等视觉模型可以生成自然语言描述；标签翻译与 Caption 共用 LLM 管理层，但翻译 profile 不要求视觉能力。

首版主流程：

```text
选择数据集 → 选择运行方式 → 选择具体模型 → 模型专属参数/提示词
→ 单图试标 → 输出设置 → 批量打标 → 查看结果/进入标签编辑
```

远程 LLM 的路由原则仍为优先：当存在已配置且具备 `vision` 能力的远程 Profile 时，生产请求优先使用远程；只有用户明确打开本地兜底，且远程请求失败，才启动本地视觉模型。Issue #409 要求 API 不可用时不能展示空入口，因此 UI 仅展示真实可用的 API Profile；后端通用 API 能力可以保留，但“未配置 API”不构成空白功能入口或本阶段阻塞。

## 3. 首版范围

### 3.1 In scope

- 现有 Tagger 页面内的模型/运行方式优先 UI。
- WD/CL Tag 输出兼容，包括旧参数、阈值、标签处理和旧 `/api/interrogate`。
- 具备 `vision` capability 的本地或远程模型生成自然语言 Caption。
- 模型分组、搜索、当前系列默认展开、具体型号显示、已下载状态。
- 模型专属参数；切换模型保留各自草稿，但请求和后端校验拒绝不适用参数。
- 默认提示词、编辑、保存修改、另存为、恢复默认、未保存修改保护。
- `user_data/presets/` 中的 `kind=caption_prompt` 预设，与训练预设隔离。
- 单图试标和批量打标复用同一配置渲染与执行链路；试标不写回文件。
- 默认跳过已有标注、用户明确覆盖、单文件失败隔离、仅重试失败项、停止保留已完成结果。
- 服务端持久任务、刷新后查询、配置/提示词快照、报告、取消、缓存、原子写回和 before hash 冲突保护。
- Dataset Editor 对 Tag、自然语言、未知来源文本的安全处理；自然语言不套用 Tag 清理。
- 翻译与打标共享 Profile、密钥边界、资产/运行时、缓存和连接测试。
- Unit、Contract、Integration、Gray、Frontend、Real、EDD、Zero-Short 和隔离重建验收。

### 3.2 明确不属于首版交付

- Tag + Caption 串联的组合打标；不显示 `combined`、`mixed`、`tags_then_caption`、`caption_then_tags` 等入口。
- WD + Caption 双模型流水线、本地 + API 联合流水线。
- 为未来 API 预留但当前不可用的空表单、假模型或“即将可用”按钮。
- 让语言模型替代 WD/CL 生成训练 Tag。
- 新建独立打标产品、独立进程或独立端口。
- Agent、sidecar、provider、plugin marketplace 或其他 Agent 接口改造。
- 把 API Key 写入前端、日志、预设、任务快照、Git、环境文件或截图。
- 多任务并发调度和无明确用户选择的批量覆盖。

### 3.3 兼容性说明

当前代码中已经存在的 `mixed` provenance、格式识别和防误清理逻辑可以作为向后兼容保护保留，用于读取历史或外部产生的文件；首版新任务不得生成 `mixed`，前端不得提供创建入口，验收也不要求组合链路。历史 evidence 中曾执行过的 combined 验证只能作为历史记录，不能作为本版完成条件。

## 4. 页面和交互设计

### 4.1 运行方式和模型选择

一级选择是：

- **本地模型**：WD/CL Tagger、本地视觉 Caption 模型或受管本地 OpenAI-compatible 服务。
- **API 服务**：只有至少存在一个已配置、已就绪且声明相应 capability 的 Profile 时才显示；未配置时不显示空入口。

模型选择器按模型系列折叠，例如 WD 系列、Qwen-VL 系列。系列作者作为辅助信息；不同用途的模型不能只按作者机械合并。当前系列默认展开，其余折叠；搜索原始模型名时自动展开匹配结果。收起后显示具体型号和下载/就绪状态，不只显示系列名。

模型 ID、旧配置语义和现有 Tag 参数保持不变。模型目录中的 `capabilities` 是后端能力声明的来源，前端展示只是投影，不能用 UI 标签伪造视觉能力。

### 4.2 模型能力和专属参数

能力至少包括：

```text
supports_tag
supports_caption
supports_vision
supports_text
transport: local | api
```

以上是逻辑能力名称，线上模型目录用capabilities字符串数组（tag/caption/vision/text）、runtime（local/api）、downloaded/ready及parameters表示，不新增重复布尔字段。共享LLM Profile保持既有text/vision schema；Caption能力由视觉模型目录与生成adapter表达，后端对Profile的vision、目录output/capability和实际响应分别校验。

WD/CL 模型显示适用的 Tag 参数，如一般/角色标签阈值、标签处理选项。视觉 Caption 模型显示其支持的生成参数、语言、长度、温度/采样等实际能力和提示词编辑器。翻译模型只显示文本参数。

切换模型时保留各自草稿设置，但提交请求前根据模型 capability 过滤字段；后端再次校验，收到不适用参数必须返回稳定错误码，不得静默忽略或把参数传给模型。

### 4.3 提示词编辑

内置模板和用户预设分开。内置模板更新不能覆盖用户预设。切换模板时若有未保存修改，必须提示保存、放弃或取消。默认模板应说明描述范围、输出语言、详细程度和“不臆测”。

预设归属：

```text
user_data/
  presets/
    <stable-id>.json
```

Caption 预设使用 `kind=caption_prompt`，训练预设使用既有类型/元数据；两个列表和 CRUD 不能交叉加载。建议字段：

```json
{
  "id": "caption-default-zh",
  "kind": "caption_prompt",
  "name": "中文主体描述",
  "template": "请客观描述图像中可见的主体、动作、环境和构图。使用{{language}}，不要臆测不可见事实。",
  "system_prompt": "只描述图像可见事实。",
  "output_format": "plain_text",
  "language": "zh-CN",
  "model_capabilities": ["vision", "caption"],
  "revision": "..."
}
```

`user_data/settings.json` 只保存默认预设 ID 等非敏感设置；任务档案保存实际渲染后的 prompt、参数、模型 revision 和 preset revision 快照。任何预设和任务档案都不得包含 API Key。

### 4.4 试标、批量和底部进度

单图试标与批量任务使用同一个配置解析、能力校验、prompt snapshot、视觉请求和 formatter。试标只返回预览，不写入 caption 文件、不改变历史和 undo 栈。

批量任务在内容区底部显示当前阶段、成功/跳过/失败数量、进度、开始和停止。日志默认折叠，模型下载状态显示在模型旁，高级设置中再显示下载源。取消后保留已完成写回，未完成项不写空文件；失败项可以单独重试。

已有 caption 默认跳过；覆盖必须由用户明确选择。训练占用锁和后端 before hash 检查都必须阻止无授权写入。

## 5. 统一 LLM 管理

翻译和自然语言打标共享 `mikazuki/llm/` 的 Profile、能力声明、密钥注入、资产/运行时、缓存、revision 和连接测试。翻译Profile只需要text；Caption模型目录必须有vision/caption，所引用的共享Profile必须声明vision并支持图片请求。API Key仅在后端运行时使用，磁盘配置和响应只保留掩码，重启后重新注入。

缓存 revision 至少绑定 endpoint、model、capabilities、asset revision、推理参数、prompt revision、输入图片 hash 和密钥变更序列，不包含明文 Key。改变模型、能力、参数或提示词后旧 Caption 结果不得复用。

远程视觉请求只发送经过尺寸、质量、格式、体积和 EXIF 限制的 JPEG data URL；不得发送本地绝对路径、数据集名称、文件名或原始响应。远程优先路由必须可观测：报告记录选中的 Profile、revision、fallback 是否发生和错误码，但不记录凭据。

## 6. 后端契约

兼容旧接口：

- `POST /api/interrogate` 继续映射到 `mode=tag`，旧字段和旧输出保持兼容。
- 既有 `/api/tag-translation/*` 继续由共享 LLM facade 提供。

新契约的核心概念是 `runtime + model + capability + output`，而不是首版的 `mode=combined`。Caption 请求示例：

```json
{
  "path": "<server-side path>",
  "runtime": "local",
  "model_id": "llm:qwen3-vl-2b-local",
  "mode": "natural",
  "language": "zh-CN",
  "prompt_id": "caption-default-zh",
  "prompt": "实际渲染后的快照",
  "max_caption_length": 512,
  "max_tokens": 512,
  "temperature": 0.0,
  "conflict_action": "ignore",
  "allow_local_fallback": false
}
```

后端必须从模型注册表读取能力并做严格校验。首版不接受 `output=combined`，不生成 `mixed`。Tag 请求仍可走旧 `/api/interrogate` 或统一 job contract 的 `output=tag` 映射。

任务记录至少包含：数据集标识、模型/运行方式、output、prompt snapshot、参数 snapshot、model/prompt revision、输入 hash、逐文件状态、写回前后 hash、跳过/失败原因、取消时间和报告摘要。公开报告不得包含本地路径、原始图片、Key 或原始供应商响应。

## 7. 数据集编辑器安全

- `tag` 来源可以使用既有逗号拆分、排序、去重和下划线操作。
- `natural` 来源默认按整段文本编辑和保存，不自动拆成 Tag。
- 无来源或外部修改的文本标记为 `unknown`，不得依据短文本猜测其格式。
- 历史 `mixed` 来源只按原文保护和 `actualTags` 投影规则处理，不提供新的 mixed 生成操作。
- undo/redo、批量保存、导出和外部冲突检查都必须保留来源和 before hash。

## 8. 错误、隐私和恢复

错误码至少覆盖：profile 未就绪、能力不支持、prompt 无效、模型未安装、远程超时/429/401、fallback 未启用、取消、文件冲突、训练占用和写回失败。单文件失败不能拖垮整个批次；重试只能提交失败项并保留原始 parent job/快照。

写回采用临时文件、flush/fsync、原子替换和 before hash。rollback/clear 仅作用于本任务写回，保留备份 SHA 和 writer ownership；外部编辑后的文件不能被无提示覆盖。

## 9. 测试和验收门

### GATE-01 契约与范围

设计、任务书、goal、manifest 均声明 Issue #409 为当前契约；首版无 combined/mixed 入口；Agent 不在范围内。

### GATE-02 模型和能力

模型分组/搜索/具体型号/下载状态正确；Tag/Captions 参数隔离；前后端拒绝不适用参数；API 未配置时没有空入口。

### GATE-03 预设和任务

Caption 预设存入 `user_data/presets/` 并与训练预设隔离；保存、另存为、恢复默认、未保存保护和跨浏览器读取通过；单图与批量使用相同快照。

### GATE-04 后端和编辑器

旧 Tag/翻译兼容；Caption strict JSON/语言/长度/不臆测校验、缓存、取消、重试、冲突、原子写回和 natural safety 通过；历史 mixed 仅兼容读取。

### GATE-05 前端和 Zero-Short

Node 22 check/typecheck/lint/Vitest/build 通过；桌面、390px、键盘、空配置和错误提示通过；底部进度无常驻右栏；无 API/无视觉模型时入口可操作且不虚假承诺。

### GATE-06 真实资源

至少完成一个本地视觉模型三样本真实 caption；远程 Profile 若已配置则验证 remote-first、严格 JSON 和显式 fallback。真实 API 是可选配置路径，不将缺少 API 凭据当作首版失败。

### GATE-07 隔离重建

全新 worktree、Python 3.11 venv、Node 22 依赖、配置/SQLite/cache/output、样本和模型资产重新下载；通过空配置 Zero-Short、本地 Tag、自然语言 Caption、取消/重试/冲突/编辑器安全、测试和隐私清理。不得复用旧 worktree 产物。

任何失败必须保留 failure report、命令、环境、输入 hash、输出摘要和清理记录；没有授权不得将 failed/skip 写成 pass。

## 10. 证据和交付

证据根目录：`docs/evidence/natural-language-captioning/`。历史 combined 证据保留但标记为“旧契约历史，不是本版完成门”。新证据必须记录 Issue #409 版本、commit、模型/资产 revision、样本 hash、命令、结果、资源和清理。

完成时交付：后端/API、前端页面、Dataset Editor 安全、预设迁移说明、用户文档、测试矩阵、真实资源报告、Zero-Short、隔离重建报告、隐私扫描和剩余风险清单。没有通过 GATE-01 至 GATE-07 不得宣告完成。

## 2026-10-08 当前实现契约增量

模型目录为GET /api/tagger/models；具体模型id绑定旧Tag id或llm:<profile_id>。新请求保留mode=tag/natural表示输出能力，runtime/model_id/profile_id需一致；生成字段为flat max_tokens/temperature/max_caption_length，与旧接口同源兼容，不额外引入parameters/output别名。实现与证据见phase-0-contract-alignment/2026-10-08-model-catalog-browser.md。Goal active，最终完成门未通过。

2026-10-08契约审计：公开OpenAPI的mode枚举仅natural/tag；layout只列tags_only/caption_only。旧combined和组合layout输入得到明确400，不能作为可选项宣称可用。API、model catalog、前端TS和页面同时遵守首版范围。
