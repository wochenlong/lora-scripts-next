# CR-020：资料复盘、最小探针与文档审查

## 当前审阅与执行基线（v0.29）

R0/R1 done，R2/R3 in progress，R4–R6 pending；仅 RP-EXIT-R0/R1 已签，专项与全局验收均 incomplete。candidate10 已构建冻结并完成 v7 绑定；定向 7/0/0、完整 Rust 434/0/15、fmt 与严格 Clippy 通过，仅属于对应冻结输入。真实预览 legacy-v7-preview-only-01 在确认前 fail，错误为“恢复候选计划与固定根/编译锁或原文摘要不符”；具体失败字段尚未定位。confirmed=false、无工具写 invoke、未产生 worker；真实关闭/退出、自然 exit0/Job 排空及独立失败保护比较通过，不能授业务、worker/reader 取消或性能通过。

本层为 v0.29 文档归一化，保留既有执行授权和 Goal，不创建、重置或标记工具 Goal 完成。本轮只整理文档。下方 v0.26 历史快照、旧阶段记录及“08 未构建/10 待构建”等描述仅是原时间点事实，不能作为现行操作指令。07/execution-ledger.json 和 continuation-current.md 尚停在 10 构建中；本次保留原件，最新事实以 candidate10 admission、v7 binding、native-report 与 host-status 为准。

当前唯一下一步：先只读拆分 candidate10 预览的组合校验拒绝，逐字段比较历史 plan 自摘要、schema/kind/rebuild、release/engine/profile、固定 recipe/lock、四 write_roots、profile_writes 与 main_env_fallback，定位具体不匹配项并落盘。当前只证实组合校验拒绝，不能预断是摘要、根或锁错误。定位后按原授权最小修复及正反例合同→当前输入质量门→冻结后继候选与显式 supersedes 新批次→正式只读预览；预览真正通过后才续三取消、强杀恢复及 A/B/C，继而完成 R2–R6。禁止删除/隔离保留候选、改历史 plan/journal、伪造 receipt/pending 或直接刷新原失败时钟重跑。

## 历史文档交付快照（v0.26-review）

本轮整理问题、优化方案、针对性实测与Goal提示词；文档工作不追加产品修复、构建、沙盒操作、commit或push。既有修复、执行授权、active Goal及阶段进度保留；已在途外部工具的轻合同收口单列，不冒充产品验收。

- **问题范围：** 恢复自阻挡、检查无反馈且不能取消、重装确认窗迟出、维护与启停慢；补原8失败行、AI Toolkit/Anima Fast共10遗漏按钮。T1–T5、R0–R6、42 CASE、52引擎展开及26条历史未闭项不缩减。
- **质量事实：** `uv-resource-fmt-02` exit0；`uv-resource-full-rust-03` 实际415通过/0失败/15忽略，两者均在本次错误出口修复之前。`legacy-errors-focused-01` 为7通过/2失败/2忽略，两个新增夹具问题已改但未复跑；四文件错误合同修复后的六合同、整树fmt/完整Rust/严格Clippy均待验证，不能沿用旧通过。
- **新增P1与方案：** `ControlledProcessReapFailed`在通用终态、deadline/rollback、旧resume watchdog及持久化失败出口曾被改写。四文件已作最小修复，尚待验证；正常落盘保持`Failed/worker_reap_failed`，持久化失败保typed错误并说明未保存、保留旧attached现场，不伪报恢复成功。详任务书RP-REAP-ERROR-01。
- **候选与工具：** candidate07已构建但固定uv EXE的67,598,848 B超过旧32MiB门，产品原生not-run；candidate08未构建。v4原46项工具合同通过仍绑定07；v5的verification-03已通过31项Node＋67项Python纯合同、14条Node语法及16份Python AST/compile检查，工具源码前后SHA一致、v4原件未变；仅证明外部工具。08身份接入、复验冻结与产品原生均未验，不可直接原生。回执为`<run>/R2/execution-resume-20261103-03/native-tool-preparation-v5/verification-03/verification.json`。
- **执行边界：** R0/R1 done，R2/R3 in progress，R4–R6 pending；仅RP-EXIT-R0/R1已签。专项和全局验收均incomplete。不训练、不加载/下载训练模型、不恢复产品下载预算；测试资源上界仅约束本次Agent操作。

