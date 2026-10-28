# 施工计划产物与门禁清单

## 计划元数据

- Plan ID：`desktop-launcher-full-20261028`；Version：`0.1`；Last updated：2026-10-28（Asia/Shanghai）。
- Scale mode：Full。原因：跨Rust/Python/UI的长期新功能、真实GPU、资料迁移、可信更新和Windows分发；保留全部施工体系产物，无合并删除硬门。
- Route / method：新功能＋迁移＋发布准备＋测试；SDD（规格驱动）＋架构/合同＋验收场景；不涉及LLM评测，EDD不适用。当前仅规划。
- Canonical progress file：[00_总控目标索引](00_总控目标索引.md)。Related handoff：none。
- Current branch：`feat/desktop-launcher`；起始HEAD：`9ca2de963122f34599e34e5ff382199de9188811`；已有功能尚未提交。
- Current active phase：M0；Execution readiness：`executing`；用户已明确开始执行，实时进度见唯一总控，其余阶段pending。
- Spec：[后续设计书0.1](../../design/desktop-launcher-next-design.md)，按D1–D6推荐方案与0.1预算执行，授权原文见总控/用户审计单。历史[底座计划](../desktop-launcher-foundation-plan/00_总控目标索引.md)作为完成证据保留，不由本计划重开。
- Source materials：[预检复盘](00_预检证据/preflight-source-review.md)、issue #516保存快照、用户本轮硬要求、当前Git/硬件只读核对。
- Evidence roots：`E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/planning/`；后续`<run-id>/M0..M6/`。重型根提案`F:/NextTrainerLauncherSandbox/<run-id>/`，当前未创建。

## 必需产物清单

42个产物：41份Markdown与1份静态验证器；每个路径都由验证器核对，产物存在不等于执行门通过。

