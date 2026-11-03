# 启动器可靠性与性能返修：定向沙盒验收设计

## 计划元数据

- Plan ID：`desktop-launcher-reliability-20261102`；附件ID：`acceptance`；Version：`0.15-executing`；Last updated：2026-11-03 12:35，Asia/Shanghai。
- Execution readiness：`executing`；Current active phase：R2 可取消引擎检查任务；R0/R1 done，R3 in progress，R4–R6 pending。RP-EXIT-R1已签；R2–R4门未签，旧文档快照仅历史。
- Canonical progress file：沿用 [00_总控目标索引.md](00_总控目标索引.md)。本文件是新返修计划的验收附件，不设第二份总进度。
- Related handoff：none；历史输入为上一轮[正式报告](full-acceptance-20261101-report.md)与[原任务书](full-acceptance-20261101-task-book.md)。本轮依据为[新任务书](reliability-performance-20261102-task-book.md)、[开工门](reliability-performance-20261102-readiness.md)和[新Goal](03_goal提示词/启动器可靠性与性能修复_20261102_goal提示词.md)。
- Current branch：计划目标为 `feat/desktop-launcher`；执行者在 R0 记录真实分支、HEAD、脏文件与工具版本，不把本文目标当作现场检查结果。
- 稳定用例：42个CASE模板；R0四行仅基线pass。Rust10＋13＋33、Python30＋13各有模块证据；前端33/33含31项store＋2项实际Activity SFC，并已统一build-02。terminal-rollback-04仅单合同控制语义pass；原生/四引擎/性能未闭，模板数、模块断言数和实测实例数分别统计。
- 用户已通过active Goal授权并继续完整R0–R6。本附件保存当前实测合同与已验证/待验证边界，文档更新不替代执行。当前已有一个真实恢复主路径成功及终态回退控制语义合同，尚无全部阶段或训练结论；阈值是执行目标，各CASE取得实际证据后才更新。

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
| CASE-R2-07 | C/I/R | 在基础Python完整核验、原守卫枚举及控制记录读取中分别取消；≤1s接受、≤5s停止，无worker继续启动、完整guard保持。32MiB边界/metadata后增长/增长中取消或期限按下方参数，Catalog验签段补测 | 屏障/计数、原错误、控制状态SHA与进程审计 | partial（读取层合同pass）；真实整链及时延not-run |
| CASE-R2-08 | C/I/R | 独立自有进程持有真实工具缓存 lease，让 query 进入等待后取消/期限到；等待原因可见、可取消，不使用无关 token 无限等 | lease 证据、等待/取消事件、零新 worker | not-run |
| CASE-R2-09 | U/C/I/R | 在完整树遍历以及大文件分块 SHA 两个位置取消；分块循环响应，≤5s停止扫描，所属 Job≤10s回收；只读树保持不变 | 两参数实例、块/文件计数、读差值、Job证据 | not-run |
| CASE-R2-10 | U/C/I/R | 总期限在启动前/worker运行两路径到达；准确标timeout，不能伪装cancelled或integrity failure；排队/加入共享任务/重订阅不刷新绝对期限。准备/输入/输出/回收都在同一期限；保留最后扫描计数与原因 | deadline事件、两终态、各阶段用时/剩余量、回收结果 | not-run |
| CASE-R2-11 | C/I/R | 断开本案IPC/事件、关窗或worker异常，坏帧/超大输出/stdin不消费/未关输出管道均有终态与有界缓冲。分别记录产品worker和测试宿主的Child wait、stdin关闭、两reader join、Job前后active、是否强制终止及关闭句柄补清理；实际编译由新宿主承载，保留compile-02回收失败 | 各异常身份、错误图、逐项资源证明；宿主/产品分列 | partial；旧微型桥/宿主及compile-03受控清理原身份保留；Anima停服full正常成功分支的worker wait/stdin关闭/readers join/Job0与宿主自然退出已验，异常/断连等分支及取消回收时限仍未验 |
| CASE-R2-12 | C/I/R | 网页服务运行时做只读检查；另一目标允许的独立维护进行时仍可查询。跨目标并发按设计限流，等待有原因，真正冲突修改仍拒绝 | HTML/API、目标冲突域、任务和UI状态 | not-run |

旧Rust前置证据：r4-scan-01的8/8及r1-core-regression-05的12pass/1专属lease helper ignored保留原身份；前者Job受控1→0、后者自然0→0。最新final-cancel-green-01的7/7、exit0、源稳定、Job受控1→0已验证真实OperationManager取消/提交竞争、原子写与Core成功收口；不授全部门后工作≤10秒或原生恢复通过。

