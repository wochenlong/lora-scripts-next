# CR-020 资料复盘、最小探针与开工门

日期：2026-11-02（Asia/Shanghai）；版本`0.2-executing`；模式`plan system update`。当前结果为**已授权执行，R0完成、R1进行中；六探针与原生轻反馈校准已收口，产品修复/重型恢复尚未通过**。本文件承接专项预检、最小可行性方案、编号门禁和最终文档复盘，复用既有Full体系，不生成新的平行总控或多层审计。

## 资料复盘

| 来源 | 本轮读取/核验 | 用途及边界 |
| --- | --- | --- |
| [总控](00_总控目标索引.md)、[manifest](plan-manifest.md)、[CR-019报告](full-acceptance-20261101-report.md) | 已读 | 现有分支、最终包、227/52及未闭状态；报告为证据，不是新修复通过 |
| Git状态/日志及远端`feat/desktop-launcher` | 只读已核 | 规划前HEAD与远端`91e3d2e6…`；最后产品`4e1b4cc7…`，其后无产品修复；开工时重核当前值 |
| `core.rs / gui_rebuild.rs`及旧独立根因记录 | 已读 | P1精确恢复自身pending仍会被全根guard拦截，发生在持久任务前 |
| `EnginePanel.vue / main.rs / core.rs / engine_bridge.rs / control.py / runtime.py / worker.py` | 主代理/专项只读复核 | 已有异步线程与worker回收；缺端到端query任务/取消/进度，900秒属于旧验收器门 |
| `App.vue`重装确认与`gui_source_repair.rs / instances.rs`扫描路径 | 已读 | 确认窗等预览、重复完整扫描；未证明每阶段真实耗时 |
| 旧查询终态/54分钟源码维护/85分钟重建原件与只读路径审查 | 已读 | 不重复旧重操作，不覆盖原fail；原累计进程I/O不作单任务增量证据 |
| [共用证据治理](00_预检证据/testing-and-evidence-governance.md)、[失败模板](00_预检证据/failure-report-template.md)、[完成门](00_预检证据/stage-completion-gate-template.md)、[清理模板](00_预检证据/evidence-cleanup-report-template.md) | 已读并复用 | 其中旧M0–M6及CR-004历史调度不覆盖CR-019/020；本轮禁止训练、采用针对性真实功能验收 |

