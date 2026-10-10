# 规划 gate 审查

2026-10-11：本表仅评价规划。用户已明确恢复全面执行；AC-U0已签署，实际阶段证据见主任务书和U0完成门；U1–U6仍需各自证据。

| Gate | 名称 | 状态 | 证据与结论 |
|---|---|---|---|
| GATE-00 | 资料来源可信 | pass | [feature/dev快照、模拟合并与来源已归档](preflight-source-review.md) |
| GATE-01 | Canonical唯一 | pass | [原主任务书更新，阶段文件不另记进度](../../natural-language-captioning-task-book.md) |
| GATE-02 | 总目标可验收 | pass | [T1–T7与AC-U0…6闭环](../00_总控目标索引.md) |
| GATE-03 | 范围和授权 | pass | [Agent等范围外，用户数据与运行时Key保护](risk-and-authorization-governance.md) |
| GATE-04 | 目标覆盖 | pass | [RQ-01…14映射目标和阶段](../01_目标计划书/01_适配与模型统一实施验收计划.md) |
| GATE-05 | 目标可测试 | pass | [逐目标测试、证据与最终候选要求](../01_目标计划书/01_适配与模型统一实施验收计划.md) |
| GATE-06 | 阶段可执行 | pass | [U0–U6均有步骤、输出、完成与验证](../02_长程任务书/U0_本地合并与开发基线冻结.md) |
| GATE-07 | 阶段可失败 | pass | [各阶段均写失败退回，不能降门](failure-report-template.md) |
| GATE-08 | 开工清单完整 | pass | [每阶段入口及不满足处理明确](../04_阶段开工清单/U0_本地合并与开发基线冻结_执行前清单.md) |
| GATE-09 | 证据治理完整 | pass | [测试/失败/完成/清理/探针模板齐全](testing-and-evidence-governance.md) |
| GATE-10 | 真实测试受控 | pass | [远程120次、磁盘60GiB和30GiB余量、本地探针与清理界限](testing-and-evidence-governance.md) |
| GATE-11 | MVP假设已处理 | pass-with-boundary | [新模型未实测，用户指定在U0后U1验证；仅允许U0开工，U2受AC-U1阻挡](../05_最小可行性验证/minimal-feasibility-probe-plan.md) |
| GATE-12 | goal一致 | pass | [完整阶段顺序、边界、沙盒就绪关闭及人验后续一致](../03_goal提示词/最新dev适配与Qwen统一_goal提示词.md) |
| GATE-13 | 变更控制 | pass | [冻结基线、证据继承、模型变更重测及续接规则](change-control-governance.md) |
| GATE-14 | 最终复盘可追溯 | pass-with-boundary | [文档定稿，U0现场保留且goal已暂停；用户要求暂停施工](../06_开工前最终复盘报告.md) |

GATE-11不是免测：模型可行性按用户指定延期至合并后U1，必须通过才可冻结默认。GATE-14允许计划交付，不自动启动施工。
