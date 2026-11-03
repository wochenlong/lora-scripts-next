# 桌面启动器完整交付施工计划

**本次审阅交付：长程任务书＋针对性实测矩阵＋Goal提示词。**

**当前入口：CR-020可靠性与性能修复任务书v0.15（既有active Goal继续执行）。** R0/R1 done，RP-EXIT-R1按正式恢复缺陷及保护范围签收；R2可取消引擎检查任务active（in progress），R3必要前置in progress，R4–R6 pending。candidate05下native04真实UI取消留下合法committing事务，新进程正式GUI recover04 succeeded、intent committed并绑定g1208b56f57f3e752，正式IPC重复恢复也succeeded。两原生suite/host均pass，资料/控制保护及自然Job/CDP回收通过。当前full Rust344pass/0fail/15ignored，60份Rust/Cargo输入与当前及candidate05一致。R1-04按参数证据pass-with-boundary，不夸全GUI矩阵；R1-06最终CAS合同及实际命中原生window通过，分块取消/性能时限仍属R2/R4，未外推。Anima Fast停服full单配置实测suite/host通过，首反馈1.9ms、任务ID可见上界17.1ms、完整检查保守285776.1982–285935.7808ms，worker/readers回收及控制/资料保护通过；仅授该配置，取消与余三引擎未验。旧native02/03失败保留，recover03禁止。R2–R4门未签，嵌套Operation取消盲区仍待修。R1阶段Git保存待做，当前增量未提交/未push；整个专项/既有active Goal尚未完成。 [任务书](reliability-performance-20261102-task-book.md)与[总控](00_总控目标索引.md)保存当前状态；R1审计/完成门见本run `R1/stage-evidence-audit-02.json`、`stage-completion-02.json`。

- [新长程任务书](reliability-performance-20261102-task-book.md)：四类问题、七阶段R0–R6、目标数值、开工/退出门、阶段push和失败处理。
- [针对性实测矩阵](reliability-performance-20261102-acceptance.md)：旧8失败行、四引擎及10未操作入口、协议/取消/扫描差分、最终同包真实验收与证据。
- [Goal提示词](03_goal提示词/启动器可靠性与性能修复_20261102_goal提示词.md)：后续续接的唯一下一动作：由Root按原阶段授权核对R1精准变更集并保存commit/普通push及远端SHA回执；本轮文档审核不执行git保存、GUI、构建或新测试。R1业务门通过不等于远端阶段基线已保存，含R2/R3必要前置源码不代表其阶段通过。Anima full原案已结束，不等待exec96794、不重复该案；42CASE、七阶段、4完整＋4取消、原阈值/资源、旧8失败行/10未操作按钮/52单元保持。
- [资料复盘与开工门](reliability-performance-20261102-readiness.md)、[manifest](plan-manifest.md)、[CR-020](00_预检证据/change-control-governance.md#cr-020启动器可靠性与性能修复规划)：文档/实际探针状态分列，保留旧失败及资源边界。

以下v0.6说明是历史施工入口。旧M阶段状态、训练豁免或实测调度不覆盖当前CR-019/020与最新用户指令；后续执行先读上方新入口，不重新从M1开工。

**现行执行 v0.6 / CR-006（2026-10-29，用户已要求）。** M1–M5 连续完成施工，阶段之间只核依赖、编译/类型检查和最小冒烟，保存一次开发基线后自动推进；所有综合原生/安装/故障实测集中到 M6 的统一沙盒验证。四引擎仅小夹具冒烟，真实引擎安装/损坏修复、GPU/模型/训练/权重实测仍 `skip + CR-004`。取消候选/成本后暂停、两轮或单包单案停锁、阶段间再次审批、C/S 双重保存和逐阶段真实矩阵。一般失败先诊断修复并补最短受影响检查，不结束 Goal；仅新增必要授权、硬预算或无法隔离的真实资料风险可中断。旧记录保留，未验证不作 pass。

- 唯一执行进度：[总控索引](00_总控目标索引.md)。M0 已完成、M1 施工中、M2–M6 尚未开始；新调度不伪改状态。
- 执行入口：[v0.6 Goal 提示词](03_goal提示词/桌面启动器全程执行_goal提示词.md)，主执行者据此连续施工，不再按候选/成本逐批等待。
- 功能清单：[目标索引](01_目标计划书/00_目标计划书索引.md)、各阶段[长程任务书](02_长程任务书/阶段M1_可靠安装与精准修复_目标M1_长程任务书.md)与[manifest](plan-manifest.md)。保留既定产品范围，不用减少功能代替精简测试。
- 最新变更：[CR-006](00_预检证据/change-control-governance.md#cr-006连续施工完成后统一沙盒验证与汇报)；测试时点与最小覆盖见[测试治理](00_预检证据/testing-and-evidence-governance.md)，阶段保存见[Git治理](00_预检证据/git-baseline-governance.md)。
- 历史事实：[候选报告](m1-candidate-report.md)、[成本参考](remaining-work-cost-review.md)、[既有复盘](06_开工前最终复盘报告.md)保留；其中旧暂停/轮次/阶段实测门不覆盖 CR-006。

以上旧v0.6侧聊“仅文档、不启动Goal/施工/测试/代理”的限定仅是历史批次说明，不覆盖顶部v0.15及最新用户继续执行指令。静态验证器只证明规划结构/链接一致，不证明产品可用。
