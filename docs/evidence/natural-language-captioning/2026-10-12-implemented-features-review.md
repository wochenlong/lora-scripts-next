# 已实现自然语言打标与共用 LLM 功能审查

日期：2026-10-12。工作副本：`feat/NL-Captioning`，HEAD `1f8f90c1`，冻结 dev 基线 `2bdccd1b`。审查覆盖已提交实现及当前未提交增量，不限于 `git diff HEAD`。

结论：确认 **13 项问题：2 项 P1，11 项 P2**。P1 涉及用户原文或草稿被静默覆盖，应优先修复。本轮完成的是审查，问题尚未修复。没有修改业务源码、生产配置或数据集，没有启动或重启服务，没有提交或推送。

## 确认问题

### R01 / P1：后台打标与编辑器竞争写回，哈希保护仍可让两个写入都成功

定位：[caption_job.py:95](../../../mikazuki/tagger/caption_job.py#L95)、[caption_job.py:97](../../../mikazuki/tagger/caption_job.py#L97)、[dataset_editor.py:347](../../../mikazuki/dataset_editor.py#L347)。

`write_caption_atomic()` 在最终哈希检查与 `os.replace()` 之间没有共用的文件写锁。Caption 后台线程与 Editor 的 HTTP 保存可以针对同一文件、同一个 expected hash 都通过检查。线程在检查后暂停、另一方完成保存、暂停方继续 replace，是合法的执行顺序；结果为两次成功，后者覆盖前者，没有 `caption_conflict`。CaptionJobManager 自身锁不被 Editor 使用，训练占用检查也不阻止这个场景。

隔离探针让两个生产 helper 在 replace 入口同步，第一 writer 完全成功返回后第二 writer 才替换，实测 `successful_writers=2`、`conflicts=0`、最终为后台描述。此探针证明共享 helper 的竞争窗口，入口线程并行由调用链确认；没有对用户运行服务制造并发写入。

建议：Editor 保存、Caption 提交、撤销与回滚共用同路径的写入协调机制，将最终冲突检查及提交放进同一临界区。补后台提交与 Editor 保存竞争的回归。

归属：已提交 Caption/Editor 写回实现。

### R02 / P1：保存回包无条件清除保存过程中继续输入的新草稿

定位：[DatasetEditorPage.vue:624](../../../frontend/src/pages/DatasetEditorPage.vue#L624)、[DatasetEditorPage.vue:629](../../../frontend/src/pages/DatasetEditorPage.vue#L629)、[DatasetEditorPage.vue:798](../../../frontend/src/pages/DatasetEditorPage.vue#L798)。

用户提交原文 A，保存回包前继续编辑成 B。`apply()` 无条件清除对应草稿并将编辑框重置为已保存的 A，B 丢失。保存期间允许继续编辑，也没有提交草稿版本与当前版本比较。组件探针确认 B 先进入草稿存储，回包后草稿消失且编辑框恢复 A。

建议：保存磁盘基线后，仅在当前草稿仍等于提交快照时清除草稿；保留请求期间新增修改。保存按钮应有提交状态，但不应以锁死编辑框替代草稿版本保护。

归属：冻结 dev 遗留；自然语言原文编辑继承并暴露此风险。

### R03 / P2：本地模型操作把旧完整配置草稿升级为新 revision，绕过冲突检查

定位：[LlmSettingsDialog.vue:60](../../../frontend/src/components/LlmSettingsDialog.vue#L60)、[LlmSettingsDialog.vue:62](../../../frontend/src/components/LlmSettingsDialog.vue#L62)、[LlmSettingsDialog.vue:152](../../../frontend/src/components/LlmSettingsDialog.vue#L152)。

模型管理加载配置 A 后，另一标签页将远程配置改为 B。当前弹窗执行本地安装/启停，仅合并 managed Profile，却将旧远程字段、路由及缓存草稿的 revision 改成 B 的 revision。随后保存携带“新 revision + 旧字段”，后端版本冲突检查无法阻止覆盖 B。组件实测提交 revision 为 `external-tab-new-revision`，远程名称仍是旧值。

建议：保留原草稿版本，或进行明确的三方合并，对其他标签页修改过的字段报冲突；不能只替换 revision。

归属：当前未提交设置收敛增量新增。

### R04 / P2：首次配置视觉模型的入口形成循环

定位：[TaggerPage.vue:36](../../../frontend/src/pages/TaggerPage.vue#L36)、[TaggerPage.vue:479](../../../frontend/src/pages/TaggerPage.vue#L479)、[TaggerPage.vue:496](../../../frontend/src/pages/TaggerPage.vue#L496)。

没有 ready 视觉模型时，自然语言模式按钮禁用；LLM 模型管理按钮只在自然语言模式中出现。新安装、模型未启动或所有视觉模型停用时，用户无法从打标页进入管理，只能绕到 API 设置页。既有组件测试明确断言未验证视觉模型时该方式按钮禁用，不能把该测试解释为首次配置流程通过。

建议：允许选择自然语言方式并打开管理；将 ready/视觉能力门控放在预览和启动生成操作上。

归属：ready 门控原已存在；当前按打标方式隐藏管理入口的增量形成此回归。

### R05 / P2：英文正文带中文招牌被当成中文，翻译被跳过

定位：[caption_translation.py:19](../../../mikazuki/llm/caption_translation.py#L19)、[captionLanguage.ts:3](../../../frontend/src/dataset/captionLanguage.ts#L3)、[useCaptionTranslation.ts:25](../../../frontend/src/composables/useCaptionTranslation.ts#L25)。

判断规则比较“汉字字符数”与“英文单词数”。正常英文描述 `A sign says 欢迎光临.` 会被判为中文。前端不发请求并标记已是中文；绕过前端调用后端也返回英文原文，`source_language=zh`、`skipped=true`，route resolve 次数为 0。

建议：识别主体句子语言，避免引号、牌匾和专名中的中文压过英文主体；增加中英混合可见文字的样本。

归属：已提交自然语言翻译实现。

### R06 / P2：导入/迁移后的短正文被猜成 Tag，开放了破坏性 Tag 操作

定位：[dataset_editor.py:128](../../../mikazuki/dataset_editor.py#L128)、[dataset_editor.py:141](../../../mikazuki/dataset_editor.py#L141)。

格式来源按绝对路径保存在私有 SQLite。复制或迁移数据集后，新的路径没有来源，短正文被启发式当成 Tag。探针导入 `  A cat, sleeping on grass\r\n`，scan 得到 `tag`，批量 remove `A cat` 返回 200，正文变成 `sleeping on grass`。也会将整段翻译路由变成 Tag 翻译。

这与设计书“无来源文本按 unknown 保护、不依据短文本猜测”的约定不符。使用说明已经承认旧短文本有歧义，但实际界面未提供确认格式的步骤。该成功批处理仍可 undo，不能声称不可恢复。

建议：对有歧义的无来源文本按 unknown 保护，提供明确的格式确认，或让正式导入/迁移保留来源。

归属：已提交格式识别及来源实现。

### R07 / P2：关闭翻译缓存或更换模型后，浏览器仍返回旧 Tag 译文

定位：[useTagTranslations.ts:25](../../../frontend/src/composables/useTagTranslations.ts#L25)、[useTagTranslations.ts:45](../../../frontend/src/composables/useTagTranslations.ts#L45)、[DatasetEditorPage.vue:266](../../../frontend/src/pages/DatasetEditorPage.vue#L266)。

浏览器缓存键仅含 locale/provider/tag，不含 Profile 或配置 revision，共用 `cache.translation=false` 也没有传给该 composable。保存新路由或关闭缓存后刷新仍命中浏览器旧译文，后端根本收不到请求。组件实测换到 `remote-b` 且关闭缓存，API 次数为 0，仍显示旧模型译文。

建议：将共用缓存策略和模型身份贯穿到浏览器层；配置变化时失效对应 LLM 缓存；关闭缓存必须绕过浏览器读取与新增。

归属：浏览器 helper 继承 dev，共用配置适配不完整。

### R08 / P2：Tag 翻译就绪检查只看一个远程配置，阻止后端可执行的翻译

定位：[DatasetEditorPage.vue:312](../../../frontend/src/pages/DatasetEditorPage.vue#L312)、[DatasetEditorPage.vue:359](../../../frontend/src/pages/DatasetEditorPage.vue#L359)、[DatasetEditorPage.vue:374](../../../frontend/src/pages/DatasetEditorPage.vue#L374)。

第一个远程 Profile 未就绪、第二个已验证文本能力时，前端只检查第一个并阻止请求、打开设置；后端 `candidate_profiles()` 原本可选择第二个。组件复现确认第二个 ready=true，但翻译 API 为零请求。用户选择首个未就绪配置时同样影响其他可用候选的兜底。

建议：前端使用后端路由就绪投影，或按所有符合文本/语言/启用条件的候选判断，保持路由规则一致。

归属：已提交共用路由适配缺陷。纯 local-endpoint 被 managed Qwen 状态阻挡的分支只有静态疑点，未独立复现，不另列确认问题。

### R09 / P2：切换同名模型的新接口后，Tag 翻译失败记录仍阻止重试

定位：[translation_service.py:463](../../../mikazuki/tag_translation/translation_service.py#L463)、[translation_store.py:146](../../../mikazuki/tag_translation/translation_store.py#L146)。

失败记录只绑定 locale/tag/model/prompt hash，没有共享 Profile revision。第一个接口失败后换第二个已验证接口，只要 model 名称相同，就继续跳过该 Tag。探针保留默认 max_retries=3，第一个接口尝试 4 次后失败；切换使共享 revision 变化，仍不调用第二个接口；显式 refresh 才得到“猫”。

建议：失败缓存使用完整模型/接口/凭据代次身份，并规定过期或可重试条件。

归属：失败记录机制继承 dev，共享多 Profile 适配未完成。

### R10 / P2：“清空翻译缓存”没有清理失败记录

定位：[tag_translation/api.py:186](../../../mikazuki/tag_translation/api.py#L186)、[translation_store.py:320](../../../mikazuki/tag_translation/translation_store.py#L320)。

实际 UI 链调用 `DELETE /api/tag-translation/cache`，其 `clear_results()` 只删除成功缓存，不清 `translation_failures`。R09 探针调用此真实 handler 后缓存计数为 0，仍不重新请求已经失败的 Tag。即使不切换接口，用户修复服务后也无法通过“清空缓存”恢复正常重试。

建议：清理指定 provider 的成功及失败缓存，保持页面计数、清理语义和实际行为一致。

归属：既有 Tag 失败缓存与当前共用缓存清理入口的适配缺口。

### R11 / P2：远程失败后生成的本地 Caption 译文无法命中缓存

定位：[caption_translation.py:45](../../../mikazuki/llm/caption_translation.py#L45)、[caption_translation.py:63](../../../mikazuki/llm/caption_translation.py#L63)。

读取缓存用预选远程 Profile revision，写入用实际本地 Profile revision。远程仍保持已验证但实际请求失败时，相同正文反复尝试远程并再次执行本地推理。探针连续两次 `cached=false`，调用为 `[remote,local,remote,local]`，SQLite 已有 1 条本地译文。

建议：保持远程优先，在远程失败、选定本地兜底后检查本地对应缓存，再决定是否推理。

归属：已提交自然语言翻译实现。

### R12 / P2：取消本地批量任务后仍可能启动下一条排队推理

定位：[caption_job.py:270](../../../mikazuki/tagger/caption_job.py#L270)、[caption_job.py:273](../../../mikazuki/tagger/caption_job.py#L273)、[caption_job.py:716](../../../mikazuki/tagger/caption_job.py#L716)。

本地 worker 获得任务内 semaphore 后不重查任务取消标志；各 worker 的 `_cancellable()` 独立每 50ms 检查。正在推理的请求取消并释放 slot 时，排队 sibling 可以在自身取消检查前发出第二个请求。

本轮原有取消回归出现失败：provider calls 从预期 1 变为 2。独立 fake transport 重复探针中，正常传播 CancelledError 的 40 次里有 12 次发出第二个请求，吞取消模拟晚到的 40 次里有 16 次。频次仅是本次运行观察，不能作为稳定概率。最终均 cancelled、无 TXT、slot 归零；已确认影响是多发推理和停止延迟，没有确认晚到写盘。

建议：获得本地执行许可后、真正发请求前重查任务取消；取消统一关闭该任务待执行请求的准入。

归属：当前未提交 Caption 并发增量。

### R13 / P2：数据库写故障后的恢复与回滚不完整

有两条已确认路径，均需明确事务/恢复处理：

1. Editor：[dataset_editor.py:347](../../../mikazuki/dataset_editor.py#L347)、[dataset_editor.py:352](../../../mikazuki/dataset_editor.py#L352)、[dataset_editor.py:427](../../../mikazuki/dataset_editor.py#L427)。TXT 已提交后再写来源；来源 SQLite 故障时返回 500，文件已经改变，但尚未登记编辑历史。隔离故障注入得到 `txt_exists_after_error=true`、`can_undo=false`。
2. Caption：[caption_job.py:154](../../../mikazuki/tagger/caption_job.py#L154)、[caption_job.py:312](../../../mikazuki/tagger/caption_job.py#L312)、[caption_maintenance.py:62](../../../mikazuki/tagger/caption_maintenance.py#L62)。来源写失败后任务正确保留 intent，但允许直接开始新任务；启动覆盖当前 intent，重启只恢复最新任务，旧任务未核验。探针在单次故障恢复后开始一个 ignore 任务，再重启：旧 TXT 仍在、旧 report 为空、format=null、旧 rollback 返回 restored=0 且没有冲突项。

建议：Editor 有自己的恢复意图/失败补偿；新任务前核验遗留 intent，重启恢复所有待核验任务，回滚不能悄悄跳过已提交但未登记的写入。

归属：已提交存储/恢复实现。故障由临时 SQLite 注入，不表示用户实际磁盘已发生故障。

## 本轮验证与证据

| 检查 | 本轮结果 | 证明范围 |
| --- | --- | --- |
| Dataset format/provenance/editor API、Caption 翻译、并发及 loopback HTTP，共 6 文件 | **80 passed / 1 failed** | 失败为 R12 对应既有取消测试；没有将失败核销 |
| LLM verification/translation/runtime secrets/unified store/managed model，共 6 文件 | **64 passed** | 与上一组有交集，不累加数量；使用临时配置/fake provider |
| Caption durable jobs/maintenance/task bridge/concurrency，4 文件 | **57 passed / 1 deselected** | 明确排除已复现的本地取消失败用例；不能解释为全部通过；日志 `.runtime/review-backend-focused-20261012.log` |
| 编辑器翻译入口、Tagger Caption、LLM 弹窗、Caption 翻译 composable，4 文件 | **51 passed** | 真实 Vue 组件；隔离 mock；本轮运行日志在 `.runtime/review-ui-regression-20261012.log` |
| 前端错误行为组件探针 | **4 个复现通过** | 通过表示错误行为被确认，不代表功能验收通过；其余原 fixture 测试由 filter 跳过 |
| 写回/格式/SQLite 故障探针 | **3 个复现通过** | 临时数据集、临时库、真实生产 helper；竞争为受控合法调度 |
| LLM 翻译边界探针 | **3 个复现通过** | 主体语言误判、负缓存换接口与清理、兜底缓存回放 |
| 本地取消重复探针及遗留 intent 恢复探针 | **80 次取消 + 1 条故障链** | fake transport，真实调度与 UnifiedLLMService；观察到 R12/R13 |
| 真实运行与浏览器复核 | **未执行** | 主项目 28000 与本地 7332 本轮检查时无监听；未启动或重启服务 |
| 真实远程/本地模型质量、完整全量测试、从零重建 | **本轮未执行** | 本轮是 review，不把历史验收冒充当前重跑 |

后端第一组实际命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_dataset_caption_format.py tests/test_dataset_caption_provenance.py tests/test_dataset_editor_api.py tests/test_caption_translation.py tests/test_caption_concurrency.py tests/test_caption_concurrency_http.py
```

独立证据均在主项目 `.runtime/`，不含真实 Key：

- `review-caption-boundaries-20261012.py` / `.log`：R01、R06、R13 Editor 分支。
- `review-frontend-20261012/evidence.md` / `results.log` / `cross-review.md`：R02、R03、R07、R08 组件复现、R04 源码与测试证据、root 三条独立交叉审查。
- `review-frontend-probe-20261012.test.ts`、`review-llm-rebase-probe-20261012.test.ts`：前端临时 fixture 归档。执行时位于临时 src 测试路径，归档后相对 import 不可直接照原路径运行；未留在业务源码中。
- `review-llm-translation-probes-20261012.py` / `.json` / `.log`：R05、R09、R10、R11。
- `review-backend-cancel-and-recovery-20261012.py` / `.log`：R12 及 R13 Caption 分支。

## 已核对的功能基础与剩余边界

英文完整提示词、预设总控语言、纯自然语言原文与只读译文、视觉/文本能力分离、共用模型资产、远程优先及本地兜底、并发参数校验和通常情况下的本地单推理，均存在真实实现与定向测试支持。此次 51 项前端回归也覆盖最近翻译设置/LLM 管理入口、弹窗返回、生命周期与迟到配置保护。

来源完整的自然语言文件、一般外部文件改动、并发任务内的串行提交及持久化故障停止 sibling 等保护已实现；R01、R06、R12、R13 指向这些保护尚未覆盖的边界，不应把整个模块描述为没有保护。

本轮范围限于 Caption、共用 LLM、翻译及它们与数据集编辑器/任务的交界；Agent、插件和训练实现未纳入此次变更审查。保留既有 dirty 工作副本及用户 `tests/test_diffsynth_review.py` 修改。

下一步：先修 R01/R02 两条内容丢失路径并补交叉模块回归，再按报告修复配置、首次入口、翻译与存储恢复问题。
