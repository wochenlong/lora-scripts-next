# 施工计划产物与门禁清单

## 当前追加 CR-020：可靠性与性能修复规划

- 日期：2026-11-03 12:35；专项Plan ID：`desktop-launcher-reliability-20261102`；版本`0.15-executing`（R1阶段签收增量）。R0/R1 done，RP-EXIT-R1按正式恢复缺陷及保护范围签收；R2可取消引擎检查任务active（in progress），R3必要前置in progress，R4–R6 pending。candidate05下native04真实UI取消留下合法committing事务，新进程正式GUI recover04 succeeded、intent committed并绑定g1208b56f57f3e752，正式IPC重复恢复也succeeded。两原生suite/host均pass，资料/控制保护及自然Job/CDP回收通过。当前full Rust344pass/0fail/15ignored，60份Rust/Cargo输入与当前及candidate05一致。R1-04按参数证据pass-with-boundary，不夸全GUI矩阵；R1-06最终CAS合同及实际命中原生window通过，分块取消/性能时限仍属R2/R4，未外推。Anima Fast停服full单配置实测suite/host通过，首反馈1.9ms、任务ID可见上界17.1ms、完整检查保守285776.1982–285935.7808ms，worker/readers回收及控制/资料保护通过；仅授该配置，取消与余三引擎未验。旧native02/03失败保留，recover03禁止。R2–R4门未签，嵌套Operation取消盲区仍待修。R1阶段Git保存待做，当前增量未提交/未push；整个专项/既有active Goal尚未完成。
- 唯一canonical progress file：[既有总控](00_总控目标索引.md)；专项细节在新任务书，不建立第二套总控。
- 模式：既有Full体系的`plan system update`，用下表合并产物保留所有硬门，不另复制七套模板。目标/阶段/清单/证据/探针/Goal/复盘皆有唯一归属。
- 最初规划前历史基线：本地/远端`91e3d2e62a5b31865f8c56a0f321418aa887ecd3`；FINAL06产品`4e1b4cc78939e8b906252b27dcc20692ad347a08`，EXE SHA`11804c053d8667b1c9b91512d72055481aeb27d58be2ac32d181ede42413cbca`；当前续接为R0保存基线`9135fad8259cdf8b41efdd79ad37ca0b0b739d83`及未提交R1–R4必要前置增量。
- 阶段：R0 基线与测量 → R1 恢复自阻挡 → R2 可取消引擎检查任务 → R3 重装预览弹窗 → R4 扫描与启停性能 → R5 最终同包定向沙盒回归 → R6 交付。R0/R1 done，RP-EXIT-R1按正式恢复缺陷及保护范围签收；R2可取消引擎检查任务active（in progress），R3必要前置in progress，R4–R6 pending。candidate05下native04真实UI取消留下合法committing事务，新进程正式GUI recover04 succeeded、intent committed并绑定g1208b56f57f3e752，正式IPC重复恢复也succeeded。两原生suite/host均pass，资料/控制保护及自然Job/CDP回收通过。当前full Rust344pass/0fail/15ignored，60份Rust/Cargo输入与当前及candidate05一致。R1-04按参数证据pass-with-boundary，不夸全GUI矩阵；R1-06最终CAS合同及实际命中原生window通过，分块取消/性能时限仍属R2/R4，未外推。Anima Fast停服full单配置实测suite/host通过，首反馈1.9ms、任务ID可见上界17.1ms、完整检查保守285776.1982–285935.7808ms，worker/readers回收及控制/资料保护通过；仅授该配置，取消与余三引擎未验。旧native02/03失败保留，recover03禁止。R2–R4门未签，嵌套Operation取消盲区仍待修。R1阶段Git保存待做，当前增量未提交/未push；整个专项/既有active Goal尚未完成。

| 当前产物 | 职责/合并的必需能力 | 状态 |
| --- | --- | --- |
| [README.md](README.md)、[00_总控目标索引.md](00_总控目标索引.md) | 当前入口、唯一总控、范围、专项和全局完成口径 | 已更新为执行状态 |
| [reliability-performance-20261102-task-book.md](reliability-performance-20261102-task-book.md) | 目标T1–T5、R0–R6、开工/退出门、进度与资源/证据/失败治理 | v0.15；audit02与completion02签R1 done，真实rollback cancel/recover/repeat通过；R2 active，R2–R4门未签 |
| [reliability-performance-20261102-acceptance.md](reliability-performance-20261102-acceptance.md) | 精确CASE、旧8行与52单元映射、六类测试适用性、指标、截图/JSON/回收证据合同 | 42模板稳定；R1代码证据与真实恢复主路径分列，R5为4完整＋4取消 |
| [reliability-performance-20261102-readiness.md](reliability-performance-20261102-readiness.md) | 资料、风险、六探针、GATE-00–14与逐份复盘 | v0.15；保留12:25原稿和更早历史，R1签收仅P1/保护范围，性能与全链取消仍待R2/R4 |
| [03_goal提示词/启动器可靠性与性能修复_20261102_goal提示词.md](03_goal提示词/启动器可靠性与性能修复_20261102_goal提示词.md) | 批准后连续施工/阶段push/同包实测的完整启动词 | 已获执行授权，Goal active |
| [00_预检证据/change-control-governance.md](00_预检证据/change-control-governance.md) | CR-020及沿用的变更控制；新旧验收不混淆 | 已更新 |
| [原正式报告](full-acceptance-20261101-report.md)、[历史执行记录](full-acceptance-20261101-execution-history.md)、[原任务书](full-acceptance-20261101-task-book.md) | 固定问题与失败证据；作为输入只读，不授新包通过 | 保留 |

目标到阶段：T1→R1/R5，T2→R2/R5，T3→R3/R5，T4→R0/R4/R5，T5→R5/R6。编号门禁状态以新readiness为准；GATE-11六探针完成，GATE-14放行R1精确恢复修复；资源unknown及逐案限额保留。实际run为`run-20261102T130200Z`，证据和沙盒分别位于`E:/OpenSourceTeamWork/workspace/tools/launcher-reliability-20261102/`与`F:/NextTrainerLauncherSandbox/reliability-20261102/`下，两根均已有归属标记。

唯一下一步：后续续接的唯一下一动作：由Root按原阶段授权核对R1精准变更集并保存commit/普通push及远端SHA回执；本轮文档审核不执行git保存、GUI、构建或新测试。R1业务门通过不等于远端阶段基线已保存，含R2/R3必要前置源码不代表其阶段通过。Anima full原案已结束，不等待exec96794、不重复该案；42CASE、七阶段、4完整＋4取消、原阈值/资源、旧8失败行/10未操作按钮/52单元保持。 以下M0–M6及父计划v0.6仅作历史。

**CR-019当前状态：incomplete。** 全量验收证据已交付，227行193通过/24部分通过/8失败/1受阻/1待复核；52引擎单元另列。旧“仅冒烟”不限制当前功能实测，未开始训练。专项A0–A5原始过程见[原任务书](full-acceptance-20261101-task-book.md)，不能使用历史执行中快照替代最终结果。

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
