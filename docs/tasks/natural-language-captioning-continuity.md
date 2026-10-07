# 2026-10-08 执行续接

Goal active；用户已明确全面施工。HEAD需读git log；本轮预设存储/API、明确导入、类型/settings保护、revision409、内置/用户模板及未保存保护、system prompt单图/批量与缓存已实现。combined UI及start/preview入口拒绝；manager内部/retry旧任务仍待审计。底部进度布局已实现未浏览器验收。

最后后端44项通过、前端331项/51文件与type/lint/build通过。未运行新契约真实资源和Phase5。源码/证据详情见phase-0-contract-alignment/2026-10-08-presets-and-delta.md。tests/test_diffsynth_review.py为既有未提交修改，不加入本批提交。tracked dist恢复基线。

单一下一步：后端模型能力目录、TaggerPage一级本地/API与模型系列选择器、前后端参数隔离。存储仍需多文件失败恢复/跨进程并发补验；UI仍需显式legacy导入按钮及实际跨浏览器验收。不重复Agent插件工作，不重新做P1探针/既有评分。

以下为历史记录，以本段和canonical任务书最新状态为准。
# 2026-10-07 Issue #409 重规划增量

- 当前契约已切换为 Issue #409；设计书、canonical task book、manifest、目标计划和 goal 已重写为 v3.0。
- 首版范围是 model-first 的本地模型/API 服务、Tag/自然语言 Caption、模型专属参数、user_data Caption prompt preset、任务安全和 Dataset Editor safety。
- 首版不创建、不展示、不验收 combined/mixed；历史 combined/mixed 证据保留为旧契约记录，不得当作本版完成门。
- Agent、sidecar、provider、plugin marketplace 不属于本任务；越界未提交计划和工具已清理。
- 当前 readiness 为 drafting；下一步是 Phase 0 差异审计，之后才重新开工。

以下内容是重规划前的历史执行记录，仅用于保留已验证事实，不能覆盖以上新契约。
# 自然语言打标续接摘要

2026-10-07；canonical progress：natural-language-captioning-task-book.md。每次继续先读goal-objective，完整目标必须包括全部前后端、完整测试/真实/人工验收和Phase4从零重建。

## 当前目标和状态

- goal文件：C:/Users/25454/.codex/attachments/33329a36-8e01-4211-b79c-a080571cde4b/goal-objective.md。
- worktree：E:/OpenSourceTeamWork/workspace/branches/feat-NL-Captioning；分支feat/NL-Captioning；本批基线2cdb77f，最新HEAD读git log，git status clean。未push。
- 本次为progress：c0c94ed报告/轮询/编辑器冲突；25e954b共享资产/cache；3b369e8翻译prompt/reasoning兼容；e673d9a恢复/来源安全。
- Phase0/1/2 done（有gate-review）；Phase3 in progress，Phase4 pending。整体goal保持active，尚未交付完成。
- 最后相关后端241 passed/4 warnings/20.75s；Node22 check329 tests/51 files/13.92s，type/lint/build pass，2个已有Lint warning，build5.58s。不得等同完整矩阵。
- 原宽范围11失败已全部重现/留脱敏逐case日志；7个依赖/README/process修复后17项/215.59s复验通过，4个WinError1314未解决。21 skipped/31根训练collection仍未核销。

## 关键决策

Tag仍WD/CL，LLM只natural；翻译text、打标vision。Remote-first，explicit local fallback默认false。Qwen3-VL-2B Q4_K_M+Q8 mmproj固定SHA/revision，CPU约3.1GB；SmolVLM只能英文候选。

Key仅进程、磁盘/响应掩码，重启重新注入。不能写真实Key到前端/Git/env文件/log/report/截图。仅bounded JPEG dataURL到远程，无文件名/目录/EXIF。Natural/mixed不走Tag清理，原子写回+before hash，外部冲突不能覆盖。

## 已实现/文件

- mikazuki/llm：共享v5迁移/锁/secret epoch/profile/routes，精准connection test、vision管理和缓存；local_text.py把既有纯文本模型注册共享profile/readiness，拒绝伪报vision。两个runtime重启保留禁用/名称/translation metadata。
- caption_job.py/store.py：共用translations.sqlite3任务快照、私有plan/backup/intent、history/report、恢复不autoinference、retry parent/frozen prompt/current profiles、冲突保护。Tag mode逐字节灰度通过；报告无私有路径/原始响应。
- LlmSettingsDialog/ManagedVisionModel：翻译/打标共用profiles/routes/cache/vision asset UI；草稿取消、精准测试、加载失败禁保存。translation_system_prompt/reasoning_effort迁移/共享与旧API双向同步，revision变化，native关闭reasoning。cache=false从API前置/流式读取到worker写缓存均兑现。
- useTaggerJob/useLlmProfiles + CaptionPromptEditor/CaptionJobProgress：单飞/AbortController/generation/离页治理，旧poll不覆盖cancel/新选择。Tagger三模式/preset/preview/progress/retry/report/history/recovery齐备。
- DatasetEditor：scan/save/batch带hash；批量全体预检，undo/redo校验另一侧hash，中途失败保留分段历史；失败后刷新UI历史，恢复CRLF/原始空白。
- caption_formats保存format+actualTags。已有non-tag来源外部修改后变unknown，不重判Tag；前端captionEditingFormat/Tags遵循source，mixed只用actualTags，draft/filter/translation不拆短natural；不存在caption可以手工Tag批量新增。无来源的历史短词仍有语义歧义，须在最终边界中说明。
- 重启报告新增caption_interrupted code，并兼容旧无code报告显示原因。

