# 施工计划产物与门禁清单

## 当前执行范围（0.31-quick，2026-11-04 用户新授权）

2026-11-04 用户已要求快速任务书、仅针对性测试并立即继续。执行 [快速任务书](reliability-performance-20261102-task-book.md) 的 Q1 修复/出包→Q2 同包针对性实测→Q3 精准 commit/push 与简明交付；不再执行下方历史完整 Rust/42 CASE/四引擎重型矩阵强门。
已过 focused 10项、fmt、严格 Clippy 复用；两次全 Rust 180秒超时保留而不授通过。candidate10 原失败保留，candidate11 成包及实测以实际回执为准。
R0/R1 done；R2/R3 在途目标按快速计划完成；未测如实记录。不开真实训练、不下载/加载训练模型、不动用户数据，不恢复下载预算。
以下旧范围、阶段状态、下一动作和 Goal 字样仅作历史，均不覆盖本层用户新授权；当前进度与单一下一动作见快速任务书，自动继续执行。

## 历史规划与记录（不再作为执行指令）


## 当前审阅与执行基线（v0.29）

R0/R1 done，R2/R3 in progress，R4–R6 pending；仅 RP-EXIT-R0/R1 已签，专项与全局验收均 incomplete。candidate10 已构建冻结并完成 v7 绑定；定向 7/0/0、完整 Rust 434/0/15、fmt 与严格 Clippy 通过，仅属于对应冻结输入。真实预览 legacy-v7-preview-only-01 在确认前 fail，错误为“恢复候选计划与固定根/编译锁或原文摘要不符”；具体失败字段尚未定位。confirmed=false、无工具写 invoke、未产生 worker；真实关闭/退出、自然 exit0/Job 排空及独立失败保护比较通过，不能授业务、worker/reader 取消或性能通过。

本层为 v0.29 文档归一化，保留既有执行授权和 Goal，不创建、重置或标记工具 Goal 完成。本轮只整理文档。下方 v0.26 历史快照、旧阶段记录及“08 未构建/10 待构建”等描述仅是原时间点事实，不能作为现行操作指令。07/execution-ledger.json 和 continuation-current.md 尚停在 10 构建中；本次保留原件，最新事实以 candidate10 admission、v7 binding、native-report 与 host-status 为准。

当前唯一下一步：先只读拆分 candidate10 预览的组合校验拒绝，逐字段比较历史 plan 自摘要、schema/kind/rebuild、release/engine/profile、固定 recipe/lock、四 write_roots、profile_writes 与 main_env_fallback，定位具体不匹配项并落盘。当前只证实组合校验拒绝，不能预断是摘要、根或锁错误。定位后按原授权最小修复及正反例合同→当前输入质量门→冻结后继候选与显式 supersedes 新批次→正式只读预览；预览真正通过后才续三取消、强杀恢复及 A/B/C，继而完成 R2–R6。禁止删除/隔离保留候选、改历史 plan/journal、伪造 receipt/pending 或直接刷新原失败时钟重跑。

本次 v0.29 八产物原稿、来源摘要、非文档文件保护及文档检查回执：`E:/OpenSourceTeamWork/workspace/tools/launcher-reliability-20261102/planning/review-plan-v029-20261103T121203Z`。模式延续既有 Full 体系的 Standard 增量归一化；任务/目标/开工清单仍合并于专项任务书，不增竞争性计划。

## 历史文档交付快照（v0.26-review）

本轮整理问题、优化方案、针对性实测与Goal提示词；文档工作不追加产品修复、构建、沙盒操作、commit或push。既有修复、执行授权、active Goal及阶段进度保留；已在途外部工具的轻合同收口单列，不冒充产品验收。