| 路径 | 作用 |
| --- | --- |
| [README.md](README.md) | 用户阅读入口 |
| [plan-manifest.md](plan-manifest.md) | 本清单 |
| [00_总控目标索引.md](00_总控目标索引.md) | 唯一执行进度 |
| [06_开工前最终复盘报告.md](06_开工前最终复盘报告.md) | 开工判定 |
| [07_用户审计单.md](07_用户审计单.md) | 当前用户审核入口 |
| [01_目标计划书/00_目标计划书索引.md](01_目标计划书/00_目标计划书索引.md) | 七阶段入口 |
| [03_goal提示词/桌面启动器全程执行_goal提示词.md](03_goal提示词/桌面启动器全程执行_goal提示词.md) | 批准后全程启动草稿 |
| [05_最小可行性验证/minimal-feasibility-probe-plan.md](05_最小可行性验证/minimal-feasibility-probe-plan.md) | 分期最小探针 |
| [05_最小可行性验证/feasibility-probe-report.md](05_最小可行性验证/feasibility-probe-report.md) | 当前not-run报告 |
| [scripts/validate_plan.py](scripts/validate_plan.py) | 静态验证器 |
| [00_预检证据/README.md](00_预检证据/README.md) | 治理/模板 |
| [00_预检证据/preflight-source-review.md](00_预检证据/preflight-source-review.md) | 治理/模板 |
| [00_预检证据/gate-validation-checklist.md](00_预检证据/gate-validation-checklist.md) | 治理/模板 |
| [00_预检证据/testing-and-evidence-governance.md](00_预检证据/testing-and-evidence-governance.md) | 治理/模板 |
| [00_预检证据/risk-and-authorization-governance.md](00_预检证据/risk-and-authorization-governance.md) | 治理/模板 |
| [00_预检证据/git-baseline-governance.md](00_预检证据/git-baseline-governance.md) | 治理/模板 |
| [00_预检证据/change-control-governance.md](00_预检证据/change-control-governance.md) | 治理/模板 |
| [00_预检证据/stage-completion-gate-template.md](00_预检证据/stage-completion-gate-template.md) | 治理/模板 |
| [00_预检证据/failure-report-template.md](00_预检证据/failure-report-template.md) | 治理/模板 |
| [00_预检证据/evidence-cleanup-report-template.md](00_预检证据/evidence-cleanup-report-template.md) | 治理/模板 |
| [00_预检证据/feasibility-probe-report-template.md](00_预检证据/feasibility-probe-report-template.md) | 治理/模板 |
| [01_目标计划书/01_目标M0_审核冻结与开发基线_实施验收计划.md](01_目标计划书/01_目标M0_审核冻结与开发基线_实施验收计划.md) | M0目标 |
| [02_长程任务书/阶段M0_审核冻结与开发基线_目标M0_长程任务书.md](02_长程任务书/阶段M0_审核冻结与开发基线_目标M0_长程任务书.md) | M0任务 |
| [04_阶段开工清单/阶段M0_审核冻结与开发基线_执行前清单.md](04_阶段开工清单/阶段M0_审核冻结与开发基线_执行前清单.md) | M0硬前置 |
| [01_目标计划书/02_目标M1_可靠安装与精准修复_实施验收计划.md](01_目标计划书/02_目标M1_可靠安装与精准修复_实施验收计划.md) | M1目标 |
| [02_长程任务书/阶段M1_可靠安装与精准修复_目标M1_长程任务书.md](02_长程任务书/阶段M1_可靠安装与精准修复_目标M1_长程任务书.md) | M1任务 |
| [04_阶段开工清单/阶段M1_可靠安装与精准修复_执行前清单.md](04_阶段开工清单/阶段M1_可靠安装与精准修复_执行前清单.md) | M1硬前置 |
| [01_目标计划书/03_目标M2_首批引擎真实闭环_实施验收计划.md](01_目标计划书/03_目标M2_首批引擎真实闭环_实施验收计划.md) | M2目标 |
| [02_长程任务书/阶段M2_首批引擎真实闭环_目标M2_长程任务书.md](02_长程任务书/阶段M2_首批引擎真实闭环_目标M2_长程任务书.md) | M2任务 |
| [04_阶段开工清单/阶段M2_首批引擎真实闭环_执行前清单.md](04_阶段开工清单/阶段M2_首批引擎真实闭环_执行前清单.md) | M2硬前置 |
| [01_目标计划书/04_目标M3_四引擎与可信更新_实施验收计划.md](01_目标计划书/04_目标M3_四引擎与可信更新_实施验收计划.md) | M3目标 |
| [02_长程任务书/阶段M3_四引擎与可信更新_目标M3_长程任务书.md](02_长程任务书/阶段M3_四引擎与可信更新_目标M3_长程任务书.md) | M3任务 |
| [04_阶段开工清单/阶段M3_四引擎与可信更新_执行前清单.md](04_阶段开工清单/阶段M3_四引擎与可信更新_执行前清单.md) | M3硬前置 |
| [01_目标计划书/05_目标M4_资料导入与兼容回退_实施验收计划.md](01_目标计划书/05_目标M4_资料导入与兼容回退_实施验收计划.md) | M4目标 |
| [02_长程任务书/阶段M4_资料导入与兼容回退_目标M4_长程任务书.md](02_长程任务书/阶段M4_资料导入与兼容回退_目标M4_长程任务书.md) | M4任务 |
| [04_阶段开工清单/阶段M4_资料导入与兼容回退_执行前清单.md](04_阶段开工清单/阶段M4_资料导入与兼容回退_执行前清单.md) | M4硬前置 |
| [01_目标计划书/06_目标M5_独立壳与Windows分发_实施验收计划.md](01_目标计划书/06_目标M5_独立壳与Windows分发_实施验收计划.md) | M5目标 |
| [02_长程任务书/阶段M5_独立壳与Windows分发_目标M5_长程任务书.md](02_长程任务书/阶段M5_独立壳与Windows分发_目标M5_长程任务书.md) | M5任务 |
| [04_阶段开工清单/阶段M5_独立壳与Windows分发_执行前清单.md](04_阶段开工清单/阶段M5_独立壳与Windows分发_执行前清单.md) | M5硬前置 |
| [01_目标计划书/07_目标M6_从零沙盒最终验收_实施验收计划.md](01_目标计划书/07_目标M6_从零沙盒最终验收_实施验收计划.md) | M6目标 |
| [02_长程任务书/阶段M6_从零沙盒最终验收_目标M6_长程任务书.md](02_长程任务书/阶段M6_从零沙盒最终验收_目标M6_长程任务书.md) | M6任务 |
| [04_阶段开工清单/阶段M6_从零沙盒最终验收_执行前清单.md](04_阶段开工清单/阶段M6_从零沙盒最终验收_执行前清单.md) | M6硬前置 |

## 门禁、验证和执行状态

| 类别 | 当前结果 | 证据/解释 |
| --- | --- | --- |
| 技能依赖预检 | pass | 7 skills / 4 routing cases，本轮运行；对应工作流Full规划能力已保留 |
| 计划静态结构 | 以planning/plan-validation.json为准 | UTF-8、路径、manifest、七阶段/六测试、代码围栏、空白与92文件保护；不验证产品 |
| 独立文档审查 | 以06复盘引用报告为准 | 架构执行、需求Goal、资源沙盒三路审查 |
| GATE-00–10、12–13 | 文档级pass | [编号清单](00_预检证据/gate-validation-checklist.md)；GATE12只检查Goal草稿一致性 |
| GATE-11、14 | pending | 无用户批准/真实资源与分期技术probe证据，不可以直接M1 |
| EXIT-M0–M6 | 全pending | 见唯一总控台账；本轮无commit/push/训练/安装 |

未来推进先更新总控，再同步本manifest的阶段指针/证据索引，不建立第二份阶段完成台账。用户批准后只先解锁M0安全准备，技术门按阶段续查；最终A1–A10和M6四引擎/干净OS不接受默默降级。

## 防漂移和唯一下一动作

阶段名、ID和顺序固定M0–M6。规格/预算/验收变化按CR记录同步全部受影响文档，保留首次失败与历史已验证状态。每阶段遵守代码C/状态S两次基线保存与外部最终回执，普通push不改写历史。提示词保持草稿直到用户明确批准且启动执行。

唯一下一步：完成M0基线验证与资源/安全探针，按实际结果保存远端开发基线，M0未过不进入M1。
