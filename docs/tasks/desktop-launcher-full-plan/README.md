# 桌面启动器完整交付施工计划

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

## 历史专项规划快照（v0.26-review）

更新：2026-11-03 18:45（Asia/Shanghai）。本轮交付任务书/实测矩阵/Goal，产品与沙盒不执行；保留原执行授权和工具Goal。R0/R1已完成，R2/R3在途，R4–R6待执行，专项与全局验收仍incomplete。R1保存基线`d409b00bac3bcb3e7ef56b424c8946f240e0a38f`；远端同SHA已核回执见开篇，本轮未新联网，产品增量未commit/push。

`uv-resource-fmt-02` exit0；`uv-resource-full-rust-03` 实际415通过/0失败/15忽略，两者均在本次错误出口修复之前。`legacy-errors-focused-01` 为7通过/2失败/2忽略，两个新增夹具问题已改但未复跑；四文件错误合同修复后的六合同、整树fmt/完整Rust/严格Clippy均待验证，不能沿用旧通过。 candidate07已构建但固定uv EXE的67,598,848 B超过旧32MiB门，产品原生not-run；candidate08未构建。v4原46项工具合同通过仍绑定07；v5的verification-03已通过31项Node＋67项Python纯合同、14条Node语法及16份Python AST/compile检查，工具源码前后SHA一致、v4原件未变；仅证明外部工具。08身份接入、复验冻结与产品原生均未验，不可直接原生。回执为`<run>/R2/execution-resume-20261103-03/native-tool-preparation-v5/verification-03/verification.json`。 R2及后续门未签，原生/性能未证。

原四类问题、42 CASE、旧8失败行、10遗漏按钮、52引擎展开及26条历史未闭项保留。当前待办是六合同/当前质量→08→v5接入→正式资源预览→三取消/强杀恢复→A/B/C及R2–R6；详任务书末尾。不训练、不加载模型、不恢复产品下载预算。


- [长程任务书](reliability-performance-20261102-task-book.md)：T1–T5、R0–R6、用户可见结果、分阶段开工/完成/失败、实测精简、资源及进度。
- [针对性实测矩阵](reliability-performance-20261102-acceptance.md)：42 CASE、原8失败行/10按钮/52单元、legacy独立修复与Job参数、截图/日志合同。
- [Goal提示词](03_goal提示词/启动器可靠性与性能修复_20261102_goal提示词.md)：可复制续执行，覆盖完整范围和完成边界。
- [资料复盘/开工门](reliability-performance-20261102-readiness.md)、[产物清单](plan-manifest.md)、[唯一总控](00_总控目标索引.md)：当前事实、最小前提、文档门与产品完成门分列。

本次审阅优先阅读长程任务书中的“审阅重点”和T1–T5目标表，再看42项针对性实测矩阵；产品完成与文档可审阅分开。v5的verification-03已通过31项Node＋67项Python纯合同、14条Node语法及16份Python AST/compile检查，工具源码前后SHA一致、v4原件未变；仅证明外部工具。08身份接入、复验冻结与产品原生均未验，不可直接原生。。

以下v0.6说明是历史施工入口。旧M阶段状态、训练豁免或实测调度不覆盖当前CR-019/020与最新用户指令；后续执行先读上方新入口，不重新从M1开工。

**现行执行 v0.6 / CR-006（2026-10-29，用户已要求）。** M1–M5 连续完成施工，阶段之间只核依赖、编译/类型检查和最小冒烟，保存一次开发基线后自动推进；所有综合原生/安装/故障实测集中到 M6 的统一沙盒验证。四引擎仅小夹具冒烟，真实引擎安装/损坏修复、GPU/模型/训练/权重实测仍 `skip + CR-004`。取消候选/成本后暂停、两轮或单包单案停锁、阶段间再次审批、C/S 双重保存和逐阶段真实矩阵。一般失败先诊断修复并补最短受影响检查，不结束 Goal；仅新增必要授权、硬预算或无法隔离的真实资料风险可中断。旧记录保留，未验证不作 pass。

- 唯一执行进度：[总控索引](00_总控目标索引.md)。M0 已完成、M1 施工中、M2–M6 尚未开始；新调度不伪改状态。
- 执行入口：[v0.6 Goal 提示词](03_goal提示词/桌面启动器全程执行_goal提示词.md)，主执行者据此连续施工，不再按候选/成本逐批等待。
- 功能清单：[目标索引](01_目标计划书/00_目标计划书索引.md)、各阶段[长程任务书](02_长程任务书/阶段M1_可靠安装与精准修复_目标M1_长程任务书.md)与[manifest](plan-manifest.md)。保留既定产品范围，不用减少功能代替精简测试。
- 最新变更：[CR-006](00_预检证据/change-control-governance.md#cr-006连续施工完成后统一沙盒验证与汇报)；测试时点与最小覆盖见[测试治理](00_预检证据/testing-and-evidence-governance.md)，阶段保存见[Git治理](00_预检证据/git-baseline-governance.md)。
- 历史事实：[候选报告](m1-candidate-report.md)、[成本参考](remaining-work-cost-review.md)、[既有复盘](06_开工前最终复盘报告.md)保留；其中旧暂停/轮次/阶段实测门不覆盖 CR-006。

旧v0.6只保留历史；本轮最新请求为整理任务书与Goal，因此只更新文档，既有active Goal保留。静态验证器只证明规划结构/链接一致，不证明产品可用。