事实、假设、固定决策和开放问题以[任务书决策记录](reliability-performance-20261102-task-book.md#决策记录)为准。R0初始磁盘为E余163.69GB、F余863.12GB；指定根元数据已核，历史未计流量/峰值仍`unknown`。新重下载0、E本run≤200MiB、F新增≤80GiB，逐重案核精确备份/暂存峰值；不能把当前余量当历史合规证明。生产密钥、GPU/模型或新机器均不作为本轮前置。

## 最小可行性探针（已授权，当前R0）

六探针已执行，结果仅支持基线复现、已有保护或原型可行性；不授产品修复通过。每案≤120秒，使用新标记小夹具、合成数据和自有进程；无需下载模型。输出保存于当前run的`R0/probes/<probe-id>/`，只回收本案资源。

| Probe | 高风险前提/方法 | 必须核对的结果 | 失败退回 |
| --- | --- | --- | --- |
| RP-PROBE-01 | Core公开入口构造目标自身committing及另一个release，重现guard自阻挡；再构造同release第二事务 | 旧失败可复现，精确事务身份/备份可验证；没有删除或全release绕过guard的必要 | R1设计；暂停恢复写入 |
| RP-PROBE-02 | worker尚未启动时，分别模拟基础Python大文件核验、工具锁等待、stdin不消费/管道堵塞 | 端到端deadline与同一CancelToken能覆盖每段；超时不遗留子进程或发布不完整工具缓存 | R2桥/任务设计；不先签取消可用 |
| RP-PROBE-03 | 合成worker交错输出进度、终态、stderr、截断/坏JSON、非零退出 | 严格帧/版本合同，只收一个权威终态；进度不当最终结果，内存有界 | R2协议，禁止直接应用到生产worker |
| RP-PROBE-04 | 双订阅同一root/engine，关一个页、取消一个订阅、显式取消共享任务、generation变化后晚到结果 | 单worker；订阅生命周期与任务取消分开；过期成功不能覆盖新dirty，任务级取消明确影响范围 | R2订阅/单飞合同 |
| RP-PROBE-05 | 小树新旧保护判定对照，内容同大小/mtime替换、额外文件、链接、receipt/所有权中途变化 | 当前完整性覆盖与未知拒绝保持；只有同观察阶段复用，不能依赖mtime/size | R4设计；无法证明则保留全校验 |
| RP-PROBE-06 | 正式只读查询前后逐字节比较小fixture安装控制文件，记录允许日志/固定工具缓存 | registry/engine state/generation/receipt/pending/intent/binding不变；查询不取得变更锁，也不妨碍合法独立目标 | R2状态边界，禁止接成隐式修复 |

探针失败不删除原件、不无限重试；先定位并改最小设计，保留新的attempt。普通设计/脚本问题由执行者修正后继续，不能以“探针仅规划”绕过R0解锁条件。已知产品P1是本轮待修目标，不等于禁止为修复它进行受控开发；未证的新保护假设则必须先有探针结果再进入依赖它的真实写入。

### R0实际结果（2026-11-02）

- RP01：3个小夹具测试通过；正式`rebuild_create + prepare_commit(false)`形成合法committing，再从Core复现自阻挡。精确身份例外原型已核，产品仍待R1修复。
- RP02/03/04/06：6份有效报告共36项原型/既有Python入口断言通过；10个有记录的自有Job全部active0。06首次采集锁文件失败保留，仅更正采集器后重测06；管道/协议原型不代表生产桥已实现。
- RP05：2个测试通过，检测同size/mtime改写、额外文件和链接；引擎receipt归属变化被正式控制校验拒绝。单独源码capture不覆盖state/engines的组合缺口保留，后续优化必须补组合保护。
- 单调钟与I/O校准3样本通过；旧Kohya正式worker段120秒有界采样截尾、stdout/stderr均0，实际逻辑读343,477,096B；Job回收且state/receipt未变，内部阶段仍unknown，不冒充全query计时或产品timeout。
- 旧FINAL06新prefs/WebView/空根原生导航9次（日志/设置/版本各3），最大首DOM-rAF耗时60.5/18.5/88.2ms；9.006秒正常退出rc0，Job active0、CDP8960关闭。仅导航采集before，不授重装/启停/查询通过。
- 当前指定证据根总量约4.694GiB，E名义余量约313MiB；本run执行再收紧至200MiB，重制品放F，新增重下载0。已测F相关根约133.81GiB；历史累计未计部分和峰值仍unknown，逐重案核缓存/增量上界，不重置额度。

证据分别在当前run的`R0/probes/`、`observation-calibration.json`、`worker-sample-kohya-01/`、`resources-audit.json`、`current-disk-metadata.json`及`issue-map.json`。原生轻反馈见R0/feedback-before-01/，ROOT实际看图；独立复核及R0/stage-completion.json明确签署RP-EXIT-R0。R1仅按精确根备份及资源门进入受控修复，不将历史unknown消除。

## 门禁与合并产物映射

下面的`plan-pass`只表示该项文档齐备；不代表批准执行或产品通过。为避免与历史门禁自相覆盖，本表是`CR-020/GATE-xx`的本轮实例；旧GATE记录不改。

| Gate | 核对内容与证据 | 当前状态 |
| --- | --- | --- |
| GATE-00 | 资料来源与当前Git/EXE/问题身份，见本文件资料表 | plan-pass |
| GATE-01 | 工作区、唯一总控、新旧证据根、禁止边界明确，见任务书元数据/资源 | plan-pass；R0资源核账完成，unknown及逐重案上界要求保留 |
| GATE-02 | 总目标与四类产品行为、8旧失败/10遗漏映射 | plan-pass |
| GATE-03 | 目标T1–T5、阶段R0–R6、专项/全局完成口径 | plan-pass |
| GATE-04 | 目标验收与测试分工，合并在任务书“目标—验收映射” | plan-pass |
| GATE-05 | 针对性CASE、旧清单映射、六类测试适用范围 | plan-pass；4个R0模板已取得基线证据，38个产品/交付模板not-run |
| GATE-06 | 七阶段Purpose/Outputs/Completion/Validation/Evidence/Failure | plan-pass |
| GATE-07 | 阶段依赖、退出门与不可削弱保护 | plan-pass |
| GATE-08 | 阶段专属开工清单＋共用清单，合并在任务书 | plan-pass；执行前逐项重核 |
| GATE-09 | 新旧证据、SHA/Pointer/真实包/清理与真实限额 | plan-pass |
| GATE-10 | 失败/完成/回收模板复用，变更控制CR-020 | plan-pass |
| GATE-11 | 六个危险前提探针、资源和回收 | pass；六探针已执行，基线/原型结果与产品not-run分列，未豁免 |
| GATE-12 | Goal路径、目标、R0–R6、测试/证据/资源/推进一致 | plan-pass；Goal active，已核授权附件 |
| GATE-13 | manifest索引实际文件/合并规则/阶段与目标一致 | plan-pass；链接/阶段核对无错误 |
| GATE-14 | 文档复盘与执行前置 | pass；RP-EXIT-R0已签，R1按精确根、备份及资源条件开工 |

## 风险与变更处理

| 风险 | 计划处理与实测要求 |
| --- | --- |
| 精确恢复放过其他真实全根冲突，P1 | 持租约后校验唯一事务；Core正式入口拒绝矩阵＋真实恢复，不按release全体豁免 |
| 只改worker时限，前置和输出仍卡住，P1 | 统一从请求入口计时；Python/工具锁/管道/回收均探针，取消回执和资源终态分开 |
| 只读检查被OperationManager变成安装修改，P1 | 明确只读任务锁语义与允许写入白名单，安装控制逐字节保持，服务运行和独立目标允许 |
| 单飞取消误伤另一订阅者或误杀用户进程，P1 | 取消订阅不等于取消任务；显式任务取消告知共享影响，只回收有身份的自有Job |
| 扫描复用漏报同大小/mtime篡改或越过探针写入，P1 | 只允许同观察阶段共享事实；身份/范围不明、写入后或未知目录均重新完整检查/拒绝 |
| 排除引擎实体后夸称所有非目标字节保护，P1 | 必须证明所有权及写路径约束；控制摘要不是整个引擎内容未改的证明，无法证明等价保护先保留全扫描 |
| deadline到达强杀提交造成半提交，P1 | 可取消阶段和不可中断提交收尾分开；持久恢复票据保留，终态待真实回收，不先显示已取消 |
| 性能目标过严或机器负载波动，P2 | 数值为待审目标；R0阶段计时和同夹具对照，目标未达保留失败，不偷换场景算倍速、不静默放宽 |
| 旧failed被新成功覆盖、模板事实代替具体引擎，P1 | 新包新attempt，原行/变体/52单元精确映射；专项complete与全局complete分列 |

涉及新权限、路径/资料/信任边界、测试范围、性能阈值或接受P1延期时，进入[CR-020变更记录](00_预检证据/change-control-governance.md#cr-020启动器可靠性与性能修复规划)。普通函数拆分、可逆工具修正和不改合同的实现由执行者判断，无需逐步审批。

## 最终文档复盘

已逐份复盘README、manifest、总控、新任务书、实测矩阵、Goal、本文件和CR-020，以及旧Goal当前入口声明；完成只读独立审查与增量复核。发现并修正了实测范围过大、资源/指标/路径不一致、探针映射遗漏、Core入口名、其他pending守护、总期限和取消竞争7类问题；增量复核未发现新的硬冲突。

规划时静态检查核对9份新改文档、155个本地链接、7个阶段、42个唯一且全部not-run的CASE、6个planned探针，`errors=[]`；旧正式报告SHA未改变、产品目录无变更。检查记录保存在`E:/OpenSourceTeamWork/workspace/tools/launcher-reliability-20261102/planning/`的`document-validation-01.json`及收尾后的`document-validation-02.json`，只证明文档结构与一致性。

**文档已获执行授权；RP-EXIT-R0通过，进入R1受控修复。** GATE-11六探针均有原件，不授产品通过；后续每阶段仍须通过其开工/退出门。当前存在的产品P1待R1修复，不能因为文档复盘完成而标为已关闭或全局验收通过。

当前唯一下一动作：执行R1精确恢复修复及Core入口正反例；真实GUI恢复前完成精确旧根预备备份，随后按阶段门继续R2–R6。