最新合计资源合同：combined-budget-green-01的19/19、exit0、源稳定、Job自然0→0；boundary本次非目标实际SHA树统计＋候选metadata预检；正式SHA/preservation用fresh非目标metadata统计＋候选实际读取余量；validate前后observe各用本次非目标实际SHA统计，不跨probe，原4GiB/50,000节点不变。修前3案RED保留；只授模块保护，性能/整链待验。

当前v0.15证据边界：R0/R1 done，RP-EXIT-R1按正式恢复缺陷及保护范围签收；R2可取消引擎检查任务active（in progress），R3必要前置in progress，R4–R6 pending。candidate05下native04真实UI取消留下合法committing事务，新进程正式GUI recover04 succeeded、intent committed并绑定g1208b56f57f3e752，正式IPC重复恢复也succeeded。两原生suite/host均pass，资料/控制保护及自然Job/CDP回收通过。当前full Rust344pass/0fail/15ignored，60份Rust/Cargo输入与当前及candidate05一致。R1-04按参数证据pass-with-boundary，不夸全GUI矩阵；R1-06最终CAS合同及实际命中原生window通过，分块取消/性能时限仍属R2/R4，未外推。Anima Fast停服full单配置实测suite/host通过，首反馈1.9ms、任务ID可见上界17.1ms、完整检查保守285776.1982–285935.7808ms，worker/readers回收及控制/资料保护通过；仅授该配置，取消与余三引擎未验。旧native02/03失败保留，recover03禁止。R2–R4门未签，嵌套Operation取消盲区仍待修。R1阶段Git保存待做，当前增量未提交/未push；整个专项/既有active Goal尚未完成。 原生04只授真实命中window；当前R1审计与阶段门见本run audit02/completion02，恢复/幂等已验，R2/R4时限未授pass。

#### R2/R3 针对性参数与当前证据边界（v0.15）

R4嵌套取消与阶段计量追加参数：新发现的R4嵌套取消盲区，尚未修复/实测：gui_registration_integrity普通Python verify、gui_entry_probe原/副本source verify、runtime_view递归复制、Operation控制记录读取（scan_observation目前仅Query TLS）、engine_namespaces控制读取/摘要、instances内存树语义及probe静态文件读取，逐项贯通外层Operation token，并在真实首块/首节点屏障触发取消；清理阶段不中断。计量分plan、before-observe、可信闭包、validator、复制、副本校验、entry probe、after-observe、最终门。暂不删除execute→finish第二validator/probe，before/after完整扫描保留；并入现有CASE-R1-06/R2-07/R2-09/R4-05参数，不新增CASE或重型轮次。这组全链指标继续阻断R4/R5和最终交付。 R1-06业务已验与时延not-run分列，阈值不降；R2 Anima停服full一配置6 checks通过，不授取消/其他引擎。

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

已有原件：`R2/python-tests-01/query-01`30/30、`legacy-02`13/13；`R2/rust-integration-01/{scan-01,bridge-01,tasks-01}`分别10/13/33通过，7桥进程案已显式include-ignored，微型worker回收不代替生产链。`R2/frontend-tests-03`27/27为旧store身份；当前`R3/cancel-retry-01/after-01`33/33（31 store＋2实际Activity SFC）、`build-02`统一构建与`evidence-verification-01.json`已通过，npm0与外层GBK打印1分列。`frontend-tests-03/build-01`未执行，不再把它当待跑入口。compile-03受控清理通过；terminal-rollback-03长路径失败保留，04单合同仅终态控制语义。各新参数以新attempt留原件，生产IPC/原生/健康及真实提交恢复未授pass。

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
| CASE-R4-04 | C/I/G/R | 同机串行取3次轻概况启动→HTML/API200→停止样本；目标启动≤60s、终态到按钮≤500ms；保留启动前完整验证，停止后端口关闭、按钮恢复 | 点击/首帧/ready/200/stop时间、PID端口、截图 | not-run |
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

