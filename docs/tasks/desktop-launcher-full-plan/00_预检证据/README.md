# 预检、执行门禁与证据入口

**v0.6 调度覆盖：** [CR-006](change-control-governance.md#cr-006连续施工完成后统一沙盒验证与汇报) 已取代旧候选/阶段审批暂停与逐阶段真实矩阵。M1–M5 连续施工、快速检查、一次阶段保存；M6 最终统一沙盒。资源/权限/真实资料守护继续有效；旧探针和失败只保留事实，不反复运行。本次仅修订文档，不启动执行。

本目录定义证据合同和模板，不代表真实执行已发生。唯一进度见[总控](../00_总控目标索引.md)。

| 文件 | 作用 |
| --- | --- |
| [预检资料复盘](preflight-source-review.md) | 现场事实、来源、冲突与资源缺口 |
| [编号化门禁](gate-validation-checklist.md) | GATE-00–14计划就绪门、EXIT-M0–M6阶段完成门 |
| [测试证据治理](testing-and-evidence-governance.md) | 六类验证、身份绑定、资源账本、保留/清理 |
| [风险与授权](risk-and-authorization-governance.md) | 待审预算、允许与排除范围、停止条件 |
| [Git基线协议](git-baseline-governance.md) | 每阶段精确提交/push和远端回执 |
| [变更控制](change-control-governance.md) | 规格/预算/测试变化和上下文连续性 |
| [完成门模板](stage-completion-gate-template.md) | 完成报告与退出判定 |
| [失败报告模板](failure-report-template.md) | 首次失败、影响、复现、修复与复验 |
| [清理报告模板](evidence-cleanup-report-template.md) | 根/联接保护、保留项与清理结果 |
| [探针报告模板](feasibility-probe-report-template.md) | 最小可行性结果、限额、退出码与门禁影响 |

本轮规划证据：`E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/planning/`；规划前已有92文件保护快照在同根`before-plan.json`。后续每run独立`<run-id>/M0..M6`，重型资产按获批F盘沙盒方案保存，不把VM/模型/venv/缓存写进Git。
