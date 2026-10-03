# 标签中文释义设计书

> 后续修订：用户实测反馈后的持久化、统一 UI 和免费翻译入口方案见
> [Tag 中文释义 v2 优化设计书](tag-translation-v2-ux-persistence-design.md)。
> v2 当前待审核，本文件的早期规划不代表所有路径均已完成实测。

状态：Draft（待审计）
分支：`feat/tag-translation`
基线：2026-09-29 的 `origin/dev`（`fb997d4`）
关联需求：[Issue #365](https://github.com/wochenlong/lora-scripts-next/issues/365)
相关需求：[Issue #40](https://github.com/wochenlong/lora-scripts-next/issues/40)、[Issue #210](https://github.com/wochenlong/lora-scripts-next/issues/210)

## 1. 摘要

为数据集打标和标签编辑结果增加中文释义辅助展示。系统优先查询 Danbooru 英中标签词库；词库未命中时，按用户选择调用免费网络翻译或 OpenAI 兼容的 LLM；所有路径都失败时保留英文原始标签。

翻译结果只用于前端阅读和筛选，不写回训练 caption，不改变打标器生成的 `.txt`，不改变批量编辑、导出和训练提交的数据。用户始终可以看到并编辑真实的英文标签。

首版采用“下载一次、只读查询、按需翻译”的设计：词库在用户首次启用时从网络下载到用户数据目录；运行时不把词库提交到仓库，也不要求项目内置大规模数据库。SQLite 仅用于本地词库文件本身，不新增业务数据库表。

## 2. 背景与问题

当前项目已经有：

- WD/CL 模型打标和进度接口；
- Dataset Editor 的 caption 读取、拆分、chip 展示和保存；
- 中文/英文 UI 国际化；
- 现有 OpenAI 兼容图像审核配置；
- Agent 插件的 provider、模型和凭据管理。

当前缺少的是标签语义辅助信息。用户看到 `blue_eyes`、`long_hair`、`hakurei_reimu` 时，需要额外查找含义；直接把 caption 翻译成中文又会破坏训练数据语义。因此需要把“原始标签”和“中文释义”建模为两个独立字段。

## 3. 目标

### 3.1 必须实现

- 对 Dataset Editor 当前图片的标签显示中文释义；
- 默认优先使用 Danbooru 标签词库；
- 支持多词标签的最长匹配；
- 词库未命中时可选择网络翻译；
- 词库和网络翻译仍未命中时可选择 LLM；
- 支持本地部署的 Qwen 0.8B 类 OpenAI 兼容服务；
- 支持远程 OpenAI 兼容 LLM API；
- 原始英文标签始终保留；
- 翻译失败不影响打标、编辑、训练和导出；
- 允许用户关闭任一翻译 provider；
- 显示翻译来源和状态，避免把机器译文伪装成词库释义。

### 3.2 不在首版范围内

- 不自动把中文写入 `.txt` caption；
- 不修改 WD/CL 打标模型输出；
- 不做独立的标签翻译数据库管理后台；
- 不在项目仓库提交约 30 MB 的 Danbooru SQLite 文件；
- 不强制安装本地 LLM；
- 不把远程翻译设置为必须项；
- 不处理整段自然语言 caption 翻译；
- 不对角色名、作品名和艺术家名进行无依据的自动纠正；
- 不把翻译结果用于训练、排序或自动清洗，除非后续需求单独批准。

## 4. 用户可见行为

### 4.1 翻译模式

设置项提供以下模式：

| 模式 | 行为 |
| --- | --- |
| 仅 Danbooru 词库 | 只查本地词库，不产生外部请求 |
| Danbooru + 免费翻译 | 词库未命中时调用用户启用的免费网络 provider |
| Danbooru + LLM | 词库未命中时调用用户启用的 LLM provider |
| 自动回退 | 词库 → 网络翻译 → LLM → 原文 |
| 关闭释义 | 不发起查询，不显示释义 |

默认推荐“仅 Danbooru 词库”。“自动回退”必须由用户显式选择，避免用户不知情地把标签发送到外部服务。

### 4.2 标签展示

Dataset Editor 的标签 chip 仍以英文原文作为主文本：

```text
blue_eyes
蓝色眼睛
```

中文释义使用次级文本或 tooltip 展示。无释义时只显示：

```text
unknown_tag
```

每个释义应携带来源状态：

- `danbooru`：本地词库命中；
- `network`：免费网络翻译；
- `llm-local`：本地 LLM；
- `llm-remote`：远程 LLM；
- `missing`：没有结果；
- `error`：请求失败，可重试。

首版不建议在 chip 上长期显示来源文字，可通过 tooltip、详情或辅助色区分。

### 4.3 原文保护

以下操作只能使用原始英文标签：

- 保存 caption；
- 添加、删除和拖拽标签；
- 批量清理；
- 数据集导出；
- 训练表单提交；
- 任务配置和日志。

中文释义只存在于独立的前端展示状态和翻译响应中。

## 5. 词库来源与下载

### 5.1 首选词库

首选候选：[ffdkj/ffdkj-Danbooru_Tag-Chinese-English-Translation-Table](https://github.com/ffdkj/ffdkj-Danbooru_Tag-Chinese-English-Translation-Table)。其公开的 `tag.sqlite` 包含 `tags` 表，字段包括：

- `name TEXT PRIMARY KEY`：英文标签；
- `category INTEGER`：Danbooru 标签类别；
- `cn_name TEXT`：中文名称；
- `post_count INTEGER`：使用次数。

该仓库说明其词库覆盖 30 万以上标签，并采用机器翻译和人工校对。正式接入前仍需审计：

- 当前下载 URL 是否稳定；
- SQLite 文件 SHA-256；
- 词库版本和更新时间；
- 数据库和翻译内容的再分发许可；
- 是否允许在用户机器上按需下载；
- 词库是否包含不适合默认展示的类别或内容。

### 5.2 存储位置

词库必须放在用户数据目录，不放在源码目录、Git worktree 或 `frontend/dist`。推荐抽象为：

```text
<user-data>/translation/danbooru/tag.sqlite
<user-data>/translation/danbooru/manifest.json
<user-data>/translation/cache.json       # 首版可不创建
```

`manifest.json` 至少记录：

```json
{
  "source": "ffdkj-Danbooru_Tag-Chinese-English-Translation-Table",
  "url": "https://.../tag.sqlite",
  "sha256": "...",
  "downloadedAt": "2026-09-29T00:00:00Z",
  "schema": "tags(name,category,cn_name,post_count)"
}
```

### 5.3 下载流程

1. 用户首次选择词库模式；
2. 后端检查本地文件和 manifest；
3. 无文件时显示下载进度；
4. 下载到临时文件；
5. 校验 HTTP 状态、文件大小和 SHA-256；
6. 使用 SQLite `PRAGMA integrity_check`；
7. 原子替换正式文件；
8. 失败时删除临时文件，保留旧词库；
9. 词库不可用时继续运行，并让 provider 回退到网络/LLM或原文。

## 6. 标签规范化和最长匹配

### 6.1 规范化原则

规范化只用于查询，不改原文。首版允许：

- 去除首尾空白；
- 将全角逗号转换为分隔符，仅用于 caption 拆分；
- 保留原始下划线形式；
- 查询时可尝试下划线形式和空格形式；
- 保留括号、冒号、斜杠、权重和 LoRA 语法的识别边界。

不能把任意 prompt 片段拆成普通英文单词后强行翻译。

### 6.2 最长匹配

对以空格组织的多词标签，查询顺序从最长到最短：

```text
long hair style
long hair
long
```

但 Danbooru 标准 tag 通常使用下划线，因此优先直接查询原始 `long_hair`。只有在词库没有结果时，才尝试安全的规范化别名。

### 6.3 未命中

未命中不报错，不产生空白译文，不写入词库。结果状态为 `missing`，后续才允许网络翻译或 LLM 处理。

## 7. 翻译 provider

### 7.1 Danbooru provider

输入一批去重后的原始标签，使用参数化 SQLite 查询。返回词库中的 `cn_name`、分类和 `post_count`。词库命中是最高优先级，网络和 LLM 不能覆盖它。

### 7.2 免费网络 provider

首版提供 MyMemory 作为可选 provider：

- 匿名使用额度有限；
- 用户可以填写邮箱参数以提高额度；
- 请求必须限流、设置超时和取消；
- 失败时返回 `error`，不阻塞页面；
- 不把响应自动写入正式词库；
- UI 应明确显示“网络翻译结果”。

后续可以加入 DeepL、Microsoft Translator 或 LibreTranslate，但每个 provider 都必须独立说明 Key、额度、隐私和失败行为。

### 7.3 OpenAI 兼容 LLM provider

LLM provider 统一使用：

```text
POST <base-url>/chat/completions
Authorization: Bearer <key>
```

配置字段：

```json
{
  "endpoint": "http://127.0.0.1:8000/v1/chat/completions",
  "model": "Qwen/Qwen3.5-0.8B",
  "apiKey": "",
  "timeoutMs": 30000,
  "temperature": 0.1
}
```

本地 Qwen 服务可以使用 Qwen 官方支持的 OpenAI 兼容服务方式；API Key 可使用空值或本地服务要求的占位值。远程 API 必须由用户明确配置。

LLM 提示词必须要求：

- 输入和输出一一对应；
- 只返回严格 JSON；
- 不增加标签；
- 不改写原始英文标签；
- 不确定时返回 `null`；
- 角色名、作品名不确定时保留英文；
- 不输出解释、Markdown 或额外句子。

推荐请求格式：

```json
{
  "items": [
    {"id": 0, "tag": "blue_eyes"},
    {"id": 1, "tag": "long_hair"}
  ]
}
```

推荐响应格式：

```json
{
  "items": [
    {"id": 0, "tag": "blue_eyes", "translation": "蓝色眼睛"},
    {"id": 1, "tag": "long_hair", "translation": "长发"}
  ]
}
```

服务端必须校验 `id`、`tag`、数组长度和字符串类型。任何校验失败都视为该批次失败，不把错位结果显示给用户。

### 7.4 Agent provider 复用

当前 Agent 插件已经有 provider、模型和凭据存储，但主程序不应直接读取插件的 `auth.json`。首版可以先使用独立的 OpenAI 兼容配置；后续再通过插件桥暴露“翻译请求”能力。

如果复用插件 provider，必须满足：

- API Key 不进入主程序前端；
- UI 只选择 provider/profile；
- 插件返回结构化翻译结果；
- 主程序仍执行结果校验；
- 插件不可用时回退到其他 provider或原文。

## 8. 统一后端接口

建议增加一个只读接口：

```text
POST /api/dataset-editor/tag-translations
```

请求：

```json
{
  "tags": ["blue_eyes", "long_hair", "unknown_tag"],
  "locale": "zh-CN",
  "provider": "danbooru"
}
```

响应：

```json
{
  "items": [
    {
      "tag": "blue_eyes",
      "translation": "蓝色眼睛",
      "source": "danbooru",
      "status": "hit"
    },
    {
      "tag": "unknown_tag",
      "translation": null,
      "source": null,
      "status": "missing"
    }
  ],
  "provider": "danbooru",
  "locale": "zh-CN",
  "dictionaryVersion": "..."
}
```

接口要求：

- 只读，不修改数据集；
- 对输入标签去重，但响应必须能够映射回每个原始 tag；
- 限制单次标签数量和总字符数；
- 支持请求取消和超时；
- 不在错误消息中泄露 API Key、完整 URL 中的凭据或本地绝对路径；
- 网络 provider 和 LLM provider 的错误应返回稳定错误码。

## 9. 缓存策略

首版不增加业务 SQLite 缓存表。

### 9.1 内存缓存

前端或后端均可使用容量受限的内存缓存，键为：

```text
provider + model + locale + dictionaryVersion + rawTag
```

### 9.2 持久缓存

只有在首版验证后才考虑 JSON 持久缓存：

- 只保存网络/LLM结果；
- Danbooru词库结果不需要重复缓存；
- 支持清空；
- provider、模型和词库版本变化时自动失效；
- 不把用户 caption 作为缓存 key 或持久化内容。

## 10. 前端接入

当前接入点为 `frontend/src/pages/DatasetEditorPage.vue`：

- `captionTags` 生成原始标签列表；
- `.caption-chips` 渲染标签；
- caption 文本框保存原始内容。

建议新增一个独立 composable：

```text
useTagTranslations(tags, options)
```

职责：

- 去重和批量查询；
- 内存缓存；
- 取消过期请求；
- 暴露 `translationFor(tag)`；
- 区分 loading、hit、missing 和 error；
- 处理用户切换当前图片导致的过期响应。

不把翻译状态并入 `caption` 或 `DatasetItem.tags` 的持久化数据结构。

## 11. 安全、隐私和许可

- 默认只使用本地 Danbooru 词库；
- 网络翻译和 LLM provider 必须由用户选择或开启；
- 只发送标签字符串，不发送图片、数据集路径和完整 caption；
- 对网络 provider 提供“仅发送未命中标签”的说明；
- API Key 只能存后端/插件安全存储，不能进入前端 bundle、日志或 Git；
- 外部词库下载必须记录来源和许可；
- 不直接复制 WeiLin GPL-3.0 实现代码；
- 不把未经审计的词库直接打进发行包；
- 标签翻译错误不能改变训练数据。

## 12. 验收标准

### 12.1 词库

- [ ] 首次下载成功后能查询 `blue_eyes`、`long_hair` 等标签；
- [ ] 断网时已下载词库仍可使用；
- [ ] 下载中断不会破坏旧词库；
- [ ] SHA-256 或完整性检查失败时不会替换正式文件；
- [ ] 词库缺失时 UI 显示明确状态并可继续使用其他 provider。

### 12.2 原文保护

- [ ] 释义查询前后 caption 内容字节级不变；
- [ ] 保存、导出、批量清理和训练提交不读取中文释义；
- [ ] 切换 provider 不改变标签 chip 的原始值；
- [ ] 翻译失败不会阻止打标、保存和训练。

### 12.3 provider

- [ ] MyMemory 成功、超时、限流和空结果都有可控行为；
- [ ] LLM 可使用本地 Qwen OpenAI 兼容地址；
- [ ] LLM 可使用远程 OpenAI 兼容地址；
- [ ] LLM 错位 JSON、缺字段和非 JSON 响应会被拒绝；
- [ ] 自动回退顺序稳定且可观测；
- [ ] 日志不输出 Key、完整请求头或用户路径。

### 12.4 UI

- [ ] 英文原词始终可见；
- [ ] 中文释义与原词视觉层级明确；
- [ ] 未命中不显示误导性空白；
- [ ] provider 来源和失败状态可通过 tooltip 或详情查看；
- [ ] 切换图片时不会出现上一张图片的异步译文串入。

## 13. 风险与待审计决策

### 高风险

1. **外部词库许可和内容质量**：下载可行不等于可以再分发；需在实现前记录许可结论。
2. **角色名/作品名误译**：LLM 和通用翻译都可能产生错误译名；不确定时必须回退英文。
3. **网络隐私**：即使只发送标签，也可能暴露用户数据主题；网络 provider 必须显式可选。
4. **本地 Qwen 运行成本**：0.8B 需要实际测试吞吐、中文质量和 JSON 稳定性；不能把它当成稳定权威词库。

### 待用户/维护者确认

- [ ] 是否确认 ffdkj SQLite 作为首选现场下载词库；
- [ ] 是否允许默认展示 character/copyright 的词库译名；
- [ ] MyMemory 是否作为首个免费网络 provider；
- [ ] 默认模式是“仅 Danbooru”还是“自动回退”；
- [ ] Qwen 本地服务是用户自行启动，还是后续由项目提供启动辅助；
- [ ] 首版是否需要 Agent provider 复用；
- [ ] 释义默认采用 chip 下方文本还是 tooltip；
- [ ] 是否需要持久化网络/LLM翻译缓存。

## 14. 实施阶段

### 阶段 A：词库探针

- 下载候选 SQLite 到临时用户数据目录；
- 审计 schema、体积、索引和许可；
- 用固定样本验证命中率；
- 输出词库探针报告。

### 阶段 B：词库 provider

- 实现下载、校验、manifest 和原子替换；
- 实现只读查询、规范化和最长匹配；
- 实现后端接口和单元测试。

### 阶段 C：网络 provider

- 实现 MyMemory；
- 加入超时、限流、取消、错误码和隐私提示；
- 增加 provider 菜单。

### 阶段 D：LLM provider

- 实现 OpenAI 兼容文本请求；
- 用本地 Qwen3.5-0.8B 做实机验收；
- 支持远程 URL、Key 和模型配置；
- 增加严格 JSON 校验和批量回退。

### 阶段 E：前端展示

- 增加 composable 和 chip 辅助展示；
- 验证切换图片、切换 provider 和请求取消；
- 运行前端测试和后端测试。

本设计书当前只定义边界和契约，不包含功能实现。进入实现前，应先完成阶段 A 的词库探针和第 13 节的许可/默认策略审计。

## 15. 复用优先的迁移方案

本项目不从零设计翻译引擎。调研后，最适合迁移的参考实现不是 WeiLin 的整套 ComfyUI 代码，而是：

[ComfyUI-Autocomplete-Aaalice](https://github.com/Aaalice233/ComfyUI-Autocomplete-Aaalice)，分析快照 `37cabccf9b4d799b7b53a1e2d74f2cd214fe91d0`。

该项目使用 MIT License，并且已经包含与本需求高度重合的模块：

- `modules/chinese_dictionary_service.py`：ffdkj SQLite 词库下载、manifest、查询和更新；
- `modules/translation_store.py`：翻译结果持久化和失败状态；
- `modules/translation_service.py`：批量翻译、重试、拆批、并发限制、响应校验和流式结果；
- `modules/translation_config.py`：provider 配置、功能开关和 DeepSeek 配置；
- `modules/api.py`：词库状态、配置、模型测试、翻译 resolve 和 resolve-stream 接口；
- `web/`：翻译加载、结果展示和状态样式。

### 15.1 允许直接迁移的部分

在确认快照和许可证记录后，可以优先迁移以下实现，再做框架适配：

1. `chinese_dictionary_service.py` 的下载、临时文件、校验、manifest 和 SQLite 查询逻辑；
2. `translation_service.py` 的批量 provider 调度、失败重试、响应校验和流式返回逻辑；
3. `translation_config.py` 的配置字段和默认值；
4. `translation_store.py` 的缓存数据模型，视 Next Trainer 是否接受持久化缓存决定是否完整迁移；
5. LLM JSON prompt 和“缺失翻译不阻塞 UI”的状态处理。

这些代码不要直接复制 ComfyUI 的路由注册和全局状态，而是保留核心类，接入 Next Trainer 的 FastAPI router。

### 15.2 必须重写的薄适配层

以下部分属于框架耦合，不能直接搬运：

- ComfyUI `PromptServer.instance.routes` 路由；
- ComfyUI 的用户目录和配置路径；
- ComfyUI 前端 DOM、输入框监听和 CSS；
- Aaalice 的 DeepSeek 专用 API 客户端；
- ComfyUI 的 SSE 生命周期和事件广播；
- Next Trainer 的 `APIResponseSuccess` 包装和错误码格式。

目标是把重写范围控制在：

```text
FastAPI 路由适配
Next Trainer 用户数据路径适配
Dataset Editor 的 tag chip 展示适配
provider 配置 UI 适配
```

### 15.3 WeiLin 代码的处理方式

WeiLin 仓库的 `LICENSE` 是 GPL-2.0-only。其 `local_translate.py`、网络 provider 和 prompt UI 虽然有直接参考价值，但在没有明确许可和完成许可证审计前，不直接复制到 AGPL-3.0 的 Next Trainer 中。

可以继续参考其：

- 本地词库优先；
- 原文和译文分离；
- 未命中保留原文；
- token 级辅助展示。

实际迁移优先采用 MIT 许可的 Aaalice 模块，以减少许可和维护风险。

### 15.4 迁移验收

迁移不以“代码复制完成”为完成标准，必须逐项对比：

- SQLite 文件下载失败和恢复；
- 词库命中结果；
- provider 选择和禁用；
- LLM 返回缺项、重复项、错位项和非 JSON；
- 失败结果缓存与重试；
- 原始 caption 是否完全不变；
- Next Trainer 前端切换图片时是否发生旧请求串入；
- MIT 版权头和第三方说明是否保留。

### 15.5 实现顺序调整

原来的阶段 A-E 调整为：

- **A：迁移审计**：固定 Aaalice 快照、记录 MIT 文件、列出可迁移文件和必须重写的适配层；
- **B：后端迁移**：先迁移词库服务、translation service、配置和最小 FastAPI 路由；
- **C：Next Trainer 前端适配**：只改 Dataset Editor 标签 chip，不迁移 ComfyUI 页面；
- **D：provider 验收**：先词库，再 MyMemory，最后本地/远程 OpenAI 兼容 LLM；
- **E：清理与许可检查**：补第三方说明、测试、敏感信息检查和迁移差异审计。

这样预计新增的核心逻辑主要来自接口适配，而不是重新实现下载器、翻译调度器、缓存和 LLM 响应校验。
