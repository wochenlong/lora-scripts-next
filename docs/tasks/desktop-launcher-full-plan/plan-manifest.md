# 施工计划产物与门禁清单

**交付后产品修正 CR-007（2026-10-30）：** 用户要求立即取消强制下载额度，默认允许下载、累计上限改为高级可选项。实现/定向验证/新制品状态以[总控](00_总控目标索引.md)和[补丁记录](download-policy-followup.md)为准；原施工阶段与历史验证不重开。

该增量施工、定向回归、重建安装器/便携包及新 EXE 原生 13 项冒烟已完成。新制品以 `3d892c86d2041662786184bca4370613ed50732e` 构建，最终普通 push/远端完整 SHA 见本 run 的 `changes/CR-007/git-baseline.json`。

**现行执行 v0.6 / CR-006（2026-10-29，用户已要求）。** M1–M5 连续完成施工，阶段之间只核依赖、编译/类型检查和最小冒烟，保存一次开发基线后自动推进；所有综合原生/安装/故障实测集中到 M6 的统一沙盒验证。四引擎仅小夹具冒烟，真实引擎安装/损坏修复、GPU/模型/训练/权重实测仍 `skip + CR-004`。取消候选/成本后暂停、两轮或单包单案停锁、阶段间再次审批、C/S 双重保存和逐阶段真实矩阵。一般失败先诊断修复并补最短受影响检查，不结束 Goal；仅新增必要授权、硬预算或无法隔离的真实资料风险可中断。旧记录保留，未验证不作 pass。

## 计划元数据

- Plan ID：`desktop-launcher-full-20261028`；Version：`0.6`；Last updated：2026-10-29（Asia/Shanghai，CR-006 连续施工/最终统一验证）。
- Scale mode：保留既有 Full 文档结构；实现跨 Rust/Python/UI、资料迁移、可信更新和 Windows 分发。验证按 CR-004 精简，不为保留结构而新增治理或强制每阶段全测试族。
- Route / method：新功能＋迁移＋发布准备＋测试；SDD（规格驱动）＋架构/合同＋验收场景；不涉及LLM评测，EDD不适用。M0已完成；当前按 CR-006 连续施工，最终系统资源仅约束 M6 对应专项。
- Canonical progress file：[00_总控目标索引](00_总控目标索引.md)。Related handoff：none。
- Current branch：`feat/desktop-launcher`；起始HEAD：`9ca2de963122f34599e34e5ff382199de9188811`；WIP `f8ed00b8c3424777bec5600ef6482838b9e1b2e6`已普通push且远端核对成功，不代表M0完成。
- Current active phase：M1 剩余施工；Execution readiness：`approved for execution`（本侧聊仅修订文档，不控制实际 Goal）。M2–M5 可按依赖连续施工，M6 最后统一验证。
- Spec：[后续设计书0.3](../../design/desktop-launcher-next-design.md)，按D1–D6推荐方案、CR-001/002、CR-003当前范围及原0.1预算执行，授权原文见总控/变更治理。历史[底座计划](../desktop-launcher-foundation-plan/00_总控目标索引.md)作为完成证据保留，不由本计划重开。
- Source materials：[预检复盘](00_预检证据/preflight-source-review.md)、issue #516保存快照、用户本轮硬要求、当前Git/硬件只读核对。
- Evidence roots：`E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/planning/`；执行run为`desktop-launcher-full-20261028-155831Z-f6c00a`，证据在`<run-id>/M0/`，CR-002授权在`<run-id>/changes/CR-002/authorization.json`。F同run标记根保留M0夹具/新Python/Torch partial及历次VM/失败，具体实测和保留状态见总控，不用历史资产抵扣后续新根验收。

## 必需产物清单

44个产物：43份Markdown与1份静态验证器；每个路径都由验证器核对，产物存在不等于执行门通过。

| 路径 | 作用 |
| --- | --- |
| [README.md](README.md) | 用户阅读入口 |
| [plan-manifest.md](plan-manifest.md) | 本清单 |
| [00_总控目标索引.md](00_总控目标索引.md) | 唯一执行进度 |
| [m1-candidate-report.md](m1-candidate-report.md) | CR-003 唯一候选包、操作与同包实测报告 |
| [remaining-work-cost-review.md](remaining-work-cost-review.md) | CR-003 后续优先级、依赖与成本审核表 |
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
| GATE-11、14 | 历史 M0 pass-with-boundary；现行规则见新版 gate 清单 | 原范围/证据及失败保留；M0 已退出，CR-006 不重开 M0，后续调度不再沿用旧 C/S 或 M5 资源门 |
| EXIT-M0 | done（原回执见总控） | 原阶段完成事实保留，M1 已进行中，不重新等待状态提交解锁 |
| EXIT-M1–M6 | pending | 见唯一总控台账；未执行后续开发/训练/最终验收 |

未来按 CR-006 更新总控并连续施工，阶段快检与最终验收分开。M1–M5 不重复真实安装/故障矩阵，M5 不因缺干净 OS 测试资源停止编码与打包；M6 统一验证对应系统专项，资源不足仅阻断该专项并最终统一说明，不虚报 pass。

## 防漂移和唯一下一动作

阶段名和 ID 保留 M0–M6。CR-006 取代旧候选暂停、单包/单案次数及 C/S 双重保存调度；历史事实保留。每阶段一次精确 commit/普通 push/远端 SHA 核对后继续，最终统一沙盒与报告。当前仅文档变更，实际执行未由本侧聊启动。

唯一下一步：主执行者读取 v0.6 Goal，完成 M1 剩余施工，连续推进 M2–M5，最后统一执行 M6。
