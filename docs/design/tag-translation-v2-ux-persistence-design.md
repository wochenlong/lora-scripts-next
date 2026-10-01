# Tag 中文释义 v2 优化设计书（待审核）

> 2026-10-01：词库下载管理、本地模型安装、缓存与失败处理发现新缺口，后续实现以[v3 统一设置与运行管理设计](tag-translation-v3-settings-and-runtime-design.md)为准。下文的历史实现声明不作为新缺口已完成的证明。

> 本文的前端缓存部分受全局治理设计约束，详见[前端缓存生命周期治理设计书](frontend-cache-lifecycle-design.md)。标签翻译不再单独定义“清缓存”语义。

## 1. 本次范围与审计状态

- 状态：drafting，等待用户审核；本轮仅设计，不修改功能代码。
- 分支：feat/tag-translation。
- 核对基线：836064c（2026-09-29）。
- 唯一进度台账：[长程任务书](../tasks/tag-translation-task-book.md)。
- 本文是 [原设计书](tag-translation-design.md) 的优化修订；冲突时以本轮用户反馈和本文明确决策为准。
- 目标：切图/刷新/重启后恢复释义、统一现有 UI、明确免费网络翻译入口，并修复前端跨模块缓存生命周期混用问题。
- 保留约束：优先迁移已有模块；Danbooru 先查；原文和译文分离；翻译不得改写 caption、导出或训练输入。
- 本轮不把更多 provider 接入、Qwen 模型部署或通用词库管理后台混入三项体验优化。现有 LLM 通路的返回值适配属于必须修正的基础契约。前端缓存生命周期治理扩大为独立横向工作流，覆盖其他资源缓存和持久化状态。
- 尚未做 Qwen3.5-0.8B 真实模型质量验收；先前通过的词库/MyMemory 冒烟不能证明完整 LLM 通路。

## 2. 现状：以代码为准

| 模式 | 当前真实行为 | 完整程度 |
| --- | --- | --- |
| Danbooru | 本地 SQLite 精确按 name 查询；首次请求可能等待下载 | 已接入；词库在磁盘上，不因切图消失 |
| MyMemory | 词库未命中才访问 MyMemory；返回可展示的中文文本 | 唯一已接入的免费网络翻译；尚不落库 |
| LLM | 词库未命中调用迁入的 OpenAI 兼容客户端 | 可保存 endpoint/model/key；发现返回值适配错误，需修正 |
| 自动回退 | 词库 → MyMemory → LLM → 未命中 | 已有调用顺序，但缓存、失败状态和 LLM 适配未闭环 |

源码证据：

- frontend/src/pages/DatasetEditorPage.vue 的 choose() 设置 showTranslations=false，并执行 clearTranslations()。
- frontend/src/composables/useTagTranslations.ts 的 clear() 清空 entries；缓存仅按 tag 索引，未区分 provider/模型/语言。
- mikazuki/tag_translation/runtime.py 已建立 assets/tag_translation/danbooru/tag.sqlite 和 translations.sqlite3。
- translation_store.py 的 translations 主键是 (tag_name, locale)，虽有 model/prompt_hash 字段，查询未将它们作为隔离条件。
- providers.py 只有 MyMemory 实现，没有 Bing、阿里、有道、DeepL、Microsoft 或 LibreTranslate 适配器。
- api.py 在调用 LLM 前已请求 MyMemory，因此自动模式可能对已缓存的标签再次联网。
- translation_manager.resolve() 返回 tag → 行对象；api.py 直接把 llm.get(tag) 当作 translation 返回，可能把对象交给前端字符串字段。现有 API 测试未覆盖非空 LLM 返回，不能把此路径算作完整验证。
- 词库 lookup 当前只做 name IN 查询。空格/下划线变体和最长短语匹配尚未落实，保留为原范围待实现项；不能据本次 UI 优化宣称已经支持。

问题分为四层：词库数据已持久化；LLM 有后端缓存但语义不完整；显示开关与前端展示结果每次切图被重置；前端各模块没有统一区分视图清理、请求取消、资源失效和持久数据删除。

## 3. 建议采用的产品行为

### 3.1 显示开关与触发动作分离

将一次性“显示中文释义”按钮改为可记忆的“中文释义”开关，旁边保留“翻译缺失项”和“翻译设置”。