本次八文档原稿、保护SHA、文档校验及审阅证据：`E:/OpenSourceTeamWork/workspace/tools/launcher-reliability-20261102/planning/review-plan-v026-20261103T104556Z/`。实际执行台账：`E:/OpenSourceTeamWork/workspace/tools/launcher-reliability-20261102/run-20261102T130200Z/R2/execution-resume-20261103-06/execution-ledger.json`；原审查及修复回执与测试原件分别保留，不覆盖旧失败。既有远端核验回执为同目录`remote-before.json`：2026-11-03T10:34:46Z的远端/本地均为`d409b00bac3bcb3e7ef56b424c8946f240e0a38f`，本次文档交付未新发起网络Git。

## 资料来源与事实优先级

| 来源 | 用途及证据边界 |
| --- | --- |
| 最新用户要求、当前Git与既有Goal | 本次交付任务书/Goal；既有完整执行授权保留，工作树产品增量未提交；不创建第二总控 |
| full-acceptance-20261101-report.md / inventory.md | 旧227行、52展开单元、8失败父行及10个未操作按钮；保留原FINAL06身份，不倒写结论 |
| 本run R0、R1/stage-evidence-audit-02.json及stage-completion-02.json | R0/R1已签，R1业务保护和原包身份；不授全部时延/变体通过 |
| R2/execution-checkpoint-20261103T145207/continuation.md及后继execution-ledger | 历史执行增量与后继接线快照，当前以本次review续接为准；缺pip与依赖未装已诊断，日志/阶段修复已进入07构建，但原生未验 |
| R2/legacy-import-diagnostic-02及rp-diag/rp-progress相关回执 | 同参数真实失败原因、5/5/8/8/3/3定向通过；合同不代原生，旧全量Rust不外推当前源码 |
| R3/legacy-environment-repair-design-20261103.md | 独立离线修复设计附件；requirements外部锚与81输入一致已证，事务/Job实现和实测未完成 |
| 当前工作树/实施交接 | `uv-resource-fmt-02` exit0；`uv-resource-full-rust-03` 实际415通过/0失败/15忽略，两者均在本次错误出口修复之前。`legacy-errors-focused-01` 为7通过/2失败/2忽略，两个新增夹具问题已改但未复跑；四文件错误合同修复后的六合同、整树fmt/完整Rust/严格Clippy均待验证，不能沿用旧通过。 candidate07已构建但固定uv EXE的67,598,848 B超过旧32MiB门，产品原生not-run；candidate08未构建。v4原46项工具合同通过仍绑定07；v5的verification-03已通过31项Node＋67项Python纯合同、14条Node语法及16份Python AST/compile检查，工具源码前后SHA一致、v4原件未变；仅证明外部工具。08身份接入、复验冻结与产品原生均未验，不可直接原生。回执为`<run>/R2/execution-resume-20261103-03/native-tool-preparation-v5/verification-03/verification.json`。 |
| R2/candidate-freeze-07、legacy-resource-preflight-01/02、resource-gate-fix-01及v4/verification-01 | 07构建、资源门拒绝/外部只读身份、uv资源合同、修前415项回归与修后错误合同待验边界和工具合同分列；08未构建，不能沿旧full02授当前质量 |
| 当前task-book / acceptance / Goal / manifest | 现行目标、阶段与证据合同；旧版本归档到review目录，不保留多个相互冲突的“当前下一动作” |

`<run>`＝`E:/OpenSourceTeamWork/workspace/tools/launcher-reliability-20261102/run-20261102T130200Z`。本轮八份原稿、保护文件SHA、静态校验及续接保存于`E:/OpenSourceTeamWork/workspace/tools/launcher-reliability-20261102/planning/review-plan-v026-20261103T104556Z/`；旧review-reader-cancel目录只保留历史审阅身份。

## 最小可行性验证与剩余前提

R0原RP-PROBE-01…06已有原件并已签门，不无改动重跑。下表明确哪些仍需先验证；本次只写计划，不给这些新前提制造通过或豁免。