- **问题范围：** 恢复自阻挡、检查无反馈且不能取消、重装确认窗迟出、维护与启停慢；补原8失败行、AI Toolkit/Anima Fast共10遗漏按钮。T1–T5、R0–R6、42 CASE、52引擎展开及26条历史未闭项不缩减。
- **质量事实：** `uv-resource-fmt-02` exit0；`uv-resource-full-rust-03` 实际415通过/0失败/15忽略，两者均在本次错误出口修复之前。`legacy-errors-focused-01` 为7通过/2失败/2忽略，两个新增夹具问题已改但未复跑；四文件错误合同修复后的六合同、整树fmt/完整Rust/严格Clippy均待验证，不能沿用旧通过。
- **新增P1与方案：** `ControlledProcessReapFailed`在通用终态、deadline/rollback、旧resume watchdog及持久化失败出口曾被改写。四文件已作最小修复，尚待验证；正常落盘保持`Failed/worker_reap_failed`，持久化失败保typed错误并说明未保存、保留旧attached现场，不伪报恢复成功。详任务书RP-REAP-ERROR-01。
- **候选与工具：** candidate07已构建但固定uv EXE的67,598,848 B超过旧32MiB门，产品原生not-run；candidate08未构建。v4原46项工具合同通过仍绑定07；v5的verification-03已通过31项Node＋67项Python纯合同、14条Node语法及16份Python AST/compile检查，工具源码前后SHA一致、v4原件未变；仅证明外部工具。08身份接入、复验冻结与产品原生均未验，不可直接原生。回执为`<run>/R2/execution-resume-20261103-03/native-tool-preparation-v5/verification-03/verification.json`。
- **执行边界：** R0/R1 done，R2/R3 in progress，R4–R6 pending；仅RP-EXIT-R0/R1已签。专项和全局验收均incomplete。不训练、不加载/下载训练模型、不恢复产品下载预算；测试资源上界仅约束本次Agent操作。

本次八文档原稿、保护SHA、文档校验及审阅证据：`E:/OpenSourceTeamWork/workspace/tools/launcher-reliability-20261102/planning/review-plan-v026-20261103T104556Z/`。实际执行台账：`E:/OpenSourceTeamWork/workspace/tools/launcher-reliability-20261102/run-20261102T130200Z/R2/execution-resume-20261103-06/execution-ledger.json`；原审查及修复回执与测试原件分别保留，不覆盖旧失败。既有远端核验回执为同目录`remote-before.json`：2026-11-03T10:34:46Z的远端/本地均为`d409b00bac3bcb3e7ef56b424c8946f240e0a38f`，本次文档交付未新发起网络Git。

## 当前追加 CR-020：可靠性与性能修复规划

- 日期：2026-11-03（Asia/Shanghai；v0.29 文档归一化）；Plan ID：`desktop-launcher-reliability-20261102`；Version：`0.29`。
- 模式：既有Full体系的Standard增量归一化；目标/任务/阶段开工清单合并到task-book，来源/MVP/文档复盘合并到readiness；共用治理沿既有文件。所有硬门保留，不新增平行canonical。
- 唯一总控：`00_总控目标索引.md`。现状R0/R1 done、R2/R3 in progress、R4–R6 pending；R2–R4未签，专项incomplete。Execution readiness：`executing`；Root继续既有Goal施工，本轮同步规划，不改产品/工具或Goal。
- 当前HEAD实核`d409b00bac3bcb3e7ef56b424c8946f240e0a38f`，最新产品增量未commit/push；远端沿10:34:46Z同SHA回执，本轮未新联网。