- 默认关闭显示，用户开启一次后保存浏览器偏好。
- 开启后，切到任何图片立即查询本地词库和已经保存的译文；切回 A 图无需再点击。
- 刷新页面或重启服务后，重新加载同一数据集与图片时自动恢复释义。此功能不负责替代数据集导航本身的恢复逻辑。
- 关闭开关只隐藏释义并取消当前展示请求，不删除译文缓存。
- 切图只废弃旧请求的展示结果；已经完成并合格的译文保留。
- 添加/删除/重排英文 tag 时，仅更新当前显示列表；新标签先查询本地信息。
- 切图和页面恢复只读本地，不自动消耗网络/LLM 额度。新增未命中项由“翻译缺失项”触发。
- 选择“词库 + 免费网络翻译”后，点击“翻译缺失项”即可使用 MyMemory，无需另配置 Key。
- 自动模式只有在用户选择它并点击翻译后执行；只发送当前图片未命中的标签。

示例：A 图含 blue_eyes，翻译后去 B 再回 A；开关仍开，蓝瞳立即恢复。B 的独有未知标签不会因浏览图片而自动发送到外部。

### 3.2 来源不是互相替代的翻译引擎

下拉改为“未命中时使用”，词库始终是第一层：

| 菜单文案 | 存储策略值（兼容现有 API） | 点击翻译时的行为 |
| --- | --- | --- |
| 仅本地词库 | danbooru | 本地查询，不外发 |
| 免费网络翻译 · MyMemory | mymemory | 词库 → MyMemory 缓存 → MyMemory 请求 |
| LLM · 本地或 API | llm | 词库 → 当前模型缓存 → 当前 LLM |
| 自动 · 网络后接 LLM | auto | 词库 → 已允许来源缓存 → MyMemory → 已配置 LLM |

自动模式缓存优先：先使用允许的有效结果（MyMemory 缓存优先于当前 LLM 缓存），全未命中才请求网络。切换“仅本地词库”后不展示其他 provider 的旧结果，避免来源混用。

## 4. 持久化设计

### 4.1 沿用现有 SQLite，不再增加另一套存储

- Danbooru 词库继续由已有下载服务维护，不把其每条命中重复写入缓存表。
- MyMemory 与 LLM 合格结果统一进入现有 translations.sqlite3。
- 前端只用有容量上限的内存 Map 加速，以及 localStorage 保存显示偏好；不把完整词库、Key 或全部译文写入 localStorage。
- 译文以标签为单位共享，多张图出现同一个标签不重复保存；不持久化图片路径或完整 caption。
- “持久化”包括后端重启和浏览器刷新后的成功译文复用。

建议在现有 SQLite 内增量迁移 translation_results_v2 表：

| 字段 | 含义 |
| --- | --- |
| tag_key / locale | 保守规范化的标签查询键、目标语言 |
| provider | mymemory 或 openai-compatible |
| profile_revision | 配置修订标识；endpoint/model/prompt 变化和显式凭据替换时更新，不包含明文 Key |
| text / source_model / prompt_revision | 已验证字符串译文及来源 |
| created_at / updated_at | 写入、更新时间 |
| normalization_version | 查询规范化规则版本 |

唯一键：(tag_key, locale, provider, profile_revision, normalization_version)。

- tag_key 首版仅去除外围空白，避免把艺术家名、权重表达式等任意折叠。
- 展示和保存用 raw_tag，绝不拿 tag_key 回写 caption。
- 外部词库版本变化时清空前端词库命中缓存并重新查询；不删除网络成功译文。
- 成功译文默认不过期；提供“重新翻译当前缺失/选中项”和“清除网络/LLM 缓存”入口。
- 后端缓存持久化；前端 Map 建议上限 2,000 个查询结果，淘汰前端条目不会删除后端数据。
- 超时、限流、未配置和解析错误不写入成功表；短期失败状态只在内存冷却，手动重试可跳过冷却。
- 不再沿用上游永久记录某模型失败后不重试的行为作为唯一重试机制。

### 4.2 旧缓存迁移

- 使用 SQLite schema version、事务和幂等迁移；原 translations 表保留，保证可回退。
- 旧数据没有 endpoint/profile 信息，不能可靠判断来自哪个服务。
- 不给旧行猜测来源；旧行保留为 legacy，不自动用于新 profile。首次实际翻译后写入 v2。
- 词库文件不动，已有译文不会被删除；旧 LLM 缓存首次可能需要重新请求，用户说明明确写出。
- 迁移失败时停止外部写缓存，显示可重试错误；仍可读词库和正常编辑数据集。

## 5. 请求、返回与失败行为

保留 /api/dataset-editor/tag-translations 和现有兼容入口，扩展请求：