| ID | 关键假设/风险 | 已有依据 | 后续最小验证、限额、输出与失败处理 |
| --- | --- | --- | --- |
| RP-PROBE-01 | 恢复只对自身合法事务例外 | R0小探针及R1正式Core/GUI签收 | 保留证据；新独立修复的精确例外用CASE-R1-02/05/06再验证，不改旧签收 |
| RP-PROBE-02/03/04/06 | 启动前取消、帧协议、共享任务、控制文件不变 | R0及R2模块合同，部分真实取消限定通过 | 全请求deadline/catalog/租约/同步I/O与Job仍待真实IPC；先小夹具/受控helper每段≤120s，证据R2；失败修任务设计，不签端到端通过 |
| RP-PROBE-05 | 同观察阶段复用不弱化保护 | R0差分及R4部分扫描合同 | 实际同大小mtime篡改/链接/控制漂移；记录真实读字节，≤120s小树，证据R4；不能证明保持完整扫描 |
| RP-LEGACY-RESOURCE（历史输入见注） | 81可信原始资源可完全离线构建精确legacy env | requirements外部锚、前检02只读81资源通过；07前检01的32MiB门拒绝67,598,848 B uv，修复草稿及正式资源计划未验 | 核对已通过的RP-LEGACY-UV-01三个合同；先验RP-REAP-ERROR-01六合同及修后完整质量，保精确uv长度/配方SHA与其他上限；08后正式只读计划核Python/81资源/生成上界，缺资源写前拒绝。外部前检不代正式计划；小探针≤120s，不新增下载 |
| RP-LEGACY-TRANSACTION | 最终路径构建与marker在每个崩溃窗口可识别归属 | full02原输入legacy13项中已覆盖八个rename窗口及幂等；当前uv三个资源合同已通过，修前fmt02/full03已通过，修后完整质量未验，生产拼装与原生继续待验 | 私有小fixture逐个rename前后、预留marker、碰撞、控制漂移/幂等；复用已覆盖且输入未变合同，仅补受影响与缺口；每案≤120s，R2；失败先补状态机，不能动唯一原件 |
| RP-PIPE-01 | ChildStdout管道取消能在writer仍活时实际join | 03历史失败；04为1/1、10.6999ms、995、unjoined=false、writer活；full02原输入同名测试通过 | 管道合同限定pass；按最终输入核适用性并补真实IPC/Job/reader/logger退出；原生未验。小探针≤120s，R2；失败禁止依赖其回收能力的目录恢复 |
| RP-JOB-REAP | 正常/取消/强杀后均有精确后代排空证明 | full02原输入三个命名Job生命周期、后代handle退出及reader04已有合同；full03宿主残留已确认为MSVC vctip.exe（工具进程），强制收尾不能授产品自然回收；生产拼装、外部writer及真实强杀恢复待验 | 受控helper留后代：返回时预先持有的Child/后代进程handle必须SIGNALED、Job ActiveProcesses=0，无关进程存活；命名Job三种生命周期分支（有持柄重开/attached后精确notfound/launching保守拒绝）、强杀→重开→排空→显式恢复，以及持久worker_reap_failed屏障；错误出口和未保存边界先按任务书RP-REAP-ERROR-01六合同验证；每小探针≤120s，R2；失败worker_reap_failed/needs_attention，禁止恢复目录 |
| RP-UI-STAGE | 快照先显示后，真实阶段能及时到DOM | 实际函数/Vue refs3/3及build通过 | 新候选两个真实阶段、切日志页/返回、三轻样本事件→DOM≤1s；轻案≤10min，R2/R3；失败不授原生、先定位订阅链 |

Windows session API/feature、持久屏障、reader、marker与资源保护已有实现和部分合同；reader04及full02/Clippy02仅原输入通过，uv三个资源合同已通过，修前fmt02/full03已通过，修后完整质量未验；命名Job三个生命周期合同已有原件，不无修改重做，生产拼装/强杀恢复原生继续待验。Job active0不替reader/logger退出，full02宿主Job强制收尾也不证明产品自然排空。新legacy实操前验证错误出口六合同/当前质量、08正式资源计划、生产状态机/Job及已接08的v5工具合同并冻结，所有资源通过才写intent/搬env；三取消/kill先核验/补齐已有v5工具并接08冻结；不重做已完成的取消定位。真实离线构建/三阶段取消/强杀恢复外门360s含回收，失败保现场，未闭P1阻断相关危险动作和阶段签收；这些是既有受控修复依赖，不新增审批。

