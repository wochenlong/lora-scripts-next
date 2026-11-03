# 启动器可靠性与性能修复：针对性沙盒验收矩阵

## 当前审阅与执行基线（v0.29）

R0/R1 done，R2/R3 in progress，R4–R6 pending；仅 RP-EXIT-R0/R1 已签，专项与全局验收均 incomplete。candidate10 已构建冻结并完成 v7 绑定；定向 7/0/0、完整 Rust 434/0/15、fmt 与严格 Clippy 通过，仅属于对应冻结输入。真实预览 legacy-v7-preview-only-01 在确认前 fail，错误为“恢复候选计划与固定根/编译锁或原文摘要不符”；具体失败字段尚未定位。confirmed=false、无工具写 invoke、未产生 worker；真实关闭/退出、自然 exit0/Job 排空及独立失败保护比较通过，不能授业务、worker/reader 取消或性能通过。

本层为 v0.29 文档归一化，保留既有执行授权和 Goal，不创建、重置或标记工具 Goal 完成。本轮只整理文档。下方 v0.26 历史快照、旧阶段记录及“08 未构建/10 待构建”等描述仅是原时间点事实，不能作为现行操作指令。07/execution-ledger.json 和 continuation-current.md 尚停在 10 构建中；本次保留原件，最新事实以 candidate10 admission、v7 binding、native-report 与 host-status 为准。

当前唯一下一步：先只读拆分 candidate10 预览的组合校验拒绝，逐字段比较历史 plan 自摘要、schema/kind/rebuild、release/engine/profile、固定 recipe/lock、四 write_roots、profile_writes 与 main_env_fallback，定位具体不匹配项并落盘。当前只证实组合校验拒绝，不能预断是摘要、根或锁错误。定位后按原授权最小修复及正反例合同→当前输入质量门→冻结后继候选与显式 supersedes 新批次→正式只读预览；预览真正通过后才续三取消、强杀恢复及 A/B/C，继而完成 R2–R6。禁止删除/隔离保留候选、改历史 plan/journal、伪造 receipt/pending 或直接刷新原失败时钟重跑。

## 计划元数据

- Plan ID：`desktop-launcher-reliability-20261102`；Version：`0.29`；更新：2026-11-03（Asia/Shanghai；v0.29 文档归一化）。
- 唯一总控：[00_总控目标索引.md](00_总控目标索引.md)；详细阶段：[任务书](reliability-performance-20261102-task-book.md)；前提/门：[开工复盘](reliability-performance-20261102-readiness.md)；[Goal提示词](03_goal提示词/启动器可靠性与性能修复_20261102_goal提示词.md)。
- 分支`feat/desktop-launcher`，HEAD本轮实核`d409b00bac3bcb3e7ef56b424c8946f240e0a38f`；R0/R1 done、R2/R3 in progress、R4–R6 pending，R2–R4门未签。Execution readiness：`executing`；本批同步规划与既有实测证据，不新增产品实测或改变工具Goal。
- 现行42个CASE原主表及旧8失败/10按钮/52单元映射保留。新legacy环境/Job/可见阶段是参数，不增模板，不授父CASE通过；旧module/candidate05/06各自保留身份。
- 最新事实：见本文件开篇、RP-CONTROL-IDENTITY-01参数及唯一总控；10 预览业务 fail、失败保护/退出限定 pass；组合校验的具体失败字段待定位。以下v0.26质量及工具段落为历史身份。

### 历史质量结果与仍须补验的工具参数（v0.26）

历史pipe-reader-cancel-03失败保留；reader04/full02/Clippy02沿原输入。`uv-resource-fmt-02` exit0；`uv-resource-full-rust-03` 实际415通过/0失败/15忽略，两者均在本次错误出口修复之前。`legacy-errors-focused-01` 为7通过/2失败/2忽略，两个新增夹具问题已改但未复跑；四文件错误合同修复后的六合同、整树fmt/完整Rust/严格Clippy均待验证，不能沿用旧通过。 07原生not-run，08未构建；新合同不可代原生。

下面四项工具防误判已由v4实现并通过23 Node＋23 Python合同、9条Node语法检查与Python AST；18份源文件前后SHA不变。验证回执为`<run>/R2/execution-resume-20261103-03/native-tool-preparation-v4/verification-01/verification.json`。仍绑定07，待08接入并重新验证/冻结后做真实入口；四行原生状态继续not-run。沿用CASE-R2-12/R6-03，不增加模板或四引擎重型轮次。

| 参数/CASE | 后续正式步骤与通过条件 | 当前状态/证据要求 |
| --- | --- | --- |
| legacy-pending-blocks-start / CASE-R2-12 | A独立env修复成功但原安装journal仍待续办时，断言`start_available=false`，首页显示待续办主动作或启动禁用；不以尝试启动服务验证保护 | not-run；A终态快照、首页截图、原journal SHA；A通过不替B续办 |
| trusted-click-before-close / CASE-R2-12、CASE-R6-03 | C在关闭WebView前冻结正式切换/启动/停止的点击轨迹并逐项断言`isTrusted`；页面销毁后缺失/空数组不能授pass | not-run；可信事件与点击前后UI/IPC/HTML API语义证据，退出证据分列 |
| resume-prelaunch-protection / CASE-R2-12、CASE-R6-03 | B首次副作用前比host冻结的`prelaunch_state/prelaunch_profiles`及控制身份；启动刷新后的漂移不能被采成新的before | not-run；host→首次快照→续办→退出保护差异；发现漂移fail |
| recovery-record-protection / CASE-R2-12、CASE-R6-03 | A成功及postclose按精确transaction核`original-journal.json`、`protected-controls.json`、`original-tree.json`，分别匹配plan三个预期SHA；原env仅核精确普通目录存在，不新增全树扫描 | not-run；三小记录路径/预期与实际SHA、普通目录/非链接证明；丢失或漂移fail |

## 历史文档交付快照（v0.26-review）

本轮整理问题、优化方案、针对性实测与Goal提示词；文档工作不追加产品修复、构建、沙盒操作、commit或push。既有修复、执行授权、active Goal及阶段进度保留；已在途外部工具的轻合同收口单列，不冒充产品验收。

- **问题范围：** 恢复自阻挡、检查无反馈且不能取消、重装确认窗迟出、维护与启停慢；补原8失败行、AI Toolkit/Anima Fast共10遗漏按钮。T1–T5、R0–R6、42 CASE、52引擎展开及26条历史未闭项不缩减。
- **质量事实：** `uv-resource-fmt-02` exit0；`uv-resource-full-rust-03` 实际415通过/0失败/15忽略，两者均在本次错误出口修复之前。`legacy-errors-focused-01` 为7通过/2失败/2忽略，两个新增夹具问题已改但未复跑；四文件错误合同修复后的六合同、整树fmt/完整Rust/严格Clippy均待验证，不能沿用旧通过。
- **新增P1与方案：** `ControlledProcessReapFailed`在通用终态、deadline/rollback、旧resume watchdog及持久化失败出口曾被改写。四文件已作最小修复，尚待验证；正常落盘保持`Failed/worker_reap_failed`，持久化失败保typed错误并说明未保存、保留旧attached现场，不伪报恢复成功。详任务书RP-REAP-ERROR-01。
- **候选与工具：** candidate07已构建但固定uv EXE的67,598,848 B超过旧32MiB门，产品原生not-run；candidate08未构建。v4原46项工具合同通过仍绑定07；v5的verification-03已通过31项Node＋67项Python纯合同、14条Node语法及16份Python AST/compile检查，工具源码前后SHA一致、v4原件未变；仅证明外部工具。08身份接入、复验冻结与产品原生均未验，不可直接原生。回执为`<run>/R2/execution-resume-20261103-03/native-tool-preparation-v5/verification-03/verification.json`。
- **执行边界：** R0/R1 done，R2/R3 in progress，R4–R6 pending；仅RP-EXIT-R0/R1已签。专项和全局验收均incomplete。不训练、不加载/下载训练模型、不恢复产品下载预算；测试资源上界仅约束本次Agent操作。

本次八文档原稿、保护SHA、文档校验及审阅证据：`E:/OpenSourceTeamWork/workspace/tools/launcher-reliability-20261102/planning/review-plan-v026-20261103T104556Z/`。实际执行台账：`E:/OpenSourceTeamWork/workspace/tools/launcher-reliability-20261102/run-20261102T130200Z/R2/execution-resume-20261103-06/execution-ledger.json`；原审查及修复回执与测试原件分别保留，不覆盖旧失败。既有远端核验回执为同目录`remote-before.json`：2026-11-03T10:34:46Z的远端/本地均为`d409b00bac3bcb3e7ef56b424c8946f240e0a38f`，本次文档交付未新发起网络Git。

### RP-CONTROL-IDENTITY-01：真实预览失败的修复与针对性补验

归属CASE-R2-12、CASE-R3-01/05及CASE-R6-03，42模板与四引擎重型轮次保持。

| 问题/实现要求 | 针对性验证与证据 | 当前结果 |
| --- | --- | --- |
| 产品合法控制记录被误拒 | commands.jsonl/stdout.log/stderr.log、operation snapshot.json数组按精确路径/schema识别，snapshot载荷由清单绑定；不得删日志/隔离原件补绿 | 08真实fail保留；09已通过该采集阶段，非整案通过 |
| 原文Vec数字数组放大 | 新plan版本2完整读取后保存路径/类型/长度/SHA；旧plan版本1保原算法，未知版本拒绝 | 09定向与完整质量通过；47,658,004 B真实控制已采集，最终保护序列化未达 |
| 紧凑投影与旧事务兼容 | 同长度篡改/增删/版本/边界与未知/链接拒绝合同；v1不迁移旧intent，v2摘要绑定新格式 | 09输入定向53/0/0、完整428/0/15、fmt/严格Clippy pass；不外推后继兼容改动 |
| 失败预览与正式退出 | 错误窗真实取消→窗隐藏→精确query终态→设置正式退出；业务、安全、worker/reader证明分列 | 09两真实trusted点击、自然exit0/Job0及独立失败安全pass；业务fail，无worker，不授reader取消验收 |
| 历史恢复候选的保全所有权 | 精确历史plan自摘要/固定锁recipe/四write_roots/prior_state/old-binding/当前已验证state及receipt/恢复代次全闭合；原记录完整字节纳入保护，受原预算/链接/未知/冲突拒绝约束 | 历史候选最小兼容已进入 10 冻结输入质量验证；真实预览仍被组合校验拒绝，具体字段待查，仅保全认领，不授健康/ready |
| 历史候选兼容的定向补验 | 正式中断重建→恢复旧绑定保候选；错缺plan/摘要/锁/recipe/旧绑定/恢复代次/路径/owner/链接仍拒绝；漂移改变保护或拒绝；无payload扫描/状态写入/健康授予，正常receipt/pending规则保持 | 10 定向 7/0/0、完整 434/0/15、fmt/Clippy 与构建通过；v7 真包预览 fail。逐字段诊断及后继正反例/原生待做，归 CASE-R2-12，不增模板/重型轮次 |
| 原案时钟及失败保留 | 原360/1800时钟、配置/报告/journal保持；新实现独立batch明确supersedes，不刷新retry、不复造pending | v6 合同、09 与 10 的独立绑定保留；08/09/10 业务 fail 各自保持，安全 pass 不改变业务结论 |

