# 施工计划产物与门禁清单

> 当前修订0.3（2026-10-29）：用户已批准[CR-001指定GPU验收skip及CR-002资源时点调整](00_预检证据/change-control-governance.md)。P1实际结果仍blocked，调度另记deferred by CR-002，由M5在相关系统动作/Phase6专项开始前闭合。M1–M4独立新根真实实测、M5资源硬门、M6同一最终包从零及原预算不变；M0仍待正式退出，M1未开，不能把本次批准当作阶段done。

## 计划元数据

- Plan ID：`desktop-launcher-full-20261028`；Version：`0.3`；Last updated：2026-10-29（Asia/Shanghai，CR-002用户批准后的合同同步）。
- Scale mode：Full。原因：跨Rust/Python/UI的长期新功能、真实GPU、资料迁移、可信更新和Windows分发；保留全部施工体系产物，无合并删除硬门。
- Route / method：新功能＋迁移＋发布准备＋测试；SDD（规格驱动）＋架构/合同＋验收场景；不涉及LLM评测，EDD不适用。M0执行已开始，当前按CR-001/002待正式退出；P1历史blocked由M5承接。
- Canonical progress file：[00_总控目标索引](00_总控目标索引.md)。Related handoff：none。
- Current branch：`feat/desktop-launcher`；起始HEAD：`9ca2de963122f34599e34e5ff382199de9188811`；WIP `f8ed00b8c3424777bec5600ef6482838b9e1b2e6`已普通push且远端核对成功，不代表M0完成。
- Current active phase：M0；Execution readiness：`executing`（按CR-001/002复审其余M0门与阶段保存）；用户继续执行授权有效，工具状态见总控，M0尚未done，其余阶段pending。
- Spec：[后续设计书0.3](../../design/desktop-launcher-next-design.md)，按D1–D6推荐方案、CR-001/002及原0.1预算执行，授权原文见总控/用户审计单。历史[底座计划](../desktop-launcher-foundation-plan/00_总控目标索引.md)作为完成证据保留，不由本计划重开。
- Source materials：[预检复盘](00_预检证据/preflight-source-review.md)、issue #516保存快照、用户本轮硬要求、当前Git/硬件只读核对。
- Evidence roots：`E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/planning/`；执行run为`desktop-launcher-full-20261028-155831Z-f6c00a`，证据在`<run-id>/M0/`，CR-002授权在`<run-id>/changes/CR-002/authorization.json`。F同run标记根保留M0夹具/新Python/Torch partial及历次VM/失败，具体实测和保留状态见总控，不用历史资产抵扣后续新根验收。

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
| [05_最小可行性验证/feasibility-probe-report.md](05_最小可行性验证/feasibility-probe-report.md) | M0真实结果与阻塞报告 |
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
| GATE-00–10、12–13 | 计划/授权记录pass | [编号清单](00_预检证据/gate-validation-checklist.md)；GATE12包含实际Goal记录，不代表产品通过 |
| GATE-11、14 | pass-with-boundary（M0验证范围） | 外部M0/exit-M0-final-review-CR002.md已核无本阶段未关P0/P1；CR-001指定skip/P3分期，P1实际就绪由M5承接；C/S保存待执行，M1未解锁 |
| EXIT-M0 | pass-with-boundary（状态S最终回执见总控） | 调整范围实证/独审/报告通过，完成C已远端确认；M0/baseline-final.json确认S后进入M1，失败不解锁 |
| EXIT-M1–M6 | pending | 见唯一总控台账；未执行后续开发/训练/最终验收 |

未来推进先更新总控，再同步本manifest的阶段指针/证据索引，不建立第二份阶段完成台账。M1–M4仍用独立新根真实测试，不能冒充干净OS；P1合法可用、可启动且缺WebView2的资源在M5相关系统动作/Phase6专项开始前必须齐备，未齐即停且M5不得完成。M6仍在M0–M5完整退出/push后使用最终同一包从零复验；CR-002不再延期该资源门，CR-001以外必测不降级。

## 防漂移和唯一下一动作

阶段名、ID和顺序固定M0–M6。规格/预算/验收变化按CR记录同步全部受影响文档，保留首次失败与历史已验证状态。每阶段遵守代码C/状态S两次基线保存与外部最终回执，普通push不改写历史。实际Goal已启动；不能把提示词文件或WIP保存视为阶段通过。

唯一下一步：按总控完成CR-002同步后的其余M0门、独立复审、完成报告与C/S保存，再评估EXIT-M0→M1；保留P1历史blocked和M5承接条件，不再索取已豁免GPU机器。

当前阶段指针：M0退出证据见外部M0/stage-completion.md、exit-M0-final-review-CR002.md及baseline-code.json/baseline-final.json；状态S确认后下一施工为M1 P6。旧pending段落仅表示其写入时快照，实时状态只以总控及回执为准。