以上探针表保留 v0.26 的依据与待验设计；其中“08 后”“v5 接 08”“修后质量未验”不再是当前候选指令。10 冻结输入的定向、完整 Rust、fmt/Clippy 和 v7 绑定已有通过；10 正式预览 fail、无 worker。现行下一步以开篇 v0.29 为准，后继改动仅按影响核适用性；完整保护、生产事务/Job、三取消和强杀恢复仍须实测。

## 阶段开工与完成门

任务书每个R阶段均合并目的、状态、开工清单、步骤输出、验证、完成门与失败处理。公共清单覆盖文档、上阶段门、Git/归属、资源、备份、证据和回收。R0/R1 done；R2/R3 in progress；R4–R6 pending。R1业务门不能代替R2/R4时延；R2/R3共用前置可先修再回原门，不改变签收顺序。

| 门 | 现状 | 进入下一门的条件 |
| --- | --- | --- |
| RP-EXIT-R0 | signed | 原探针/基线保持，资源每重案再核 |
| RP-EXIT-R1 | signed | 原身份业务签收保持；后续相关修改按影响回归 |
| RP-EXIT-R2 | unsigned | 独立env修复/续办/服务前置、全链任务/取消及真实大引擎达标 |
| RP-EXIT-R3 | unsigned | 两包场景真实准备窗/计划/取消/键盘/焦点及时且正确 |
| RP-EXIT-R4 | unsigned | 完整性保护不弱化、扫描/修复/重建/启停/取消指标真实通过 |
| RP-EXIT-R5 | unsigned | 最终同包空根主链及四引擎/旧失败必测通过 |
| RP-EXIT-R6 | unsigned | 最终报告/矩阵/图集/分发SHA、阶段远端回执和回收齐备 |

## Gate编号化文档审查

以下是计划完整性审查，和上表产品阶段门分开。`plan-pass`只表示要求已落盘；`conditional`表示具体执行前提仍未验证，不得读成MVP或产品通过。

| Gate | 归并产物/审查点 | 文档结论与边界 |
| --- | --- | --- |
| GATE-00 | 来源、当前Git、旧验收身份 | plan-pass；远端同SHA回执已核，本轮未新联网 |
| GATE-01 | 事实/假设/决策/未知分开 | plan-pass；缺pip已知，Job/性能未证明确列出 |
| GATE-02 | T1–T5及最终状态 | plan-pass；有用户可见结果和数值目标 |
| GATE-03 | 范围、依赖及禁止事项 | plan-pass；不训练、不恢复产品预算、单GUI |
| GATE-04 | 目标→阶段→CASE映射 | plan-pass；任务书目标表＋矩阵42模板 |
| GATE-05 | 目标验收与证据合同 | plan-pass；旧8行/10按钮/52展开与父分支保留 |
| GATE-06 | 七阶段步骤与产物 | plan-pass；任务书合并阶段长程任务，不另建竞争计划 |
| GATE-07 | 每阶段完成门/失败处理 | plan-pass；P1前提未闭阻断危险动作与后续签收 |
| GATE-08 | 每阶段专属＋通用开工清单 | plan-pass；任务书各阶段及公共清单 |
| GATE-09 | 测试分层与证据schema | plan-pass；矩阵U/C/I/G/R/Z及截图/原始JSON身份分列 |
| GATE-10 | 限额、清理、归属及恢复 | plan-pass；当前核账值，不增加产品额度 |
| GATE-11 | 高风险MVP前提 | conditional：10输入质量/构建/v7绑定通过，正式预览组合校验fail；具体字段、后继预览及生产marker/Job/原生取消待证。管道合同限定pass不授真实worker回收 |
| GATE-12 | Goal与目标/顺序/资源一致 | plan-pass；v0.29续既有Goal，不创建/标完成，逐阶段读开工清单及CASE |
| GATE-13 | 变更控制、失败/完成/清理模板 | plan-pass；沿既有治理，原稿归档可追溯 |
| GATE-14 | 逐份复盘与执行边界 | 计划结构可审阅；提供按现状续执行的提示词，GATE-11剩余前提阻断对应危险实测及签收；不得宣称所有前提通过 |

## 测试、证据与资源治理

Unit/Contract（单元/契约）验证状态机、精确身份、取消/成功竞争、帧与有界输出；Integration（集成）验证Core→IPC→UI与磁盘；Gray（差分）保旧新完整性拒绝语义；Real（真实）使用正式EXE/子进程/文件故障；Zero-Short（空根入口）只在R5验证最终同包主程序从零链。每阶段具体适用/N/A按矩阵，不为静态文档增加产品测试，也不拿合同替原生通过。