| 必需产物 | 合并职责 | 当前文档/执行边界 |
| --- | --- | --- |
| README.md | 入口 | v0.29当前入口，v0.26历史原稿保留 |
| plan-manifest.md | 产物/模式/门映射 | 本表；产品门不由文件存在授pass |
| 00_总控目标索引.md | 唯一总进度 | R0/R1事实保留，R2/R3在途 |
| reliability-performance-20261102-task-book.md | T1–T5目标、R0–R6任务、开工/完成门、决策/台账/资源 | 10输入质量/构建/v7绑定与预览业务fail/失败保护和退出限定pass分列；组合校验具体字段待查，R2–R6未闭 |
| reliability-performance-20261102-acceptance.md | 42CASE、旧8行/10按钮/52单元、6类测试及证据schema | 原42主表及旧映射保持；历史候选保全所有权补验归CASE-R2-12，不加模板/重型轮次 |
| reliability-performance-20261102-readiness.md | 来源、最小探针、GATE00–14及逐份复盘 | GATE-11 conditional；10真实预览fail，逐字段诊断、后继完整保护与生产Job/事务原生待证 |
| 03_goal提示词/启动器可靠性与性能修复_20261102_goal提示词.md | 完整续执行提示词 | v0.29只读定位10组合校验→最小修复/正反例→后继当前质量/候选/新批次预览；通过后续原链至R6，不改工具Goal |
| 00_预检证据/change-control-governance.md | CR-020连续性、授权与反漂移 | 原稿已归档，旧失败不改 |

阶段/目标映射：T1→R1；T2→R2/R5；T3→R3；T4→R4；T5→R5/R6；R0提供基线。10输入质量/构建与v7绑定已有限定通过，10业务fail，组合校验具体字段待定位；产品门R0/R1 signed、R2–R6 unsigned，整体incomplete。唯一下一动作见task-book末尾。

证据：现run为`E:/OpenSourceTeamWork/workspace/tools/launcher-reliability-20261102/run-20261102T130200Z/`；本次原稿/保护SHA/文档校验与续接在`E:/OpenSourceTeamWork/workspace/tools/launcher-reliability-20261102/planning/review-plan-v026-20261103T104556Z/`。旧candidate05/06、03失败及04/full01/full02/Clippy02均保留各自身份；本轮不运行产品或沙盒。

**CR-019当前状态：incomplete。** 全量验收证据已交付，227行193通过/24部分通过/8失败/1受阻/1待复核；52引擎单元另列。旧“仅冒烟”不限制当前功能实测，未开始训练。专项A0–A5原始过程见[原任务书](full-acceptance-20261101-task-book.md)，不能使用历史执行中快照替代最终结果。

**交付后产品修正 CR-007（2026-10-30）：** 用户要求立即取消强制下载额度，默认允许下载、累计上限改为高级可选项。实现/定向验证/新制品状态以[总控](00_总控目标索引.md)和[补丁记录](download-policy-followup.md)为准；原施工阶段与历史验证不重开。

该增量施工、定向回归、重建安装器/便携包及新 EXE 原生 13 项冒烟已完成。新制品以 `3d892c86d2041662786184bca4370613ed50732e` 构建，最终普通 push/远端完整 SHA 见本 run 的 `changes/CR-007/git-baseline.json`。

**现行执行 v0.6 / CR-006（2026-10-29，用户已要求）。** M1–M5 连续完成施工，阶段之间只核依赖、编译/类型检查和最小冒烟，保存一次开发基线后自动推进；所有综合原生/安装/故障实测集中到 M6 的统一沙盒验证。四引擎仅小夹具冒烟，真实引擎安装/损坏修复、GPU/模型/训练/权重实测仍 `skip + CR-004`。取消候选/成本后暂停、两轮或单包单案停锁、阶段间再次审批、C/S 双重保存和逐阶段真实矩阵。一般失败先诊断修复并补最短受影响检查，不结束 Goal；仅新增必要授权、硬预算或无法隔离的真实资料风险可中断。旧记录保留，未验证不作 pass。


## 历史M阶段计划与门禁（保留原时间，现行CR-020见上方）

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

## 历史M阶段防漂移与当时下一动作

阶段名和 ID 保留 M0–M6。CR-006 取代旧候选暂停、单包/单案次数及 C/S 双重保存调度；历史事实保留。每阶段一次精确 commit/普通 push/远端 SHA 核对后继续，最终统一沙盒与报告。当前仅文档变更，实际执行未由本侧聊启动。

历史当时下一步：读取v0.6 Goal推进M1–M6；该动作已被顶部CR-020及现行任务书替代，不能据此重开M阶段。