## 目标、范围与事实基线

先解决正式实例恢复入口自阻挡、引擎检查长时间占住界面、普通重装预览无及时反馈的问题，再在不降低完整性校验的前提下测量并减少重复工作，最后用同一个最终 EXE 在独立新根验证受影响功能。验收使用真实正式入口、真实 receipt、真实子进程、真实文件缺损与恢复，保留可复查截图、任务事件与文件证据；不启动训练、不加载训练模型，不要求用户重新手动验收。

已读取的正式历史证据属于 FINAL06：产品提交 `4e1b4cc78939e8b906252b27dcc20692ad347a08`，EXE SHA256 `11804c053d8667b1c9b91512d72055481aeb27d58be2ac32d181ede42413cbca`。旧 227 行为 193 pass、24 partial、8 fail、1 blocked、1 pending-review；四引擎 52 单元为 3 pass、8 partial、8 fail、22 blocked、1 not-run、10 pending-review。**52 是 13 模板在四引擎上的展开，与 227 不相加。**本计划不会重写这些历史结果。

旧三案首次健康查询约 900 秒失败，触发的是原验收 harness 的 `waitReady(900000ms)` 等待门槛，**不是前端产品超时，也不是 worker 的 1800 秒超时**。现场源码已有 `main.rs::query_engine_control` 的 `spawn_blocking`；待改善的是检查任务的接收、观测、去重、取消及总期限，不能把“加 spawn_blocking”写成新修复。原 worker 的超时从子进程启动后计时，不能据此证明启动前完整 Python 校验、工具缓存锁等待已被覆盖。R0采样尚未完成完整阶段归因，R2/R4继续定位；根因不得由累计I/O推断。

历史普通源码修复 54 分 41.498 秒、重建 85 分 27.836 秒、轻概况启动至 HTML/API200 为 156930ms，仅作历史问题线索；它们的硬件、缓存、fixture、包身份不与未来样本自动等价，禁止据此编造优化倍数。

## 执行阈值与测量合同

以下目标限定为同机、单个重操作、固定 fixture。R0 先验证采集能力与资源条件；目标缺乏事实支撑或不能达到时，记录差距与 CR，交主控审查，**不得自动放宽目标、缩小 fixture 冒充达标或停用完整性校验**。

| 指标 | 执行目标 | 起止点与判定 |
| --- | --- | --- |
| 点击及弹窗首反馈 | ≤300ms | 从输入事件到界面绘出可辨识状态；慢预览必须先出加载/取消反馈，不要求 300ms 内完成完整扫描 |
| 引擎 query 任务接收 | ≤1s | 正式 IPC 发出到返回稳定 task ID/已存在任务身份；不以 Promise 创建作为接收 |
| 活跃阶段进度 | ≤1s 刷新 | 实际工作中的任务快照可见更新；无字节变化也须阶段/心跳；等待锁、网络等待、暂停单列原因、持续时间和可取消性，不能伪造文件进度 |
| 取消接收 | ≤1s | 请求到明确 accepted/already-terminal/权限或身份错误；不能只改变按钮文字 |
| 扫描停止 / Job 回收 | ≤5s / ≤10s | 已接受任务取消到不再扫描/读文件，及该任务所属 worker/Job 全部退出；分别计时 |
| 单引擎完整只读检查 | ≤300s | 请求入口至完整成功终态，含排队、启动前 Python 验证、缓存等待、receipt、环境、源码与额外文件检查 |
| 小源码缺损修复 | ≤15min | 正式确认到验证成功；GUI 与各引擎分别计时，不用下载结束代替修复完成 |
| 保留旧实例重建 | ≤25min | 正式确认到新实例 verified/ready、绑定提交及恢复记录齐备 |
| 服务启动 | ≤60s | 点击启动到指定 HTML 与既有健康/版本 API 均 200 且语义正确、UI 出现打开网页入口 |
| 终态到按钮刷新 | ≤500ms | ready事件到可见打开网页按钮；停止完成到可见启动按钮，分别计时 |

常规快操作取 3 个样本，保存全部值、最大值与中位数；样本少不宣称 p95。重案只做少量固定fixture对照及优化后真实完整操作各1次；四引擎完整检查必须各有真实完成记录，不对每个状态重复大型安装。R0旧路径只做每段≤120秒的有界采样，小fixture可以前后各1次完整差分；大型旧操作未完成时记截尾样本，不计算速度比。完整可比样本需要相同fixture清单、硬件、电源、缓存类别和采集方法；不能保证时按不可比单样本报告。文件缓存采用明确的冷/暖标记，不以清系统缓存或重启用户机器制造所谓公平样本。

每个重案达到目标阈值仍未完成即记录目标未达、收集阶段证据并请求取消；外部保护门分别为检查360秒、源码修复20分钟、安装/实例重建/变更恢复30分钟，均从请求入口起计且包含回收。耗时校验必须在可取消阶段完成；原子提交收尾设计上界为10秒，取消返回`commit-in-progress`而非伪造cancelled。超过收尾或外部门仍无终态，记录fail/needs-recovery，停止新增操作，按经过验证的持久恢复协议处理；尚不能证明安全终止时保留精确现场并记blocked，不无限等待或盲杀未知进程。**不再进行90分钟无进度盲等。**一次失败不靠无修改重复重跑凑绿。

## 实测资源、fixture 与安全前提

当前唯一run ID为`run-20261102T130200Z`，证据根`E:/OpenSourceTeamWork/workspace/tools/launcher-reliability-20261102/run-20261102T130200Z`，沙盒根`F:/NextTrainerLauncherSandbox/reliability-20261102/run-20261102T130200Z`。创建前已核无碰撞、绝对路径及磁盘余量，两根均有`.codex-reliability-owner.json`标记。旧`launcher-full-acceptance-20261101`证据与失败原件保留；R1采用已核身份的自有runtime-final04真实committing现场，正式恢复前先完整备份state/目标backups/profiles/release.json（只读预检3989文件347,552,329B，上界512MiB），不复制venv。其余故障按新构造/身份复核的自有根执行，修改范围逐案限定。

R0 生成 fixture manifest：四引擎健康 receipt/绑定/代次、GUI 健康实例及保留旧实例、真实正式事务中断点、最小源码缺损文件、最小依赖缺损、不可恢复首次安装、真实占用 lease、用户资料哨兵；每项记录原始 SHA、大小、所有权和构造过程。故障注入只在自有沙盒通过明确受控点触发真实事务失败，不通过手改正式 receipt、pending 或临时解除锁来制造通过。不能安全构造的分支记 blocked，保留缺口。

只运行一个GUI和一个重操作；轻量指标采集不得触发额外全树扫描。磁盘预留按安装展开、暂存及回滚保留量计算，再留20%余量，不能仅按EXE大小估算。R0核账后的当前限制为新增重下载0、F增量≤80GiB、E本run证据≤200MiB，且均须落在原计划剩余额度内；原累计网络200GiB/F峰值300GiB且余100GiB/E新增5GiB且余20GiB不增加，历史缺账保持unknown。200MiB统计本节E盘run根；planning修订证据和Cargo/npm构建产物分列增量，仍核原E新增与可用余量。冻结R0原件中的20GiB/1GiB是初始限额，不能据此扩大当前范围，也不回写旧原件。小探针≤120秒、轻UI案≤10分钟、引擎检查外部保护≤360秒、主源码/重建案≤20/30分钟（含回收）、每串行组≤2小时，与任务书一致。安装树不塞入证据包；按独立可见状态保存必要截图，允许多CASE复用原图Pointer；模块/工具合同用真实输出和SHA、screenshots=[]/不适用；长过程保存结构化事件，空间不足先停止新重操作，不能删唯一旧证据。固定SHA缓存不足须记录前置不足，不能暗中新下载；这些记录不恢复产品下载预算。

### 最新修订与原CASE的归属

| 最新待验范围 | 现有CASE | 现状与所需证据 |
| --- | --- | --- |
| 最终取消/提交竞争及Core成功收口 | CASE-R1-06；只读取消兼容归CASE-R2-04 | final-cancel-green-01的7/7、exit0、源稳定、Job受控1→0；只授CAS/原子写/Core收口合同。短收尾/controlled修复已获扫描36/36、binding1/1及完整Rust344/0/15、Clippy/fmt模块证明；真实pending恢复/健康/时延另取当前同包原生证据 |
| 候选＋非目标树合计资源保护 | CASE-R4-05 | 修前3案RED保留；combined-budget-green-01的19/19、exit0、源稳定、Job自然0→0，仅模块通过；fresh非目标metadata余量与实际SHA层分列，保持4GiB/50,000节点，不授性能/原生通过 |
| 回退取消窗口采集工具 | CASE-R1-06及R1-01的证据前提；归档/回收交叉CASE-R6-01/03 | candidate05下native04真实UI committing取消→新进程正式GUI recover→正式IPC重复成功；audit02/completion02签R1业务门；原cancel receipt unknown保留，≤5/≤10秒与完整嵌套取消尚未验 |