## 实际证据/资源

- 当前证据目录docs/evidence/natural-language-captioning/phase-2-frontend-editor：history-polling-editor-conflicts、shared-assets-cache-browser-flow、translation-options-compatibility、browser-restart-recovery-and-source-safety，以及resolved failure记录。
- Browser：实际Vue/API+fake模型/Tag，完成natural3图、combined3图、preview无写盘、429部分失败+只重试1项、cancel、报告、mixed原文save/undo/redo/hash、外部冲突、CRUD/cancel/cap/lang、桌面/390px/Tab/Escape/空配置/隐私提示。lifespan=off，不能当正式启动或Phase4。
- 最后真实进程重启root：workspace/sandboxes/nl-caption-browser-recovery-20261007，停止未完成job后--resume，recovered=true/failed3/provider0/files0；UI显式retry3/3，parent关联，旧历史3项可见。外部short编辑unknown和保存“猫”natural均原文保护无Tag按钮。
- tools/serve_caption_browser_fixture.py支持fresh root和仅标记root的--resume，拒绝真实endpoint/credentials；替换词库/MyMemory防自动外网。初始r1继承auto偏好曾触发词库下载，已取消，不能称该初次完全无外网。
- 当前所有自建dev/模型进程已停止，所有测试handle完成，浏览器about:blank。tracked dist恢复基线，不手改生成物。fixture/DB/图像/模型不入Git。
- Python3.11.15：workspace/sandboxes/nl-caption-runtime-20261006/.venv/Scripts/python.exe，requirements+pytest已装；不要宿主3.14。
- Node22.17.1命令：npm exec --yes --package=node@22.17.1 -- node 'I:/NdoeJS/node_modules/npm/bin/npm-cli.js' --prefix frontend run check。不要宿主24。
- GitHub git proxy127.0.0.1:11809。未请求push，旧worktree保留。
- P1资产workspace/sandboxes/nl-caption-p1-20261006/.sandbox-data；中间验证可复用，Phase4禁用。真实批量nl-caption-batch-20261007-r2：3图14.803s，峰值3094904832B，冲突/cancel0.026s/再连接/停止通过；首个root脚本误选text-only失败已记录。不是Phase4。

## 待办/风险

1. Phase2完成门已逐项核销，见phase-2-gate-review。当前Phase3。
2. Phase3安全rollback/clear与冻结三样本/rubric已完成；真实remote/local/ONNX、cache隔离/EDD human score/正式Zero-Short/发布/隐私扫描仍待执行。
3. 修复完整矩阵：torch/transformers/accelerate/safetensors依赖、README、Windows symlink权限、trainingstub等；无豁免不能skip。
4. 最新官方SiliconFlow文档支持vision json_schema/json_object，已查证；仍需当前生产路径实际验收，不用P1替代。原用户真实Key只允许后端瞬时注入，不写任何文件/日志/前端。
5. Phase4全部源码提交后fresh checkout/newvenv/newNodeci/new模型下载/newconfig/SQLite/output，从零完整复验；失败回修后再建freshroot。最终release dist从源码构建。

## 单一 Next action

完成主测试矩阵复验并核销剩余失败、跳过和联网测试。

Confidence medium：本批源码和证据已核对；整体完整测试、真实/人工评分、正式启动与隔离重建仍未闭环。普通修复自主，不暂停/不缩goal/不假完工。

## 本轮增量（Phase3）