每案保存输入/包/资源SHA、步骤及预期/实际、任务/实例/代次、单调时间、截图/日志Pointer、控制与资料集合/SHA、Job/端口回收。旧失败不覆盖；模块无UI可不截图。原227/52结果不倒写，一个variant通过不自动改父行。`repair_campaign_complete`与`acceptance_complete`独立。

现限额：新增重下载0、F增量≤80GiB、E本run证据≤200MiB；原网络累计200GiB/F峰值300GiB且余100GiB/E新增5GiB且余20GiB继续约束。planning和构建另列增量，历史unknown不无限化。小探针120s，轻UI10min，检查/旧env修复360s，源码修复20min，安装/实例重建/恢复30min，组2h，均含回收。资源不足停新重案，先核归属再清重复输出，不删唯一失败/备份、不跟随链接、不暗中新下载。

## 逐份复盘与风险结论

| 文档 | 本次核对内容 | 判定 |
| --- | --- | --- |
| README / manifest | 当前8产物入口、合并模式及版本 | 结构检查；结果见document-validation.json |
| 唯一总控 | R0/R1事实、R2/R3在途、R4–R6未完成；下一动作唯一 | 与任务书同步，不签产品新门 |
| task-book | T1–T5、R0–R6、开工/完成/失败、legacy独立修复/Job及资源 | 要求完整；实现及真实安全性待证 |
| acceptance | 42 CASE原主表与原27映射不缩减；新增26条历史未闭项逐ID处置、uv资源门、07/08及v4边界参数与当前事实 | 不增加模板，不替旧状态授pass |
| Goal | 必读、阶段、完整目标、原授权、性能/资源和完成边界 | 与现行任务书一致 |
| 本文件 | 来源、MVP、GATE00–14、风险退回和六类验证 | 明确conditional前提，未授豁免 |
| change-control及既有治理模板 | 保存历史、精准Git、资源与失败/完成规则 | 沿原授权，不新增阶段确认流程 |

历史v0.26审阅结论（当前事实及下一动作以上方与末尾为准）：P1为独立env事务/Job恢复、端到端取消及性能未闭，均是待修/待验目标；管道原案已限定通过。规划审查结论`pass-with-boundary`：允许后续按已授权范围核输入、补剩余小合同和候选准备；完整原生/危险实测须各自前提满足后自动推进，未满足不得签收。工具四项修复的46合同已过，接08冻结及原生仍归CASE-R2-12/R6-03；07外部前检失败不能当已执行原生失败，uv三个资源合同已通过，修前fmt02/full03已通过，修后完整质量未验。文档完成不代表产品交付，不新增用户审批门。

本次 v0.29 文档复盘结论为 `pass-with-boundary`：八份专项文档的阶段、42 CASE、Goal、启动时限和最新候选边界已对齐，允许从只读定位下一动作续接；候选业务、危险操作前提和产品完成门仍未通过。文档检查回执位于 `E:/OpenSourceTeamWork/workspace/tools/launcher-reliability-20261102/planning/review-plan-v029-20261103T121203Z/document-validation.json`，保护的59份非本次文件SHA未变。旧 `scripts/validate_plan.py` 整体结果仍为 fail：对照归档的本次修改前输入和当前输入，均为73条问题、无新增；原因包括固定M阶段产物名单未纳入后续报告，以及历史链接问题。原失败输出与前后对照均保留，不把专项文档通过写成整个历史计划校验通过，也不修改旧校验器掩盖问题。

## 下一步动作

先只读拆分 candidate10 预览的组合校验拒绝，逐字段比较历史 plan 自摘要、schema/kind/rebuild、release/engine/profile、固定 recipe/lock、四 write_roots、profile_writes 与 main_env_fallback，定位具体不匹配项并落盘。当前只证实组合校验拒绝，不能预断是摘要、根或锁错误。定位后按原授权最小修复及正反例合同→当前输入质量门→冻结后继候选与显式 supersedes 新批次→正式只读预览；预览真正通过后才续三取消、强杀恢复及 A/B/C，继而完成 R2–R6。禁止删除/隔离保留候选、改历史 plan/journal、伪造 receipt/pending 或直接刷新原失败时钟重跑。