不增加42模板。适用条件相同的同包真实session可以多CASE复用，逐条保留断言、身份和Pointer；4完整＋4取消指独立query实例，不把内部安装校验当query/UI通过。原生可见变化才需要截图，模块工具合同不要求界面图。具体复用、存储和核账规则见[任务书](reliability-performance-20261102-task-book.md#实测精简与复用规则)。

### 旧安装续办的针对性实测参数（保留原attempt身份）

这些是现有CASE的参数展开，42模板不增加。candidate06已有确认取消/验证中取消通过及成功续办失败；只给相应参数授结果，父CASE及服务链仍未闭。

| 参数 | 现有CASE | 正式操作与必须断言 | 证据与当前状态 |
| --- | --- | --- | --- |
| legacy-confirm-cancel | CASE-R2-12；R3-05交互共用 | 点“检查并完成安装”→查看目标及说明→取消确认；任务未开始且原journal/state/profiles/receipt集合不变 | candidate06真实GUI取消确认通过；见legacy-resume-cancel-native-01及取消独核；原journal/保护集合保持 |
| legacy-verify-cancel | CASE-R1-06；R2-07/11/12 | 再确认，在真实复验阶段取消；记录接受/扫描停止/Job回收三段计时；无journal提交或其他控制写入，终态唯一 | candidate06基础Python验证中取消pass-with-scope；受理≤37.8126ms、终态≤97.6737ms，原journal不变、退出保护/自然Job/CDP通过；其他扫描/worker时限未证 |
| legacy-complete-reopen | CASE-R2-12；R5-05 | 正式复验成功，仅精确原journal转committed；operation succeeded且cancel_requested=false，其他控制/资料/全部installed receipt不变；关闭后复核，重开候选消失且current dev不变 | legacy-resume-success-native-01：确认至失败45925.9555ms，最后为依赖导入exit1，业务fail；原journal/state/profiles/receipt独核保持；成功提交/重开not-run；后续同参数诊断已证实缺pip及依赖未装，须独立修复，不重复诊断 |
| legacy-service | CASE-R2-12；R4-04；R5-07 | 上一项成功后正式启动，HTML/版本或健康API语义正确，网页按钮可见；停止后按钮、监听及自有进程回收 | HTTP/API响应、单调钟、按钮截图、端口/Job；not-run；之后才补Anima运行态取消 |
| legacy-refusals | CASE-R1-02/05/06 | 错root/版本/journal SHA、真实lease/其他pending、环境验证失败或晚到取消不能误提交；Core公开入口小夹具证明，原生成功不能替拒绝分支授pass | 原入口/错误/控制差异及源码身份；已有模块合同，新增原生范围按前四行 |

模块360秒watchdog不含全部租约/catalog等前置；本原生案从正式点击计360秒外部门并预留回收，不因此把未知同步OS I/O标为即时可取消。不写journal/receipt制造通过，不直接invoke跳过正式用户入口；不得改用户原根。原Anima取消`query-anima-fast-cancel-ready-01/02`及对应旧检查attempt失败原件（不指成功的pipe-fix-full-rust-02）保留。

### 最新失败补测参数（不新增CASE）

| 参数/归属 | 实测要求 | 当前结论及证据 |
| --- | --- | --- |
| probe-error-detail / CASE-R2-07/11/12 | 同解释器/参数受控诊断；真实非零退出时保留有界stderr原因，超大输出有截断标记，排空未证时worker_reap_failed最高优先；完成reader/Job回收后再区分用户取消与期限失败；原journal和保护集合不变。修复后新成功attempt完成正式续办及服务链 | 业务fail保留：同参数诊断已证实缺pip/依赖未装；Logger/有界尾部定向修复通过，真实GUI错误可见性尚未证；见environment-probe-log-readonly-review.md及失败保护独核。模块合同与真实GUI错误可见性分列 |
| visible-stage / CASE-R2-05/07、R4-05 | 真实两个阶段→日志页/返回页，任务事件到可见阶段≤1s，轻操作3样本；旧task/代次不得覆盖 | not-proven：取消事件已verifying但原截图仍“准备中”；取消功能通过不代表阶段显示及时 |
| main-preview-two-package / CASE-R3-01/02/05 | 仅修正工具类型识别与精确保全证明，核真实双lease后新attempt；实际两包故障→准备窗/取消/Escape/重开/归焦→精确恢复与退出保护 | r301 attempt fail：helper在备份/删除前误拒旧Intent，无fault receipt；产品预览/交互未测到，不能给产品pass/fail。后继工具不得统一放行无status/running或改历史原件 |

### 旧环境独立修复与Job恢复的针对性参数（v0.20引入，v0.21核对）

当前旧main依赖缺失已实证。设计附件`<run>/R3/legacy-environment-repair-design-20261103.md`已有产品增量，reader04及full02/Clippy02仅原输入通过，uv三个资源合同已通过，修前fmt02/full03已通过，修后完整质量未验；v4合同已过但原生闭环未验；普通legacy install会覆盖原journal，禁止用于补绿。下列参数展开既有CASE，42模板及四引擎4完整＋4取消保持。

| 参数 | 现有CASE | 正式操作/必须断言 | 当前结果 |
| --- | --- | --- | --- |
| legacy-offline-resource | R2-07/11/12；R5-05 | 固定release/ZIP requirements与81资源、Python/uv/锁/展开上界；缺资产/错SHA/计划漂移/外来配置及双lease冲突写前拒绝；原env/journal和保护控制逐字不变 | requirements外部锚及外部前检02只读通过；RP-LEGACY-UV-01三个新合同3/3通过，fmt02/full03修前通过，修后六合同/完整质量待验；正式预览与原生not-run |
| legacy-offline-build | R2-12；R5-05/07 | 正式准备窗→计划→独立修复；最终路径备份/无seed离线构建→可信静态校验→pip check/精确版本/import；registry/current dev、journal原SHA、源/receipt/资料不变；后续原SHA resume独立提交 | not-run；任务受理/阶段/取消采用既有任务系统，不能同步长锁UI |
| legacy-three-cancel | R1-06；R2-07/11/12 | venv创建、依赖sync、import三个真实阶段分别显式取消；记录受理/扫描停止/Job active0三段；排空后才能恢复原env，原journal不变，终态唯一；无关进程继续活 | not-run；不能拿candidate06基础Python取消代验 |
| legacy-kill-recover | R1-02/05/06；R2-11/12；R6-03 | 构建中强杀本事务宿主，命名Job或等强持久归属证明后代排空，再新进程正式显式恢复、清单/marker/两端无碰撞、幂等；失败worker_reap_failed→needs_attention且不移动原件 | not-run；双lease可重取/PID不存在不够；无法证明只授安全拒绝，强杀正向仍未通过 |
| legacy-preserve-collision | R1-02/05/06；R4-05 | 小fixture覆盖每个rename前后、坏marker/未知目录/保护漂移/恢复目标碰撞；仅精确自事务例外，其他pending均挡；未知不删除、不覆盖 | full02原输入八个rename窗口及幂等合同通过；生产拼装、真实碰撞与离线环境未验 |
| legacy-resume-service-return | R2-12；R4-04；R5-05/07 | 修复成功不提交journal；原SHA既有resume成功→退出保护独核→重开→选main→系统浏览器HTML/API语义200→停止→切回dev；绑定/receipt/原资料保持 | not-run；完成后再补Anima运行态取消01/02后继attempt |
| worker-reap-failure | R2-07/11；R1-06；R6-03 | 正常exit和取消的helper留下后代时，executor返回时，预先持有的Child/后代进程handle均已SIGNALED，Job的ActiveProcesses=0（不要求Job handle自身SIGNALED）；受控失败契约稳定码优先于Cancelled及普通超时，六出口及未保存边界按任务书RP-REAP-ERROR-01逐项验证；所有旧自动/重开后显式恢复分支均受持久失败屏障保护；管道阻塞reader与阻塞logger分列参数，不能只凭Job0判成功 | GUI屏障14/14等合同保留原身份；blocked-sync-reader原03失败、后继04及full02同名合同通过；错误出口四文件已改但六合同未复跑；持久化失败须保typed、旧记录原文与明确未保存，其余缺口not-run，不能由管道单案授整链通过；故障注入不声称发生真实OS回收故障 |
| job-lifecycle / persistent-barrier | R1-02/05/06；R2-11；R6-03 | 每命令独立Job，launching→attached-before-resume→reaped均持久，session精确匹配；有额外持柄时强杀后新进程Open成功并排空，无额外持柄且可信attached时精确notfound可按生命周期证明销毁；launching未attached即使notfound仍拒绝。模拟回收失败后重开，正式recover/旧resume保持needs_attention，排空证据齐全后才受控恢复 | full02原输入三个命名Job生命周期合同已通过；持久屏障/会话/宿主代次合同各留身份。生产拼装与真实强杀恢复not-run，不外推全部通过 |
| legacy-stage-attribution | R1-06；R2-07/11/12 | venv/sync/import以attached worker的PID/FILETIME、Job/session和实际命令行核阶段；不只认phase/log。错过记tool_coverage=unsupported，业务CASE保持blocked或not-run，不能用其他阶段或cancelled终态补绿 | not-run；v5纯工具98项合同及语法检查通过；08接入/冻结未验，不可原生 |
| legacy-drop-job-before-kill | R1-06；R2-11/12；R6-03 | 强杀前释放工具外部产品Job查询句柄，只保提前获取的精确host/worker进程句柄；≤10秒两者SIGNALED；工具不得TerminateJob。fallback分列fail；额外持柄仅小合同 | not-run；不能由有持柄小合同授真实无持柄强杀通过 |
| legacy-first-recovery-ui-idempotency | R1-02/05/06；R2-12；R6-03 | 新宿主首次恢复经真实按钮/确认窗；成功后才对同一事务重复正式recover_legacy_environment IPC，补充幂等且write_invoke_used_by_harness=true；前后保护不变 | not-run；首入口不允许直调IPC代验，不能沿v4全局false |

附加边界仍展开上述worker-reap-failure及job-lifecycle参数，不增加CASE：Job active0不等于宿主reader/logger退出。构造受控阻塞reader，核有界返回及requires_new_host持久宿主PID/创建时间；同一活宿主拒恢复，新宿主先证明旧代退出再证明Job排空。跨session、原Intent SHA不匹配、缺侧录的旧匿名dirty及其他事务继续拒绝且零恢复写；命名Job回收不能代替宿主退出证明。既有部分合同已有结果；管道04限定通过不覆盖其他取消执行器，未覆盖的合同及原生分支保持not-run。

每个新参数均保存task/operation/transaction/plan SHA、原journal和保护集合前后原文SHA、EXE/资源身份、阶段时间、截图及Job/监听回收；旧失败不覆盖。独立env修复/取消/强杀恢复各案外部门360s含回收，小合同/最小helper单段120s；不得拆段绕单案外门。原生测试仅在可信资源/状态机/Job最小前提通过后实施，先保唯一失败原件及可恢复备份。

### RP-LEGACY-UV-01：正式资源门与候选接入参数

| 参数/CASE | 实际输入与针对性断言 | 当前状态与后续证据 |
| --- | --- | --- |
| trusted-uv-identity / R2-07/12 | 真实固定uv EXE为67,598,848 B，ZIP为23,236,992 B；精确长度与内置SHA均核对。坏SHA、短/长或读取中增长、取消/期限继续拒绝，其他32MiB/总树限制保持 | 07前检01拒绝；uv定向三个合同已编译通过；fmt02/full03修前通过；修后六合同/完整质量未验。新增固定资源合同与已有增长/取消参数按影响补，不把32MiB错误扩散为全局放宽 |
| missing-archive-zero-write / R2-12 | 正式resources函数缺归档，在intent、env搬移、解释器启动前拒绝；私有树/原journal/资料前后集合SHA不变 | 新增合同已在uv-resource-focused-01通过；原始输出、fixture/源码SHA与完整前后差异 |
| equal-length-bad-sha / R2-12 | 保持归档长度但更改内容，正式resources拒绝；不能只按存在/大小放行，所有私有树零写 | 新增合同已在uv-resource-focused-01通过；与缺归档分别留断言 |
| production-resource-preview / R2-12 | 08正式只读计划核81资源、Python/uv/锁、安装生成上界及备份/暂存，绝不写intent或移动env；前检02外部结果仅作输入依据 | product_plan=not-run；前检02为6.185s、81 wheel、压缩378,332,343 B、ZIP展开799,556,886 B/12,974条目及Python4,184文件，不授正式计划pass |
| candidate-tool-binding / R2-12、R6-03 | uv资源合同及错误出口六合同/修后质量→08构建/冻结→v5全部候选身份接入及专用取消/kill工具核验→复验/冻结→正式计划→三取消/强杀恢复→A成功/B提交/C服务；08 EXE/实际worker/资源身份全链一致 | 07构建pass、原生not-run；08未构建；v4原46合同pass但绑定07，不可运行。每次变更新attempt，禁止混包或伪造08回执 |
| native-cancel-kill-tools / R1-06、R2-07/11/12 | 历史v4 A仅支持success；核验/补齐已有v5的venv/sync/import三个取消与强杀/新宿主恢复工具，接08后复验冻结。在原journal仍pending时依次执行这些故障案，每案Job/reader排空、原env/journal恢复、保护核对且无未清needs_attention才继续；全部通过才A成功/B提交/C服务。B后不得手改pending复现；截图及身份齐全 | v5纯工具合同98项通过，08接入与原生覆盖not-run；A/B/C成功不能授这些分支通过；仍沿既有legacy-three-cancel/legacy-kill-recover参数 |

上述参数不增加42模板。新小合同≤120s、正式旧env案外门360s含回收；新增重下载0。原失败与07/v4原身份保留。

### RP-PIPE-01：管道取消修复与端到端回收参数

| 项目 | 固定要求 |
| --- | --- |
| 归属 | CASE-R2-11 / blocked-sync-reader，关联R2-07、R1-06、R6-03；不新增模板，不扩大四引擎重案 |
| 已观察失败 | `R2/rust-integration-01/pipe-reader-cancel-03/console.txt`：取消后1008.0771ms，stop已置位、writer仍存活、`unjoined=true`；0/1，exit101，结果fail |
| 最小输入 | 真实Windows ChildStdout管道；本机Rust1.94实际走重叠I/O（ReadFileEx）。writer持有输出句柄且不发stop；记录reader进入read及取消API真实返回值/错误，不得先杀writer使reader被动EOF |
| 后继结果 | fix04为1/1、exit0，reader在10.6999ms实际join、Windows995、unjoined=false且writer仍活；该毫秒值只属于04冻结输入。最新full02同名测试通过，04和full02各保留源码SHA |
| 修复后判定 | 精确原测试reader返回小于2秒，实际join且`unjoined=false`，writer在reader返回时仍活；已join的可解释读取取消错误单列，未知错误失败；随后stop/helper退出及无关进程存活另证 |
| 已核诊断与方案 | 仅CancelSynchronousIo无法取消当前重叠读取；修复为每pipe保留OwnedHandle副本、重复CancelIoEx并兼容原同步取消，在原期限内真实join。复制失败须排空Child/Job；后续按影响核竞争/logger等未覆盖参数，不重做已证实定位，不放宽时限或detach |
| 整链回归 | 受影响的正常尾部/非零错误/连续输出/阻塞logger/共用deadline合同；新包至少一次正式取消→两reader退出→Child wait→Job active0→GUI终态，产品回收目标≤10s |
| 恢复保护 | 未join保持worker_reap_failed/needs_attention，禁止同宿主恢复目录；新宿主先证旧代退出，再证Job排空；强制宿主Job清理仅为测试收尾，不算产品pass |
| 资源及证据 | 新attempt目录`<run>/R2/pipe-reader-fix-<attempt>/`，单段≤120s，无下载/训练；原失败只读，保存源码SHA、取消API结果、单调钟与回收；无UI合同可无截图，正式GUI必须截图 |
| 当前门 | 管道合同限定pass；真实IPC、其他执行器、Job/事务前提及RP-EXIT-R2仍未闭。前提有证才继续相关环境变更实测，不由合同通过直接签整门 |

## 分阶段稳定用例矩阵

测试类型缩写：U=Unit（单元）、C=Contract（契约）、I=Integration（集成）、G=Gray（新旧对照）、R=Real（真实资源）、Z=Zero-Short（新根用户入口）。每行证据按原包/模块/原生身份分列；R0仅基线，R1业务恢复门已签且时延维度仍未验；R2 Anima停服full单配置通过，取消/其他引擎未验；R3原生未闭，R4性能/嵌套取消未验，R5/R6 not-run。

### R0 基线与测量

完成门：身份、旧映射、fixture、安全范围和计时/读字节采集已复核；不足的基线被明确标记，不伪造 before；重测许可来自主控任务书已批准的范围。

| CASE | 类型 | 操作与必须断言 | 主要证据 | 状态 |
| --- | --- | --- | --- | --- |
| CASE-R0-01 | C/I | 只读冻结旧报告、旧 8 失败行、52 单元、EXE/代码身份与新分支脏状态；校验旧输入 SHA 并建立旧→新映射，不更新旧结论 | identity、legacy-index、Git 快照、SHA 清单 | pass（仅基线） |
| CASE-R0-02 | I/R | 核查自有沙盒边界、磁盘、端口、已有用户进程；生成健康/缺损/事务/lease/资料 fixture manifest；只允许白名单目标 | preflight、fixture manifest、资料哨兵 | pass（仅基线） |
| CASE-R0-03 | U/C/I | 验证单调时钟、事件序号、PID/Job及读字节差值；同时完成RP-PROBE-02/03/04/06：前置及管道取消、帧协议、共享订阅与安装控制零修改；不可分离读数记unknown | 采集校准、4探针各自结果和收尾证据 | pass（仅基线） |
| CASE-R0-04 | U/C/I/G/R | 完成RP-PROBE-01/05的Core自阻挡及保护判定小夹具；旧重路径每段≤120秒有界采样，小fixture同输入前后各1次，快反馈3样本；未完成记截尾并安全回收，不盲跑旧54/85分钟重案 | 两探针结果、before阶段序列、失败及回收 | pass（仅基线） |

### R1 恢复自阻挡

完成门：正式 Core 与 GUI 调用链通过正反例；只豁免属于当前合法恢复的事务，不放宽其他事务或真实 lease。恢复失败留现场与准确错误；资料及其他实例不变。

| CASE | 类型 | 操作与必须断言 | 主要证据 | 状态 |
| --- | --- | --- | --- | --- |
| CASE-R1-01 | U/C/I/R | 从正式重建提交故障形成合法pending，经GUI→IPC→`Core::gui_lifecycle_operation`的recover_rebuild正式入口恢复；覆盖可构造的recover_rollback合法事务。不得只测内部helper；任务持久化、事务身份、receipt、绑定终态均正确，重复恢复幂等。已完成回退且当前registry为new状态才可幂等成功；仍为old状态必须拒绝，不能误报rolled_back | 正式入口调用、operation快照、pending前后、成功图 | pass；旧真实主重建恢复原包证据及当前full344终态new重复/old拒绝、candidate05 native04真实committing UI取消→新进程GUI恢复→正式IPC重复成功；audit02/completion02签RP-EXIT-R1，旧02/03 fail及recover03禁止保留 |
| CASE-R1-02 | U/C/I | 提交错误root/marker/transaction ID/release ID/pending kind或损坏备份摘要；有合法目标事务时逐项移走registry、正式profile和必要目录，均在写入前拒绝且不自动初始化；原树零修改，合法事务仍可后续恢复 | 参数/错误码、SHA差异、事务快照 | pass（正式Core身份/结构/损坏参数及零写入已逐项核对） |
| CASE-R1-03 | U/C/I/R | 同版本另一独立未完成事务存在时，不因“同 release”统统放行；验证身份精确匹配，非目标事务保持 | 两事务 manifest、拒绝原因、零写证据 | pass（正式Core＋真实Windows事务文件；stage-evidence-audit-01） |
| CASE-R1-04 | U/C/I/R | 另一版本真实pending与目标恢复同时存在仍拒绝，未知/损坏事务失败关闭；非目标已完成事务的历史授权或old/new备份损坏仍拒绝，合法后续registry切换不被历史终态误挡。只允许经过校验的目标自身pending例外，不按release跳过全根guard | 冲突矩阵、真实pending、正式Core入口结果与精确参数 | pass-with-boundary；当前full344正式Core异release pending/unknown/terminal冲突及历史授权语义合同通过；不声称全GUI历史组合矩阵实测 |
| CASE-R1-05 | C/I/R | 由独立自有进程持有真实 workspace/目标 lease 后尝试恢复，拒绝且不持久化非法任务；释放 lease 后同入口可成功；禁止只伪造 busy 布尔值 | lease owner、PID、持有/释放时间、前后结果 | pass（真实独立进程持锁、拒绝及释放后成功；stage-evidence-audit-01） |
| CASE-R1-06 | U/C/I/R | 在已批准恢复故障点中断并重开，验证任务/事务可识别、取消或失败无资料丢失。覆盖creating/building/validating、prepare_commit扫描/sidecar后且committing持久化前、finish复验后且registry原子写前，通过真实OperationManager.cancel触发；接受取消后不继续切换绑定/报成功，任务cancelled，pending合法且可后续恢复。registry原子写之后不能倒改cancelled；保留旧实例恢复入口。扫描返回后checkpoint不证明分块取消时延，时延另由R2/R4验收 | 两checkpoint、取消回执/磁盘任务、pending及绑定前后、后续恢复、重开图 | pass-with-boundary；当前full344正式Core各阶段/检查点取消、最终CAS/原子写及收口合同通过；native04真实UI命中committing取消后新进程恢复成功，pending/registry/资料保护通过；原cancel receipt unknown与实际window边界保留，分块取消/门后时限仍归R2/R4 |

R1已验代码证据：旧61 passed/2 ignored与真实主恢复保留原身份。terminal-rollback-01编译101、native-rollback-01 locator失败、02夹具缺保护SHA被guard正确拒绝、03长路径原子替换os error 3全部保留。code-tests-04“仅格式通过”及SHA `17b4b46d…`是历史快照；当前terminal-rollback-04已单合同1/1证明Core终态控制夹具registry=new两次幂等、registry=old拒绝零写与资料/非目标保护，明确healthy_environment_claimed=false、committing_recovery_claimed=false。新r1-core-regression-05为12pass/1专属真实lease helper ignored（父案已调用并通过），Job自然0→0；不据这些授健康/原生提交恢复，也不无修改重跑。finish最终取消窗口/Core完成边界已有7/7模块合同，且门后全扫已前移并接controlled token、受影响模块/完整Rust已通过；正式真实committing恢复由candidate05的native-rollback-04真实取消及native-rollback-recovery-04新进程GUI恢复、正式IPC重复恢复证明。candidate04原生02失败保留，不能作为恢复成功证据；原61份profiles＋2份非目标state证据保留。

R1原生验收前置：host已扣除预检/CDP实际耗时并注入`suite_budget_ms`，Node不超过1600秒及剩余预算，确认恢复前保留60秒主动取消/退出；41项及45项两组合同与工具身份已由`harness-review-01.json`核验。无独立全局watchdog，同步OS I/O硬阻塞仍是边界；工具合同通过不替代真实恢复和回收。主重建恢复会话及candidate05回退取消、恢复会话均已结束并回收；历史入口定位失败保持原结果，续接不重开已结束attempt。

### R2 可取消引擎检查任务

完成门：query 返回任务身份；同目标单飞，订阅与任务取消分离；切页可继续观察，旧代次结果不污染现状态；总期限覆盖 worker 启动前后；取消、断连与异常都有真实终态及资源回收证据。

当前R2/R3接入已落未提交工作树；既有Rust10＋13＋33/Python30＋13保留。前端33/33＝原27＋4项取消失败store＋2项实际Activity SFC合同，真实Vue/受控IPC/时钟/内存renderer；非原生。`R3/cancel-retry-01/after-01`源稳定、exit0及Job自然排空；`build-02` npm/vue-tsc/vite exit0、26源/配置稳定、9产物SHA、Job自然排空。外层Python在结果保存/回收后打印U+2713到GBK终端失败exit1，`evidence-verification-01.json`独立核验通过；未为打印错误重构建。 生产IPC/原生/大引擎/时限仍待验，不以模块pass使含R的CASE整行通过。

| CASE | 类型 | 操作与必须断言 | 主要证据 | 状态 |
| --- | --- | --- | --- | --- |
| CASE-R2-01 | U/C/I/R | 正式 query 返回稳定 task ID，≤1s 接受；快照含目标身份/阶段/开始时间；成功、取消、超时、失败互斥终态，不能 ready 快照冒充已完整检查 | IPC 请求响应、schema、任务事件、加载图 | partial；Anima停服full单配置真实UI受理上界17.1ms/稳定ID/完整目标快照/成功终态已验；取消/超时/失败互斥及其他配置待验 |
| CASE-R2-02 | U/C/I/R | 同 root/release/engine/instance/generation 两次并发检查加入同一工作，记录两个订阅身份；worker/全树扫描只有一份。小合同覆盖4个不同身份在途时重复请求仍可经独立resolver解析并加入、新唯一目标busy、解析失败句柄可失败收口、活动task/alias不被历史淘汰、容量用尽有界拒绝。容量初值见任务书，不新增重型实测轮次 | task/订阅及alias、容量/错误合同、PID、扫描计数、并发时间线 | not-run |
| CASE-R2-03 | U/C/I/R | 两个订阅者中一个退订或页面销毁，另一订阅仍获得进度与正确终态；取消按钮必须明确是退订还是取消共享任务，不能暗中停止别人任务 | 订阅事件、另一视图截图、worker 存续 | not-run |
| CASE-R2-04 | U/C/I/R | 有归属权限的显式取消共享任务；仍可取消且实际停止后，所有订阅收到同一cancelled终态。取消与成功竞争时以权威终态线性化，已成功返回already-terminal；重复取消幂等，错ID不影响他案。只读检查没有安装提交段，不制造commit-in-progress长段；修改操作的原子边界由R1-06独立验证 | 正反/竞争响应、任务终态、回收计时 | not-run |
| CASE-R2-05 | I/R | 检查中切引擎、切日志/设置页、回到原页；任务继续可观测、无重启扫描，返回页恢复状态；窗口退订与退出策略按实现合同验证 | 页面连拍、事件序列、扫描启动次数 | not-run |
| CASE-R2-06 | U/C/I/R | 在安全受控边界改变 instance/generation/绑定，再让旧任务完成；旧结果标陈旧，不覆盖新代次、不产生旧计划确认；不同目标不错误单飞 | 代次前后、旧任务终态、UI/计划身份 | not-run |
| CASE-R2-07 | C/I/R | 在基础Python完整核验、原守卫枚举及控制记录读取中分别取消；≤1s接受、≤5s停止，无worker继续启动、完整guard保持。32MiB边界/metadata后增长/增长中取消或期限按下方参数，Catalog验签段补测 | 屏障/计数、原错误、控制状态SHA与进程审计 | partial；读取层合同pass，candidate06旧安装基础Python取消参数真实通过；query及其他阶段/整链时延未证 |
| CASE-R2-08 | C/I/R | 独立自有进程持有真实工具缓存 lease，让 query 进入等待后取消/期限到；等待原因可见、可取消，不使用无关 token 无限等 | lease 证据、等待/取消事件、零新 worker | not-run |
| CASE-R2-09 | U/C/I/R | 在完整树遍历以及大文件分块 SHA 两个位置取消；分块循环响应，≤5s停止扫描，所属 Job≤10s回收；只读树保持不变 | 两参数实例、块/文件计数、读差值、Job证据 | not-run |
| CASE-R2-10 | U/C/I/R | 总期限在启动前/worker运行两路径到达；准确标timeout，不能伪装cancelled或integrity failure；排队/加入共享任务/重订阅不刷新绝对期限。准备/输入/输出/回收都在同一期限；保留最后扫描计数与原因 | deadline事件、两终态、各阶段用时/剩余量、回收结果 | not-run |
| CASE-R2-11 | C/I/R | 断开本案IPC/事件、关窗或worker异常，坏帧/超大输出/stdin不消费/未关输出管道均有终态与有界缓冲。分别记录产品worker和测试宿主的Child wait、stdin关闭、两reader join、Job前后active、是否强制终止及关闭句柄补清理；实际编译由新宿主承载，保留compile-02回收失败 | 各异常身份、错误图、逐项资源证明；宿主/产品分列 | partial；旧微型桥/宿主及compile-03受控清理原身份保留；Anima停服full正常分支已有原件；blocked-sync-reader原03失败保留，后继04及当前full02同名合同通过。full02宿主需强制回收，不能授产品自然退出；其他异常/断连/整链取消时限未闭，R2门未签 |
| CASE-R2-12 | C/I/R | 网页服务运行时做只读检查；另一目标允许的独立维护进行时仍可查询。跨目标并发按设计限流，等待有原因，真正冲突修改仍拒绝 | HTML/API、目标冲突域、任务和UI状态 | not-run |

旧Rust前置证据：r4-scan-01的8/8及r1-core-regression-05的12pass/1专属lease helper ignored保留原身份；前者Job受控1→0、后者自然0→0。最新final-cancel-green-01的7/7、exit0、源稳定、Job受控1→0已验证真实OperationManager取消/提交竞争、原子写与Core成功收口；不授全部门后工作≤10秒或原生恢复通过。

最新合计资源合同：combined-budget-green-01的19/19、exit0、源稳定、Job自然0→0；boundary本次非目标实际SHA树统计＋候选metadata预检；正式SHA/preservation用fresh非目标metadata统计＋候选实际读取余量；validate前后observe各用本次非目标实际SHA统计，不跨probe，原4GiB/50,000节点不变。修前3案RED保留；只授模块保护，性能/整链待验。

历史v0.18取消/成功续办attempt保留原candidate06身份：取消受理上界37.8126ms、终态上界97.6737ms；成功续办从确认到失败45925.9555ms，原journal、profiles及receipt保持。后续诊断已查明缺pip/依赖未装；full02原输入为412/0/15、strict Clippy02 exit0，原生错误/阶段显示与成功续办仍未证。R1业务门与原包签收保持，≤5s/≤10s时限留R2/R4，不将旧unknown或旧full03当当前结论。

#### R2/R3 针对性参数及历史v0.16证据身份

同版v0.16增量证据：本run `R2/harness-service-03/tool-delivery-03.json`（11 Node/3 Python及语法pass）；`R2/query-anima-fast-cancel-ready-02/native-report.json#/service_preparation/installation_snapshot`，原始snapshot `0002-installation-snapshot-after-root-refresh.json`、`0003-owned-service-pre-start-diagnostic.json`、`0004-owned-service-pre-start-diagnostic.png`。正式precondition_failed保持fail；无服务/无query，控制/profile全等，宿主正常产品exit0/自然Job0/CDP回收不授业务通过。旧源审计`R2/harness-service-03/legacy-journal-readonly-audit-03.json`引用`launcher-full-acceptance-20261101/versions-01/native-report.json`；原分支pass不再继承为全安装成功，旧原件不改。

R4嵌套取消与阶段计量追加参数：R4嵌套取消第一批已实现并获实际Cargo 355pass/0fail/15ignored：gui_registration_integrity的Python controlled verify、gui_entry_probe两次source controlled verify及64KiB静态读取、runtime_view仅probe副本受控复制、scan_observation显式Option token控制读取、instances私有load_with_cancel在两处纯读取链路接入。Query取消/期限优先，32MiB缓冲硬限及增长块追加前拒绝保持；控制读取最多额外一个64KiB块，静态读取最多额外1字节，勿混称。普通load/save和必须完成的保全不继承旧Operation token；JSON解析/validate暂存结果后检查停止原因，不能中断内部计算。该增量已进入candidate06但未commit，尚无本批原生时延证据；engine_namespaces控制读取/摘要、其他控制记录/Registry读取及instances内存树语义取消仍待后批，清理阶段不中断。计量分plan、before-observe、可信闭包、validator、复制、副本校验、entry probe、after-observe、最终门。暂不删除execute→finish第二validator/probe，before/after完整扫描保留；并入现有CASE-R1-06/R2-07/R2-09/R4-05参数，不新增CASE或重型轮次。这组全链指标继续阻断R4/R5和最终交付。 R1-06业务已验与时延not-run分列，阈值不降；R2 Anima停服full一配置6 checks通过，不授取消/其他引擎。

R2多根宿主29/29、query工具四合同与语法通过；R3 main-preview工具16/16合同/两语法通过。R2当前另有Anima停服full一配置真实通过，证据在本run query-anima-fast-full-01/native-report.json；R3 main-preview真实GUI未跑。工具自测不授业务通过，Anima该配置不覆盖共享/取消/其他引擎。

以下并入既有CASE，保留42模板与既定重型轮次；共享/硬限已有合同不再列待修，当前组件统一构建已通过；Activity SFC仅覆盖pending取消/重试，App/EnginePanel与原生整链仍待实测。

| 关联CASE | 必测参数与预期 | 证据/当前状态 |
| --- | --- | --- |
| R2-02/03/04、R3-02 | shared初始false；本地受理前/后复用、canonical alias及subscriber_count 1→2→1累计共享提示；不同目标不串。两个生产IPC订阅只启动一个worker，切页/退订继续、显式取消共享终态一致 | 原20合同已覆盖共享提示；当前33项保留原27项store合同。准备窗/日志双视图原生截图及生产身份not-run |
| R2-02/04/06、R3-02/05 | 主程序和引擎准备窗各测：begin IPC未返回taskId时关闭/按Esc并立即重开；已受理但cancel IPC在途重开；existing plan_install/plan_repair；重装不先绕去full inspection。取消中提示等待，不发第二查询、不提供可确认旧计划；cancel_requested/cancelling任一生效，invalidated仍守卫。真正终态/回收后重开才得新task | 原27项store及当前统一build-02已pass；新增4项store取消失败合同＋2项实际Activity SFC合同pass；App/EnginePanel原生仍not-run。留任务/目标/worker次数、时间线和前后截图 |
| R2-05/06、R3-02/04/05 | 普通切页保持共享；store按完整target隔离，组件对同root/release/engine取消收尾期间所有准备暂拒绝（含不同action/scope），防重装绕inspection；不同root/release/engine不误阻。旧取消错误/晚到成功不能覆盖新epoch、重新开窗或授权提交。Admission拒绝后关错误窗不误取消另一个视图任务 | store部分合同及当前统一构建pass；实际Activity SFC仅覆盖pending取消/失败重试，App/EnginePanel生产IPC/原生、鼠标/Esc/Tab/ShiftTab及归焦not-run |
| R2-04、R3-02/03 | 取消请求未送达且后台仍running，与后台已收到但响应丢失分别覆盖；轮询前后都保留取消意图、不可复用旧计划，原按钮可显式重试且在途去重；权威cancel_requested/终态清旧错误，后台先成功仍按成功。Activity受理前可取消并显示等待，不另增按钮 | 新增4项store＋2项实际Activity SFC合同pass（与原27共33）；原生传输故障注入尚未执行，不用受控IPC授原生pass |
| R2-07/11 | 恰32MiB读取接受、+1在扩Vec前拒绝；无observer同样受限；真实File在metadata后经确定性屏障增长至超限，保留最后实际读量，不靠sleep竞争。限制读取缓冲，不声称限制进程RSS | scan-01新增5项内通过，10/10总计；真实全链not-run，JSON语义另判 |
| R2-07/10/11 | 上述增长中触发同observer取消/期限，原cancelled/timed_out优先，不被完整性/JSON错误吞掉；Catalog历史验签虽有4MiB/64 receipts上界，须测量并按需补同token检查点 | 增长取消/期限读层合同pass；Catalog段/端到端时延未验；同步OS I/O硬阻塞边界保留 |
| R0-03、R2-11、R6-03 | Cargo exit0与Job回收分别判定；新宿主持有Job时显式回收并验证active_after0。利用合法源码修改的必要编译验证，禁止清target强造；若调用终止记受控清理，不记自然排空 | compile-02旧回收失败保留；compile-03编译exit0、Job active1→0且termination_requested=true，受控清理通过，不能称自然排空；生产产品链仍待验 |

已有原件：`R2/python-tests-01/query-01`30/30、`legacy-02`13/13；`R2/rust-integration-01/{scan-01,bridge-01,tasks-01}`分别10/13/33通过，7桥进程案已显式include-ignored，微型worker回收不代替生产链。`R2/frontend-tests-03`27/27为旧store身份；当前`R3/cancel-retry-01/after-01`33/33（31 store＋2实际Activity SFC）、`build-02`统一构建与`evidence-verification-01.json`已通过，npm0与外层GBK打印1分列。`frontend-tests-03/build-01`未执行，不再把它当待跑入口。compile-03受控清理通过；terminal-rollback-03长路径失败保留，04单合同仅终态控制语义。各新参数以新attempt留原件，R1业务恢复保留candidate05已签身份；candidate06生产IPC/原生/健康及全链时延未授pass。

### R3 重装预览弹窗

完成门：普通高级入口立即给反馈；慢、错、过期、取消均可见且不误提交。原失败“30秒未出现确认”需有相同分支的新包事实，不能用另一个健康预览覆盖。

| CASE | 类型 | 操作与必须断言 | 主要证据 | 状态 |
| --- | --- | --- | --- | --- |
| CASE-R3-01 | C/I/R | 正式环境页高级入口，构造旧案对应多包缺损后点击普通重新安装；≤300ms显式加载/可取消反馈，最后计划窗准确对应目标与新环境/旧资料保留 | 输入/反馈/最终弹窗图、计划摘要、计时 | not-run |
| CASE-R3-02 | U/C/I/R | 慢预览时鼠标/Esc显式取消，分别在受理前及取消IPC在途立即重开；不新建第二扫描或复用可确认计划，提示等待收尾，终态后可重开。切页继续共享，晚到结果不重开/误提交；按上方参数逐目标记录 | 取消/重开/迟到事件、任务数/目标、零写与截图 | partial（store及Activity隔离合同33/33、统一build-02 pass）；App/EnginePanel原生not-run |
| CASE-R3-03 | U/C/I/R | 预览权限/完整性错误及 worker异常分别返回；弹窗或页面准确显示可理解错误并可关闭重试，不留不可取消遮罩 | 错误原件、错误图、控件恢复、零写 | not-run |
| CASE-R3-04 | U/C/I/R | 预览后切 root/release/engine/generation 或引入目标占用再确认；旧计划被拒绝并引导重新检查，不能把旧摘要静默套用 | 旧新身份、占用证据、拒绝图、零提交 | not-run |
| CASE-R3-05 | U/C/I/R | 普通及四引擎弹窗取消/Esc/Tab/ShiftTab/焦点返回，详情展开收起及一致亚克力颜色可读；重复点击只提交一次，取消不改 receipt/绑定/资料 | 键盘事件、焦点与样式图、任务数、SHA | not-run |

### R4 扫描与启停性能

完成门：前后计量同口径，能解释各扫描阶段与读字节；任何减少重复扫描的实现均保留 generation/计划摘要与执行前必要验证；达不到目标按差距记录，不能用跨操作不可信缓存授予健康。

| CASE | 类型 | 操作与必须断言 | 主要证据 | 状态 |
| --- | --- | --- | --- | --- |
| CASE-R4-01 | U/C/I/G/R | 同 R0 fixture 完整检查 after 1次，记录 Python/receipt/环境/源码/额外文件阶段文件数、逻辑哈希字节与进程 I/O 差值；重复检查数据保持真实，不遗漏异常 | before/after 可比性、阶段指标、完整检查终态 | not-run |
| CASE-R4-02 | I/G/R | 相同最小 GUI 源码缺损做 after 1次正式修复，≤15min目标；非目标/资料集合 SHA不变，必须修复后正式核验完成 | 缺损清单、修复任务、阶段读量/时间、SHA | not-run |
| CASE-R4-03 | I/G/R | 同 fixture 保留旧实例重建 after 1次，≤25min目标；新旧实例/绑定/恢复记录正确，不通过删旧目录提速 | 重建任务、保护核验计数、实例与资料manifest | not-run |
| CASE-R4-04 | C/I/G/R | 同机串行取3次轻概况启动→HTML/API200→停止样本；目标启动至HTML/API语义200且打开网页入口可见≤60s，终态到按钮≤500ms；保留启动前完整验证，停止后端口关闭、按钮恢复 | 点击/首帧/ready/200/stop时间、PID端口、截图 | not-run |
| CASE-R4-05 | U/C/I/G/R | 在检查→计划→确认→执行链路测同操作扫描次数；再引入文件/代次/计划变化，必须检出并拒绝旧计划；跨操作缓存不得绕过完整性保护；验证候选＋非目标e树合计MAX_TREE/50k：boundary候选metadata预检、正式SHA实际读取共享余量、fresh observe且不跨probe；覆盖合计超限、刚好边界、增长读、取消优先与未知文件；两层合计预算19/19模块合同已通过，生产链扫描计量/性能未验，不增预算 | scan identity、计数、异常检测与拒绝结果 | partial（19/19仅模块；生产链/性能未验） |

### R5 最终同包定向沙盒回归

完成门：所有 R5 结果具有同一最终产品提交、EXE SHA、清单/配方 SHA；产品变更使受影响结果失效并重跑最短闭环。四引擎均有本引擎证据；AI Toolkit 与 Anima Fast 的五个未到按钮优先。此阶段覆盖下列模板的参数实例，不以重复历史全量活动扩大测试成本。

| CASE | 类型 | 操作与必须断言 | 主要证据 | 状态 |
| --- | --- | --- | --- | --- |
| CASE-R5-01 | C/I/R/Z | 新独立根正式安装主程序；按R0原ENG-01失败目标（AI Toolkit/DiffSynth）补未安装→计划取消→确认安装→receipt/绑定ready/UI刷新，其他引擎复用核身份的独立健康根；未重做的安装分支保留旧包边界，不声称四引擎同包从零实装 | 新根安装图、目标安装任务与receipt、下载校验、路径/代次 | not-run |
| CASE-R5-02 | C/I/R | 四引擎各完整检查1次，共4个成功实例，≤300s目标：Kohya/AI Toolkit在网页服务运行时完成，Anima Fast/DiffSynth在服务停止时完成；每引擎另一个服务状态复用取消用例，受理后取消并核服务/安装控制不变，共4个取消实例，不再重复4次完整扫描。零安装修改不等于零任务日志，不声称8次完整检查 | 4完整＋4取消的逐实例报告、完整范围、哈希/任务/200或停服监听证据 | not-run |
| CASE-R5-03 | C/I/R | 每引擎独立点击ENG-06收起再打开、ENG-07高级、ENG-08仅检查、ENG-09重装预览/取消、ENG-10导入probe取消/确认；AI/Anima10入口优先。至少一个受影响代表目标完成正式独立重建（优先AI Toolkit），与主程序正式重建分列。其他目标未执行的确认/完成分支明确保持未测，不能由代表目标授pass；probe不训练/不加载模型 | 4×5动作索引、键盘/鼠标图、任务终态、代表实例变更、probe输出 | not-run |
| CASE-R5-04 | C/I/R | 四引擎各选一个receipt覆盖的小源码文件移入本案隔离备份；正式主按钮发现→计划取消零写→确认精准修复→完整核验→导入probe；依赖最小缺损另参数化，不能用源码修复冒充依赖分支 | 缺损原SHA/备份、计划详情、修复与probe、其他树/资料不变 | not-run |
| CASE-R5-05 | C/I/R | R0识别原ENG-04失败的精确目标/变体并逐项补验；共享恢复核心的有旧快照/首次无旧快照另选最少真实代表场景，使用正式受控中断或核身份的新现场。未覆盖目标保留原状态，不额外要求四引擎各做两轮故障；恢复入口有终态，无旧环境保留现场并给重装入口 | 旧失败映射、中断点/pending、恢复记录、不可恢复提示图 | not-run |
| CASE-R5-06 | C/I/R | 每引擎计划前/计划后取得真实目标lease，修改被阻止；另一独立引擎无冲突安装/检查不要求停网页服务；检查只读继续允许；确认窗详情/取消/焦点均对本引擎核实 | ENG-11/12/13实例、lease、任务/200、零越权写 | not-run |
| CASE-R5-07 | I/R/Z | 最终同包新根启动服务验证HTML与健康/版本API200、点击打开网页、切日志追踪任务、停止及取消启动；校验用户资料哨兵、记录合理新增缓存；最后关闭自有GUI，Job/PID/端口归零 | 请求原件、浏览器截图、日志、资料差异分类、清理报告 | not-run |

R5-03优先复用本轮R5-05已保留的合规fixture，但每项记录实际输入与身份。四引擎检查/五按钮/小源码修复/probe为四目标必测；新增完整安装只补原失败目标，独立重建及额外恢复故障取代表，未测变体继续列缺口。任何缩小受影响必测范围须CR，不得靠“同组件”授具体目标通过。R5-05无法安全触发的必测旧失败保持blocked，不能手改receipt/pending补绿。R5-04依赖缺损只取一个共享小依赖拒绝/修复代表，不删Torch巨型目录或模型，不把代表当四引擎依赖全通过。

### R6 交付

完成门：新结果可追溯，旧报告原样，结论不夸大；同包定向回归通过不等于旧227行全量重新通过。任何 fail/blocked/not-run/pending-review 都须在读者报告首页列出。

| CASE | 类型 | 操作与必须断言 | 主要证据 | 状态 |
| --- | --- | --- | --- | --- |
| CASE-R6-01 | C/I | 为42模板及全部参数实例生成索引，连接旧8失败/52单位与新证据；统计按实际实例，原失败保留，取消/超时/失败分列；每个业务pass有精确报告Pointer及截图 | 新机器矩阵、差距表、旧新映射、报告 | not-run |
| CASE-R6-02 | C/I/R | 冻结输入→导出相对链接图集→离线验SHA/JSON Pointer/截图解码及包身份→抽查失败与四引擎五按钮图片；验包成功只授完整性、不自动授业务通过 | export manifest、verifier、图集复核截图 | not-run |
| CASE-R6-03 | I/R | 记录前后资料集合、所有自有PID/Job/端口/lease及磁盘；仅清本案已核目标，保留失败原件与交付证据；逐阶段push的远端提交由主控验证，不含安装树或敏感资料 | cleanup、owner核对、资料manifest、阶段基线索引 | not-run |

## 旧失败行与新 CASE 的精确衔接

来源为 FINAL06 正式报告列出的8行；它们包含共享入口与原尝试，不等于8个独立确诊根因。新结果新建记录，不能把本表写回旧包将其改绿。

| 旧失败行 | 原问题边界 | 本轮主 CASE |
| --- | --- | --- |
| APP-ENV-004 | 环境页普通重装预览/确认入口不闭合 | R3-01/02/03/04/05、R4-03 |
| ENV-MAIN-01 | 主检查修复父分支，含修复耗时及后续未达 | R1-01/06、R4-02/05、R5-07；主控按原proof逐分支裁定 |
| ENV-MAIN-06 | 高级入口父分支；旧衍生导航成功不能抹父失败 | R3-01/05，单列导航与后续预览结果 |
| GUI-LIFE-05 | 正式重建事务恢复自阻挡 | R1-01…06，经正式Core与GUI入口双层验证 |
| ENG-01 | 有后台安装成功但UI验收失败，目标/页面变化需新证据 | R5-01、R2-05/06、R5-07 |
| ENG-02 | 首完整健康查询等待导致后序未到 | R2-01…12、R4-01、R5-02 |
| ENG-04 | 异常事务恢复分支未闭合 | R5-05、R2-06、R5-06 |
| ENG-09 | 独立重装预览/取消/确认仍有失败 | R3-02…05、R5-03/05；每引擎真实重装完成单列 |

### 旧未闭变体的补充映射（v0.17）

R0/issue-map.json保持原件，不按其中planned_case_ids自动关闭历史条目。下列变体复用现有42模板，但要取得对应业务入口的精确证据；恢复冲突通过不能替代版本切换/删除保护，只读取消通过不能替代提交阶段取消。

| 旧未闭项 | 新CASE参数 | 必须操作与断言 | 当前判定 |
| --- | --- | --- | --- |
| APP-VER-008 | CASE-R1-04、R5-06的版本切换参数 | 在自有夹具分别构造目标结构缺损、真实占用，从正式切换按钮触发；拒绝有原因，当前绑定及非目标保持；恢复有效条件后再操作成功 | not-run；不凭恢复入口的冲突合同授通过 |
| APP-VER-011 | CASE-R5-06的删除保护参数 | 从正式版本删除入口请求删除当前版本，明确拦截且目录/登记/绑定无删除；不为测试解除保护 | not-run |
| APP-ENV-003 | CASE-R2-12的主程序只读参数 | 真实主服务运行时从主程序检查入口完成只读检查，网页/API继续可用；安装控制与资料保持，无隐式修复 | not-run；引擎只读不能代验主程序 |
| APP-LOG-023 | CASE-R1-06及R5-07的日志监视区参数 | 从集中日志任务区对修改操作发取消，覆盖可取消阶段与提交收尾；重复取消幂等，已终态控件禁用；按accepted/commit-in-progress/已终态真实响应核pending/receipt/资料及回收，不把只读query取消结果套用 | not-run；可复用同包既有真实修改session，不额外增加重建轮次 |
| APP-HOME-015 | CASE-R4-04、R5-07的停止失败重试参数 | 用自有服务的安全受控故障点形成stop_failed，从正式重试按钮停止；错误/可重试反馈、权威终态、端口与按钮正确恢复 | not-run；若无法安全构造则blocked，正常停止成功不关闭该分支 |
| ENV-LEGACY-01…03 | historical-gap（历史缺口） | 非受管旧配方的正向执行不属于本轮受管legacy原journal收尾；保持原包、原状态与原因 | 本专项不授通过，不因新增续办入口自动关闭 |

失败/受阻按具体变体保留，不删旧失败。新增参数采用轻量夹具或既有同包session，不对四引擎扩增重型安装/扫描轮次。

## 52 引擎单位展开规则

必须生成四个 engine ID：`kohya`、`anima-fast`、`ai-toolkit`、`diffsynth`；每个分别生成 ENG-01 至 ENG-13，主键为 `<candidate_sha>/<engine_id>/<ENG-ID>/<variant>`。不能以当前选择引擎或一个 task_id 复用于四个目标。

| 旧模板 | 对应新 CASE 与参数化要求 |
| --- | --- |
| ENG-01 安装 | R5-01：取消/确认/完成刷新 |
| ENG-02 健康主按钮 | R5-02：服务停止/服务运行；R2-01/02任务接收及单飞 |
| ENG-03 损坏修复 | R5-04：源码/依赖、取消/确认；尚未构造的分支保留not-run/blocked |
| ENG-04 可恢复异常 | R5-05：有旧快照/首次无旧快照的真实中断事务 |
| ENG-05 不可恢复提示 | R5-05：异常诊断/高级仍可重装，不能冒充恢复成功 |
| ENG-06 收起结果 | R5-03：收起再打开，本引擎状态保留 |
| ENG-07 高级选项 | R5-03：鼠标/键盘，路径/代次可读 |
| ENG-08 仅检查文件 | R5-02/03、R2-12：普通/服务运行/允许的其他apply期间只读 |
| ENG-09 重新安装 | R5-03：四目标预览/取消、代表目标确认真实终态；其他确认/完成保留具体缺口；R3负例与R5-06冲突 |
| ENG-10 运行检查 | R5-03/04：取消/确认导入probe，GPU/驱动/模型与真实训练不在验收范围，保留不适用边界 |
| ENG-11 计划详情 | R5-04/06：展开/收起，write_roots/source_paths/packages与计划一致 |
| ENG-12 取消与焦点 | R3-05、R5-03/06：取消按钮/Esc/Tab/ShiftTab，取消零安装写 |
| ENG-13 占用复核 | R5-06：计划前/计划后目标占用、其他引擎无冲突；R2-12允许只读 |

每个52单位的 variants 单独给结果及证据；一部分variant通过时单位最多partial，不因主路径通过清空剩余分支。AI Toolkit 与 Anima Fast 原各5个未操作按钮为 ENG-06…10，本次每一个必须有独立实际输入证据；Kohya历史操作与待复核单元也不能移植成新包pass。若 GPU/驱动故障验证不适用，写清用户本轮“不真实训练”的边界，不能顺手声称 GPU能力通过。

## 历史未闭项处置台账（v0.20补齐，v0.21保留）

来源为FINAL06冻结的`evidence-bundle/adjudication/combined-controls-227.json`，以下恰为24条partial、1条blocked和1条pending-review。上方原27条映射及42CASE主表保持，不增加重型测试轮次。表中CASE是后续取证位置，不表示已经通过；共用session必须取得本入口的实际输入、状态与精确报告Pointer。未覆盖variant保持历史结果，`repair_campaign_complete`不自动变成全局`acceptance_complete`。

| 原ID | 原状态 | 本轮处置/可复用CASE | 不能据此关闭的缺口 |
| --- | --- | --- | --- |
| APP-HOME-011 | partial | R4-04/R5-07新根启动；旧main链另记 | 旧89合法环境可启动仍为历史缺口 |
| APP-HOME-015 | partial | R4-04/R5-07的stop_failed重试参数 | 正常停止不能代验失败重试 |
| APP-HOME-020 | partial | R1-06/R5-07共用修改session，取得首页取消输入 | 日志页取消不能代验首页按钮及其终态 |
| APP-VER-008 | partial | R1-04/R5-06版本切换拒绝/成功 | 必须从本入口验证结构坏、真实占用 |
| APP-VER-011 | partial | R5-06当前版本删除保护 | 恢复冲突拒绝不能代验删除保护 |
| APP-ENV-001 | partial | R3-01多坏包、R4-02源码修复 | 半装无binding、目录丢失、Python坏等未测variant保留 |
| APP-ENV-003 | partial | R2-12主程序服务运行时只读检查 | 独立引擎只读不能代验主程序 |
| APP-LOG-023 | partial | R1-06/R5-07修改取消、提交收尾、重复/终态 | 只读检查取消不能代验修改提交 |
| APP-BASE-001 | partial | R2-05/06慢响应切页/迟到隔离可共用 | 未取得App完整Report早晚到证据则保持partial |
| ENV-MAIN-04 | partial | R4-02同session观察修复中与终态 | 预览错误不等于修复执行失败；未测失败分支保留 |
| ENV-ADV-03 | partial | R4-02非目标保护可复用非当前目标变体 | 未取得“非当前修源码且不切版”证据则保留，不另起重案 |
| ENV-LEGACY-01 | partial | historical-gap（历史缺口）保留 | 非受管旧配方不能由受管legacy journal收尾代验 |
| ENV-LEGACY-02 | partial | historical-gap（历史缺口）保留 | 同上，保持原包/原因 |
| ENV-LEGACY-03 | partial | historical-gap（历史缺口）保留 | 同上，保持原包/原因 |
| ENG-03 | partial | R5-04四目标源码缺损/取消/确认 | 依赖变体仅按实际代表证据授结果，其他目标保留 |
| ENG-05 | partial | R5-05最少异常/不可恢复代表 | 其他目标未做仍保留具体缺口 |
| ENG-06 | partial | R5-03四目标收起再打开 | 必须逐目标实际输入 |
| ENG-07 | partial | R5-03四目标高级选项鼠标/键盘 | 不能以同名控件跨目标代验 |
| ENG-08 | partial | R5-02/03、R2-12完整/允许并发只读 | 各服务状态按4完整＋4取消及具体variant记录 |
| ENG-10 | partial | R5-03/04真实import probe取消/确认 | 不授训练、模型、GPU/驱动异常分支通过 |
| ENG-11 | partial | R5-04/06计划详情展开/收起 | 逐目标核内容与真实计划 |
| ENG-12 | partial | R3-05/R5-03/06取消/Esc/Tab/归焦 | 未操作的具体弹窗不能由代表目标代验 |
| ENG-13 | partial | R5-06计划前后真实占用/其他目标无冲突 | 不恢复网页服务全局排斥 |
| TRUST-01 | partial | historical-gap（历史缺口）保留 | 原测试会话分支不属本专项，不以资源查询代验 |
| GUI-LIFE-07 | blocked | 当前源码不可达，保持历史blocked | Core rollback合同不能声称对应UI已到达 |
| APP-HOME-014 | pending-review | R5-07取消启动，显式补旧ID映射 | 必须最终包首页实际取消输入及Child/Job/监听结果 |

## 测试分层与阶段适用映射

| 阶段 | Unit | Contract | Integration | Gray | Real | Zero-Short |
| --- | --- | --- | --- | --- | --- | --- |
| R0 基线与测量 | 采集器已知量 | 身份/指标schema | 采集链及manifest | 原基线before | 自有目录与受限测量 | 不单独执行；由R5新根覆盖 |
| R1 恢复自阻挡 | guard身份判定 | 错ID/事务kind | 正式Core至事务恢复 | 正反例行为对照，不以旧失败代替运行 | 真实pending/lease/资料保护 | 不重做首装；以R5新根作最终适用性 |
| R2 可取消引擎检查任务 | 单飞键/订阅/取消/deadline | 任务及事件schema | 前端/IPC/Rust/worker | 旧同步等待与新任务行为对照 | 真worker、锁、哈希与Job | 不独立首装；R5健康环境执行 |
| R3 重装预览弹窗 | 迟到/过期状态机 | 预览身份/错误 | 弹窗至计划链 | 原失败分支新包回归 | WebView/慢预览/真实缺损 | 不全新安装；新根R5引用相同组件 |
| R4 扫描与启停性能 | 计数/去重复边界 | 期限/计划身份 | 检查/修复/重建/启停 | 同fixture前后测 | 同机计时与增量读字节 | 不另起整轮；启动新根在R5 |
| R5 最终同包定向沙盒回归 | 不重复独立单元套件，引用已过构建证据 | 真实IPC/API断言 | 全链路 | 身份一致的前阶段变更影响核对 | 四引擎与GUI真实维护、无训练 | 新目录/新绑定/正式安装/启停 |
| R6 交付 | 无产品单元变化，不适用 | schema/SHA/Pointer | 图集/验包/清理 | 旧新映射保留 | 离线证据可读性及端口回收 | 不适用；不把离线验包冒称新根实测 |

当前实现范围说明：`full`与`files_only`均验证完整内容闭包，均不运行import/GPU；运行检查以独立probe实测。不得宣传前者/后者存在未经测量的额外提速，也不得把源码文件检查称为训练通过。

## 证据 schema 与保存合同

每个实例最少一个 `case-result.json`，截图、事件和外部原件只存引用，不把大文件内嵌 JSON。可扩展字段不可覆盖原件；下面是规划schema示例，`null`/`not-run`都不是测量结果。

```json
{
  "schema_version": 1,
  "plan_id": "desktop-launcher-reliability-20261102",
  "run_id": null,
  "case_id": "CASE-R5-03",
  "instance_id": "ai-toolkit/ENG-10/confirm",
  "status": "not-run",
  "candidate": {"commit": null, "exe_sha256": null, "catalog_sha256": null, "recipe_sha256": null},
  "target": {"root": null, "release_id": null, "engine_id": "ai-toolkit", "instance_id": null, "generation": null},
  "fixture": {"manifest_sha256": null, "cache_state": "unknown", "fault_point": null, "ownership_proof": null},
  "task": {"id": null, "subscription_ids": [], "worker_pids": [], "job_identity": null, "terminal": null},
  "time": {"utc_start": null, "utc_end": null, "monotonic_start_ms": null, "elapsed_ms": null, "accepted_ms": null, "first_feedback_ms": null, "cancel_accepted_ms": null, "scan_stopped_ms": null, "job_reclaimed_ms": null},
  "metrics": {"stages": [], "files_hashed": null, "logical_hash_bytes": null, "process_io_read_bytes_delta": null, "io_scope": "unknown", "network_bytes": null, "scan_count": null, "censored": false},
  "assertions": [],
  "evidence": {"screenshots": [], "report_pointers": [], "events_jsonl": null, "before_after_manifests": []},
  "legacy_links": [{"engine_id": "ai-toolkit", "control_id": "ENG-10", "original_status": "blocked", "original_report_sha256": null, "original_pointer": null}],
  "cleanup": {"owned_processes_reclaimed": null, "ports_closed": null, "leases_released": null, "profile_diff": null},
  "limits": ["no-training"],
  "failure": null
}
```

`assertions` 中每项带 expected/actual/status、源JSON Pointer或文件SHA；截图逐件列相对路径、SHA、UTC及任务/目标身份。截图须来自真实运行的WebView/浏览器，不能用UI预览或伪造状态替代。阶段事件包含单调seq、UTC/单调时钟、task/target、phase、waiting_reason、files/bytes及取消状态；逻辑哈希字节与进程 I/O字节分别列，进程I/O可能包含非磁盘读取，不能叫物理磁盘吞吐；OS无法按本操作准确归属时写unknown。记录启动前计量和进程创建时点，不能仅用退出时累计I/O作优化证据。

资料检查区分原有文件“改动/缺失”和合理新增缓存。旧冷启动案因新增 `config/.update_cache.json` 整步失败原样保留；新案定义并记录新增缓存规则，不得事后删缓存掩盖差异，也不能忽略其他新增文件。完整性保护的receipt/清单不因性能目标而删项。

状态只使用 `not-run/pass/partial/fail/blocked/pending-review`；任务终态另列 `succeeded/cancelled/timed_out/failed`，业务成功与验包完整性分开。失败保留原始输入、错误、截图、最后阶段、任务/lease/进程回收与下一步；修复后新增attempt，旧attempt不覆盖。新包适用性不足的历史成功保持pending-review。

## 决策、风险与执行状态

当前事实、阶段台账、已核代码/候选身份统一见[任务书](reliability-performance-20261102-task-book.md)，先读其 v0.29 基线，本附件不建立第二份进度。R0/R1 done，R2/R3 in progress，R4–R6 pending；旧失败和各attempt身份保留，父CASE不能从一个参数通过推成全绿。

P1包括新独立环境事务/Job恢复、未闭全链取消/时延及扫描保护；其最小前提和退回路径见[开工复盘](reliability-performance-20261102-readiness.md)。文档可审阅不等于这些前提通过；缺资源/未知归属/控制漂移/回收失败保现场，不进入依赖它的危险写入。性能未达不得自行删CASE或提高时限。

本次只同步规划，不运行原生、不改 Goal。唯一后续执行动作见任务书开篇 v0.29 与末尾；10 已构建并预览失败，先逐字段定位组合拒绝，后继候选质量/冻结/正式预览真正通过后，才续原故障/修复链。原 CASE、性能阈值、42 主表及旧映射保持。
