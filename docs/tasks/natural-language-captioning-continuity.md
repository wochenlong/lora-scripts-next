# 自然语言打标续接摘要

2026-10-07；canonical progress：natural-language-captioning-task-book.md。每次继续先读goal-objective，完整目标必须包括全部前后端、完整测试/真实/人工验收和Phase4从零重建。

## 当前目标和状态

- goal文件：C:/Users/25454/.codex/attachments/33329a36-8e01-4211-b79c-a080571cde4b/goal-objective.md。
- worktree：E:/OpenSourceTeamWork/workspace/branches/feat-NL-Captioning；分支feat/NL-Captioning；HEAD e673d9a，git status clean。未push。
- 本次为progress：c0c94ed报告/轮询/编辑器冲突；25e954b共享资产/cache；3b369e8翻译prompt/reasoning兼容；e673d9a恢复/来源安全。
- Phase0/1 done（有gate-review），Phase2 in progress、已完成增量待逐项核销完成门；Phase3/4 pending。整体goal保持active，尚未交付完成。
- 最后相关后端229 passed/4 warnings/22.53s；Node22 check328 tests/51 files/13.11s，type/lint/build pass，2个已有Lint warning，build5.34s。不得等同完整矩阵。
- 宽范围1139 passed/11 failed/21 skipped，另31训练collection errors；无豁免，缺逐用例日志须恢复/复现。后续必须修复或获得明确适用批准。

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

1. 审计Phase2完成门，各项用实际证据对应；不要仅据check绿色标done。
2. Phase3安全job回滚/清理、冻结公开3–5样本/hash/rubric、真实远程中文和Qwen本地/remote-first显式fallback、ONNX三模式、cache隔离、EDD真实评分、正式Zero-Short、发布/隐私扫描。
3. 修复完整矩阵：torch/transformers/accelerate/safetensors依赖、README、Windows symlink权限、trainingstub等；无豁免不能skip。
4. API JSON schema vs SiliconFlow兼容尚需官方文档和生产路径验证，不能以P1原始探针代替当前adapter验收。真实Key由原用户提供，仅后端瞬时注入。
5. Phase4全部源码提交后fresh checkout/newvenv/newNodeci/new模型下载/newconfig/SQLite/output，从零完整复验；失败回修后再建freshroot。最终release dist从源码构建。

## 单一 Next action

审计并核销 Phase2 完成门。

Confidence medium：本批源码和证据已核对；整体完整测试、真实/人工评分、正式启动与隔离重建仍未闭环。普通修复自主，不暂停/不缩goal/不假完工。
