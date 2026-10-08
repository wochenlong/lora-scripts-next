# 自然语言打标证据索引（Issue #409）

本目录保存摘要、可复现命令、环境版本、样本/模型/源码hash、Profile/prompt revision、测试与失败结果、人工评分及清理报告。不得包含Key、请求头、用户图片、原始远程响应、本地绝对路径、模型/运行时二进制、venv或node_modules。

当前契约按Phase0–5执行；旧Phase编号、combined和Agent相关历史不作为本版验收依据。

- [契约/模型能力目录与浏览器](phase-0-contract-alignment/2026-10-08-model-catalog-browser.md)
- [user_data预设事务和导入](phase-0-contract-alignment/2026-10-08-preset-transactions-import.md)
- [任务归档和既有TaskManager](phase-0-contract-alignment/2026-10-08-task-archives-bridge.md)
- [Tag持久化及单图试标](phase-0-contract-alignment/2026-10-08-tag-preview-durable-ui.md)
- [当前真实模型/UI/Editor及修复](phase-4-real-evaluation/2026-10-08-real-ui-editor-and-fixes.md)
- [完整功能矩阵审计](phase-4-real-evaluation/2026-10-08-functional-matrix.md)
- [用户评分与四项跨平台环境批准](phase-4-real-evaluation/2026-10-08-user-gate-approval.json)
- [从零重建与失败重跑记录](phase-5-isolated-rebuild/2026-10-08-rebuild-execution.md)

Phase4已按用户批准的环境口径通过；候选8986b9e已在新r5根完整重建并通过所有功能/真实/浏览器检查。前四根不作为最终通过。唯一未关闭的是自动审批拒绝的Windows剩余目录清理。

- [最终逐项验收审计](phase-5-isolated-rebuild/2026-10-08-final-acceptance-audit.md)
- [原始结果与批准组合口径](phase-5-isolated-rebuild/final-8986b9e/acceptance-summary.json)
- [清理状态及拒绝原因](phase-5-isolated-rebuild/2026-10-08-cleanup-status.json)

原[人工评分事件](phase-3-evaluation/human-evaluation-approval.json)和[冻结公开样本](phase-3-evaluation/frozen-eval-manifest.json)保留；重建输出只在精确文本SHA匹配时引用已有评分。初始manifest中的空评分不得改写。远程真实历史见phase-3-evaluation；当前fresh远程Profile未配置，不能标记本轮远程通过。