- 新caption_maintenance.py + API rollback/DELETE +UI确认；caption_formats.writer_job_id、backups.format_detail和rollback prepared/done。保护same bytes later writer、raw original bytes/source、busy/in-use、backup SHA；prepared恢复和幂等；历史删后不删来源。当前12个维护测试，241相关完整后端；Node22 check329。
- 实际维护browser root nl-caption-maintenance-browser-20261007（fake/lifespanoff）：cancel不写，rollback恢复2/冲突1保持外部编辑，history clear→idle/history0/backups0且caption/format1仍保留。两server停止，无活跃handle，aboutblank，dist恢复基线。
- Stage3 frozen-eval-manifest/evaluation-rubric/preflight-and-phase4-inputs已落在docs/evidence/.../phase-3-evaluation；样本copy在sandbox/nl-caption-eval-20261007/samples，仅中间使用，Phase4从URL新下载。版权/public URL与SHA实际对上；评分null，不能伪造human。
- 失败日志sandbox/nl-caption-eval-20261007/logs/reproduced-11-failures.txt已脱敏。具体原case见Stage3 maintenance-and-matrix-progress。
- 测试venv新增torch2.7.0+cpu、torchvision0.22.0+cpu、transformers4.51.3、accelerate0.33.0、safetensors0.8.0（uv pip --python指定venv，venv无pip），未改GUI requirements/宿主。Original11失败中7个已关闭，17 tests通过。4个symlink权限等待用户；已request_user_input_async，不要重复问/擅自skip。已读取官方Windows资料；Admin=False，DeveloperMode未检出。所有进程终止后再具权限验Windows4case。
- 更新两README现有Bash/WSL CLI说明以修复已有测试。没有发布/push。

## 本轮增量：真实模型与用户评分

- 生产模块基线776c082，新增tools/verify_caption_production.py。remote 3/3、41.7s；local-r3 3/3、13.894s、启动2.952s、峰值3070423040B；routing三图全部remote，故障后disabled拒绝/explicit真实local成功。缓存3命中零请求、preview零写盘、模型停止；本地资产复用P1，仅Phase3。
- 用户原话“全部部合格。”“4分 all”，最初A/B六条五维各4，总20。SHA实核通过；approval独立于冻结manifest，后续routing不同文本不沿用分数。
- EOF输入/导入后mkdir r2失败已记录并修复；fresh local-r3/routing通过。证据见phase-3-evaluation/2026-10-07-production-real-and-human-review.md。
- diffusers0.32.2/einops0.8.1已装进指定测试venv。完整主tests收集正在复验；Windows symlink问题仍未豁免。
- 唯一下一步：完成主测试矩阵复验并核销剩余失败、跳过和联网测试。

## 2026-10-07 Tag/combined、Zero-Short和矩阵增量

真实默认WD ONNX三图旧/新Tag逐字节相同（13/11/8 Tags、8.366s）；实际WD+Qwen combined三图3/3、24.208s，mixed来源和actualTags正确，缓存3命中零LLM请求、preview零写盘、模型已停止。正式FastAPI lifespan=on和新Node22 dist已通过空配置/无Key/无词库/无视觉模型启动；API健康与桌面/390px页面可用，安装/配置入口、默认禁用fallback/生成均核对。证据见phase-3-evaluation/2026-10-07-real-tag-combined-zero-short.md，不属于Phase4。

主tests收集1503项；分区运行1467 passed/11 failed/25 skipped/1 deselected/77 subtests/308.42s。排除的唯一联网ModelScope tokenizer测试实际下载整个模型仓库，已停止并保留pending，未豁免。11失败中的7项已修复：任务维护测试不再向sys.modules泄漏Tagger替身，LyCORIS fake工厂允许可选导入缺失；相关55 passed/7.50s。另4项Windows symlink权限未解决。修复后的分区复验实际1474 passed/4 failed/25 skipped/1 deselected/77 subtests，306.54秒；仅4个Windows symlink失败。被排除的ModelScope项在独立7项真实组中通过，完整组合运行仍待复验；25项skip逐案审计/授权尚未核销。

DiffSynth Windows fixture改为稀疏标志+末字节seek/write，保留逻辑长度与模型header，13 passed/2.80s。初次truncate产生的测试文件清理被自动审批拒绝（仅blocked by policy），保留未复用，最终清理待核销。自建正式UI和模型进程停止，浏览器about:blank。

使用/维护说明已补充docs/natural-language-captioning-usage.md。Phase3仍in progress，Phase4 pending，goal未完成。当前唯一下一步：完成主测试矩阵复验并核销剩余失败、跳过和联网测试。

ModelScope tokenizer联网测试已限定实际JSON/TXT下载，7 passed/7.39s，原卡住单项关闭；主矩阵分区再次复验handle29013已结束（1474通过/4权限失败/25跳过/1单独验证），日志sandbox/nl-caption-eval-20261007/logs/main-tests-partition-r2-20261007.txt。不要重复启动观察同一run；结束后记录实际总数，再在修复后的源码上完整组合复验。HEAD2d56b45已提交18文件，后续ModelScope修复读最新git log。已有4个Windows权限与25个skip仍未核销，root vendor矩阵仍待处理。冻结manifest保持原样，评分approval为后来用户事件。清理被review拒绝的临时模型目录未删除，未复用。

最新HEAD读git log；本轮所有自己启动的模型/UI/测试进程均已结束，浏览器about:blank。当前Windows权限问题尚需用户处理；没有批准任何失败或skip豁免。下一轮先完成矩阵缺口审计，不重做P1探针或人工评分。用户评分只对应最初A/B精确文本。