```json
{
  "tags": ["blue_eyes", "an_unlisted_tag"],
  "locale": "zh-CN",
  "provider": "mymemory",
  "local_only": true,
  "refresh": false
}
```

- local_only=true：仅词库和该模式允许的磁盘缓存；不触发任何外部翻译或词库下载。
- local_only=false：用户点击翻译后的请求；按策略补缺。
- refresh 仅用于显式重试，仍保持词库优先，不无提示重译所有成功标签。
- 翻译查询和词库下载分离；下载已有 start_update/status 能力，新增薄路由和重试按钮，不让图片查询等候几分钟的下载。
- 每次输入按现有上限 500 标签校验，增加总字符上限；超限明确响应，不静默截断。
- 单条 translation 强制为 string|null；LLM 行对象必须通过适配层抽取 text。
- response 带 dictionary_revision、profile_revision，前端避免复用过期配置结果。

逐项响应建议：

```json
{
  "tag": "an_unlisted_tag",
  "translation": "辅助中文译文",
  "source": "mymemory",
  "status": "translated",
  "cached": true,
  "error_code": null
}
```

status 区分 translated、missing、error、not_configured；source 取 danbooru/mymemory/llm 或 null。错误不能伪装成普通未命中。

MyMemory 必须检查 HTTP 状态、responseStatus、quotaFinished 与 responseData 类型；不把额度错误文本当译文。对限流停止本批继续请求，提示服务限制，自动模式再交给已配置 LLM。官方额度提示应链接服务说明，不显示未经服务器确认的“今日剩余额度”。

LLM 保留现成批处理、重试和校验代码；配置字段从 deepseek 向 llm 过渡时读取旧值并兼容旧 API，不丢失用户设置。先修复当前对象/字符串错误，再谈增加更多 provider。

## 6. UI 统一方案

### 6.1 复用位置

| 当前组件/样式 | 本次复用点 |
| --- | --- |
| DatasetEditorPage 的右侧面板与工具栏 | 释义入口保持在单图 caption 区，沿用按钮、间距和层级 |
| DownloadSourcesPanel 的紧凑选择 + 高级设置交互 | 主界面短入口，复杂设置进入弹窗；不复制下载源业务代码 |
| PathPickerDialog 与历史记录的 el-dialog | 翻译设置使用现有弹窗和键盘焦点行为 |
| SettingsContainerPage 的表单反馈 | 保存状态、成功消息、失败保留输入、局部 busy |
| tokens.css / dark-theme.css / dataset.css | 复用真实存在的颜色/边框/字号 token，不新建独立配色 |

拟拆出 components/dataset/TagTranslationControls.vue 和 TagTranslationSettingsDialog.vue，页面仅协调。沿用已注册 Element Plus 组件及 CSS，新增组件时依照 frontend/AGENTS.md 注册。

### 6.2 交互草图

```text
单图编辑
sample.png

[✓ 中文释义]                         [翻译设置]
未命中时使用 [免费网络翻译 · MyMemory ▾]
[翻译缺失项（3）]       已有释义 12 / 15

┌ blue_eyes   × ┐  ┌ long_hair   × ┐
│ 蓝瞳          │  │ 长发          │
└──────────────┘  └──────────────┘

查看 / 编辑 caption 原文
[保存 Caption]
```

- 英文主行，中文次行至少 12px；长译文可换行/省略，悬浮或键盘聚焦查看完整释义。
- 原有拖拽和删除按钮保留命中区域，中文文字不产生新的删除行为。
- 来源在 tooltip/可聚焦说明中显示“词库 / 免费网络 / LLM·模型 / 已缓存”，不为每个标签堆多个徽标。
- 总体未命中数量可见；不为每个未命中项都弹错误。
- 窄屏按钮换行，设置弹窗宽度 min(640px, 94vw)，不横向溢出。
- 浅色、深色、键盘和触屏均验收。

翻译设置弹窗包含：

1. 词库：就绪/未下载/下载中/更新失败，条数、更新/重试入口。
2. 免费网络：MyMemory（免 Key），用途、连接测试、简短限制说明。
3. LLM：本地服务/远程 API 共用 endpoint/model/Key；Key 已设置状态、替换/清除、连接测试。
4. 缓存：网络/LLM 成功条数、清理操作说明。清缓存不删除词库、不修改 caption。

主工具栏不再展开 endpoint、模型和密码输入框；将现在的“LLM 设置”改为完整的“翻译设置”。

## 7. 免费接口究竟接入了哪些

