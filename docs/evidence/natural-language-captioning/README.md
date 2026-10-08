# 自然语言打标证据索引（Issue #409）

2026-10-09最终闭门：用户已手动清空sandboxes，实测五个剩余Windows根全部不存在，无自建模型/应用进程，Git过期worktree注册已清理。功能源码与候选8986b9e的Git内容一致（仅65项LF/CRLF checkout行尾差异）；此前全部验收证据有效。GATE10/G-11通过，Phase0–5完成，保留四项Windows原生symlink未验与本轮远程未配置的批准/可选边界。详见phase-5-isolated-rebuild/2026-10-09-cleanup-closure.json。用户要求在goal完成后另建全新手动测试项目，此为后续独立交付，不能复用已删除沙盒。

以下2026-10-08及更早条目保留为历史，当前状态以上述闭门结论和canonical任务书为准。

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

Phase4已按用户批准的环境口径通过；候选8986b9e已在新r5根完整重建并通过所有功能/真实/浏览器检查。前四根不作为最终通过。Windows剩余目录已由用户删除并于2026-10-09复核，全部完成门已关闭。

- [最终逐项验收审计](phase-5-isolated-rebuild/2026-10-08-final-acceptance-audit.md)
- [原始结果与批准组合口径](phase-5-isolated-rebuild/final-8986b9e/acceptance-summary.json)
- [清理状态及拒绝原因](phase-5-isolated-rebuild/2026-10-08-cleanup-status.json)

原[人工评分事件](phase-3-evaluation/human-evaluation-approval.json)和[冻结公开样本](phase-3-evaluation/frozen-eval-manifest.json)保留；重建输出只在精确文本SHA匹配时引用已有评分。初始manifest中的空评分不得改写。远程真实历史见phase-3-evaluation；当前fresh远程Profile未配置，不能标记本轮远程通过。

- [用户手动清理与最终闭门](phase-5-isolated-rebuild/2026-10-09-cleanup-closure.json)

- [goal完成后全新手测项目交付](phase-5-isolated-rebuild/2026-10-09-manual-test-delivery.md)

- [手测反馈：英文优先与自然语言译文增量](2026-10-09-manual-feedback-change.md)