- Verified facts：R0/R1 done，RP-EXIT-R1按正式恢复缺陷及保护范围签收；R2可取消引擎检查任务active（in progress），R3必要前置in progress，R4–R6 pending。candidate05下native04真实UI取消留下合法committing事务，新进程正式GUI recover04 succeeded、intent committed并绑定g1208b56f57f3e752，正式IPC重复恢复也succeeded。两原生suite/host均pass，资料/控制保护及自然Job/CDP回收通过。当前full Rust344pass/0fail/15ignored，60份Rust/Cargo输入与当前及candidate05一致。R1-04按参数证据pass-with-boundary，不夸全GUI矩阵；R1-06最终CAS合同及实际命中原生window通过，分块取消/性能时限仍属R2/R4，未外推。Anima Fast停服full单配置实测suite/host通过，首反馈1.9ms、任务ID可见上界17.1ms、完整检查保守285776.1982–285935.7808ms，worker/readers回收及控制/资料保护通过；仅授该配置，取消与余三引擎未验。旧native02/03失败保留，recover03禁止。R2–R4门未签，嵌套Operation取消盲区仍待修。R1阶段Git保存待做，当前增量未提交/未push；整个专项/既有active Goal尚未完成。 stage-evidence-audit-02核full344的60份Rust/Cargo与当前/candidate05一致、日志SHA一致；Rust全套Job受控1→0，原生04自然回收，勿混称。
- Active assumptions：新沙盒可供四引擎完整安装与暂存/回滚；正式故障点能安全构造恢复与异常分支；进程读字节有可用采集权限。均在R0验证，不预授pass。
- Locked decisions：原始报告、失败截图与receipt不篡改；新CASE另记；不训练；不降完整性；不以其他引擎或旧包证据补绿；只在自有范围取消与回收。
- Open questions：阈值已获执行授权，同机完整检查≤300s、重建≤25min实际可达性仍待测；R2独立查询管理器接口设计已落盘，实现已落，仍须验证共享取消与终态竞争；历史未计流量/峰值仍unknown。
- P1风险：总期限未覆盖启动前验证；跨generation结果误用；共享取消误伤其他订阅；真实lease被过宽豁免；为提速削弱保护；未达阈值却按日志ready授予通过。任一存在且无明确延期决策，不能签最终验收通过。
- P2风险：四引擎维护需要较多磁盘和网络；计时受缓存/杀毒/磁盘影响；fault fixture无法安全构造。记录资源和不可比边界，不擅自更换更小配方冒称原目标完成。

| 稳定阶段 | 进度 | 测试状态 | 本文要求的阶段输出 |
| --- | --- | --- | --- |
| R0 基线与测量 | done | pass（仅基线） | 六探针、身份/fixture/采集/资源及9次原生导航；R0/stage-completion.json |
| R1 恢复自阻挡 | done | pass-with-boundary，RP-EXIT-R1已签 | 主恢复旧证据＋当前full344参数/lease/CAS＋native04真实取消/GUI恢复/IPC重复；R1-04不夸全GUI，时限留R2/R4；stage-completion-02.json |
| R2 可取消引擎检查任务 | in progress | active，Anima停服full单配置suite/host及6 checks通过 | 反馈1.9ms、受理上界17.1ms、完整检查保守≤285.936秒、worker/readers/Job回收与资料控制保护；其余配置及取消未验 |
| R3 重装预览弹窗 | in progress | 旧33/33/build-02原身份保留；target_binding VNode4/4/frontend-build-01 pass，真实GUI未闭 | main-preview工具16/16合同/两语法仅授工具；主/引擎准备窗/焦点/首反馈仍需原生证据 |
| R4 扫描与启停性能 | pending | 当前合计预算19/19模块GREEN；自然Job0→0 | 真实同机前后计量/完整性与原生结果待补，不提前签门 |
| R5 最终同包定向沙盒回归 | pending | not-run | 四引擎52单位分支、新根服务/资料/回收 |
| R6 交付 | pending | not-run | 差距报告、截图图集、验包与清理记录 |

每阶段验收仅更新主控进度与新证据索引；阶段push基线由主控执行并记录远端SHA，不把“push成功”当作阶段业务通过。若R0测量证明目标不现实，原目标与失败样本保留，提出含原因、影响和替代测法的CR；变更经既有授权/审阅流程落定后才能变更完成门。

下一步动作：后续续接的唯一下一动作：由Root按原阶段授权核对R1精准变更集并保存commit/普通push及远端SHA回执；本轮文档审核不执行git保存、GUI、构建或新测试。R1业务门通过不等于远端阶段基线已保存，含R2/R3必要前置源码不代表其阶段通过。Anima full原案已结束，不等待exec96794、不重复该案；42CASE、七阶段、4完整＋4取消、原阈值/资源、旧8失败行/10未操作按钮/52单元保持。