- 已接入：MyMemory。界面原来只写 MyMemory，导致用户不容易识别它是免费网络服务。
- 未接入：WeiLin 的 Bing/阿里/有道适配器，以及之前调研的 DeepL/Microsoft/Google/LibreTranslate。
- 调研列表不等于已实现列表；本次只展示真实可用的 provider，不添加虚假菜单。
- WeiLin 的界面布局与 provider 分类可以参考；现成网络适配器是否迁移另行按单文件来源与调用稳定性审计。
- 不能仅凭 WeiLin 仓库存在 GPL v2 文本就断言所有文件为 GPL-2.0-only；前文的绝对判断证据不足，本次仍不直接引入这些文件。
- 若审核希望首版菜单包含 Bing/有道/阿里，再补针对性适配调查；不把普通网页使用的内部接口标成稳定官方 API。

## 8. 并发、状态与配置边界

- 将 cancelCurrent()/resetView() 与 clearCache() 拆开；切图只取消展示订阅，绝不清空全部缓存。该规则适用于全前端资源，具体分类和迁移顺序以[前端缓存生命周期治理设计书](frontend-cache-lifecycle-design.md)为准。
- 使用 AbortController 和 generation 标识；旧响应可以完成合法后端缓存写入，但不可覆盖新图的 loading/error/结果。
- 删除标签后返回的旧结果不能重新插入 caption；译文映射与 caption 数据严格独立。
- 后端相同 profile+tag 的并发查询共用 in-flight 请求，避免不同图片重复计费。
- 切换 provider 后重新投影该模式允许的结果；改变 endpoint/model/prompt 后换 revision，不借用旧模型译文。
- MyMemory 和 LLM 的调用超时、限流、JSON 错误必须可见且不会阻止正常保存 caption。
- 偏好键建议 dataset-tag-translation-prefs-v1，仅保存 enabled、mode、locale；Key 只由后端保存。
- 仅本地查询模式不会因已保存的 LLM Key 自动激活收费请求。

## 9. 审核后实施顺序与验证

| 阶段 | 改动 | 必须通过的证据 |
| --- | --- | --- |
| A | 固定返回契约、补缓存 schema 迁移、MyMemory 持久化 | 非空 LLM 响应为字符串；迁移两次幂等；错误响应不落库 |
| B | 前端偏好、切图恢复、旧请求取消 | A→B→A 自动恢复；刷新/服务重启后本地缓存恢复；不重复网络请求 |
| C | 统一工具栏与设置弹窗 | 现有样式、浅深色、窄屏、键盘、设置保存/测试/错误反馈 |
| D | 真实浏览器和原文保护验证 | MyMemory/LLM 回退、词库下载失败仍可读旧库、caption 字节一致 |

验收用例：

- A/B 两张图共用标签 + 各自独有标签；翻译一次后往返，已命中项请求计数不增加。
- 译文成功写入后重启后端；浏览器重新加载同一图，local_only 请求取到持久结果。
- 关闭开关再开启，译文恢复；清缓存后只有网络译文需重新获取，Danbooru 可继续使用。
- MyMemory 429/额度耗尽/超时/错误 JSON 分别有错误状态；自动模式按配置回退。
- LLM 返回行对象适配正确；缺项、未知项、重复项、不确定 null、解析失败都不发生错位。
- 配置从模型 A 切到 B，不能错误复用 A 的结果；模式切为词库不能残留网络结果。
- 切图时故意延迟前一请求，结果不会覆盖下一张图片。
- 展示、重试、切换 provider 和查询均不改变 caption 文件；显式保存后的值只有英文原文。
- 使用 Node 22 运行 npm run check；Python 运行词库/缓存/provider/API/数据集编辑相关测试。
- 文档准确标记已接入/未接入/待实机验证；Qwen 实机质量仍需独立证据。

## 10. 供本轮审核的四个决定

1. 持久化范围：同图往返 + 刷新 + 服务重启均恢复（建议采用）。
2. 触发方式：切图自动读本地，未命中外部翻译由按钮触发（建议采用）。
3. 布局：主界面紧凑工具栏 + 统一翻译设置弹窗，中文常显于英文下方（建议采用）。
4. provider 范围：本轮明确呈现 MyMemory，保留 LLM；其他免费服务后续单独接入（建议采用）。

实现状态：代码已完成 A/B/C 阶段，D 阶段的真实浏览器、真实 MyMemory/LLM 和 Qwen 0.8B 质量属于目标环境验收。自动化验证与专项测试记录见长程任务书；本设计中的缓存、UI、provider 菜单和 LLM 字符串契约已落实。
