# CR-020：启动器可靠性与性能修复长程任务书

## 计划元数据

- Plan ID：`desktop-launcher-reliability-20261102`；父计划：`desktop-launcher-full-20261028`；变更：CR-020。
- Version：`0.15-executing`（R1恢复阶段签收、Anima停服full单配置已验快照）；Last updated：2026-11-03 12:35（Asia/Shanghai）。
- Canonical progress file：[既有唯一总控](00_总控目标索引.md)。本任务书保存R0–R6专项细节，总控保存总体状态；冲突时先核最新用户指令和实际证据，再同步两者，不另建竞争总控。
- Related handoff file：`E:/OpenSourceTeamWork/workspace/tools/launcher-reliability-20261102/planning/execution-update-20261103T042854Z/continuation.md`；保留旧失败及执行身份，不重开结束attempt。
- Current branch：`feat/desktop-launcher`；工作副本：`E:/OpenSourceTeamWork/workspace/branches/dev`。
- Current active phase：R2 可取消引擎检查任务（in progress）；R0/R1 done，R3必要前置in progress，R4–R6 pending。RP-EXIT-R1已签，R2–R4门未签；Execution readiness：`executing`，整个Goal未完成。
- 模式：既有Full体系的`plan system update`，采用合并文档，保留目标、阶段、开工清单、证据、完成门、最小探针、Goal、复盘及manifest。方法：缺陷修复＋BDD用户行为＋合同/差分测试＋真实沙盒证据。
- 配套：[针对性实测矩阵](reliability-performance-20261102-acceptance.md)、[资料复盘与开工门](reliability-performance-20261102-readiness.md)、[Goal提示词](03_goal提示词/启动器可靠性与性能修复_20261102_goal提示词.md)。

本任务书与配套Goal是既有CR-020的执行合同及当前续接入口。用户最新active Goal继续授权受控实现、必要合同、候选构建与原生实测；v0.9“仅文档、不运行”限定仅属于当时审阅批次，不再约束当前执行。本文档整理本身不改变工具Goal状态，也不代表全部任务完成。性能表仍是验收目标。

### 当前执行快照

核对时间：2026-11-03 12:35（Asia/Shanghai）。本v0.15替代v0.14现在时；12:25八原稿已备份。R0/R1 done，RP-EXIT-R1按正式恢复缺陷及保护范围签收；R2可取消引擎检查任务active（in progress），R3必要前置in progress，R4–R6 pending。candidate05下native04真实UI取消留下合法committing事务，新进程正式GUI recover04 succeeded、intent committed并绑定g1208b56f57f3e752，正式IPC重复恢复也succeeded。两原生suite/host均pass，资料/控制保护及自然Job/CDP回收通过。当前full Rust344pass/0fail/15ignored，60份Rust/Cargo输入与当前及candidate05一致。R1-04按参数证据pass-with-boundary，不夸全GUI矩阵；R1-06最终CAS合同及实际命中原生window通过，分块取消/性能时限仍属R2/R4，未外推。Anima Fast停服full单配置实测suite/host通过，首反馈1.9ms、任务ID可见上界17.1ms、完整检查保守285776.1982–285935.7808ms，worker/readers回收及控制/资料保护通过；仅授该配置，取消与余三引擎未验。旧native02/03失败保留，recover03禁止。R2–R4门未签，嵌套Operation取消盲区仍待修。R1阶段Git保存待做，当前增量未提交/未push；整个专项/既有active Goal尚未完成。

| 范围 | 已有实际证据 | 尚未证明或待办 |
| --- | --- | --- |
| R0 | RP-EXIT-R0已签，HEAD `9135fad8259cdf8b41efdd79ad37ca0b0b739d83`为已保存基线 | 当前增量待Root精准保存R1阶段基线，R2–R4门未签 |
| R1正式主恢复 | 旧native-recovery-01正式GUI主重建恢复证据保持原包身份；当前candidate05的native04合法回退取消→新进程GUI recover→正式IPC重复恢复通过；audit02核两项旧缺口齐备，completion02签RP-EXIT-R1 | R1仅正式恢复P1/保护通过；性能/全链取消与最终同包R5仍待验 |
| R1终态回退 | `terminal-rollback-03`长路径原子替换os error 3、0通过/1失败、exit101保留；`terminal-rollback-04`短独立根单合同1/1、exit0及Job自然排空，证明Core终态控制夹具中new registry重复幂等、old registry拒绝零写及资料/其他实例保护。`healthy_environment_claimed=false`、`committing_recovery_claimed=false`，不授可信环境健康、原生回退或真实committing恢复。 | 原失败02缺保护SHA及03长路径原件均保留；04不使R1整行通过 |
| Rust编译与宿主 | `R2/rust-integration-01/compile-03` locked/offline no-run实际编译exit0、6.85秒；Job active_before_cleanup=1、after=0、job_termination_requested=true、job_drained=true，属显式受控清理成功，不能称自然排空。compile-02旧回收失败保留。 | 新Rust修订需对应必要定向合同；不得将受控清理写成自然排空 |
| R2已有模块 | `scan-01`10、`bridge-01`13（7显式进程案）、`tasks-01`33，Python`query-01`30及`legacy-02`13均为旧执行身份通过；shared/32MiB读取硬限已有合同 | 不因文档更新重复旧全套；最新7/7与19/19见下方对应执行身份，生产IPC/大引擎/端到端时限未验 |
| R2/R3前端 | 前端33/33＝原27＋4项取消失败store＋2项实际Activity SFC合同，真实Vue/受控IPC/时钟/内存renderer；非原生。`R3/cancel-retry-01/after-01`源稳定、exit0及Job自然排空；`build-02` npm/vue-tsc/vite exit0、26源/配置稳定、9产物SHA、Job自然排空。外层Python在结果保存/回收后打印U+2713到GBK终端失败exit1，`evidence-verification-01.json`独立核验通过；未为打印错误重构建。 | 原生可见反馈、主/引擎准备窗、键盘/归焦/确认/取消时延仍待验；33项不授原生pass |
| 历史build-02前端身份 | App `57c9fcf34b4c00393c707fcac6942d9be2fbcd9ed56c46203b38ed9a5f1598ce`；EnginePanel `b744c769a7b3ef6fcbf3ed57f28299108de46fc94d1584693cb3a63ce826a863`；store `39063cfba43aa691ffac5ebd545468f37ad822a80faf804af737687943406683`；Activity `03439c8f69de0c239f382acf2e1278afc27605a2224aebcad29544be2dd16a04`；i18n `bbc9dd027826a22f8e49bc2fc471fbd1adb43a2be94fce2ccf5b28c0a4d83b0b` | App/Engine维持cancel-reopen-01身份；后三者修复取消IPC失败丢意图/pending按钮不可取消，备份/审查在`R3/cancel-retry-01` |
| R4必要基础修订 | `R2/rust-integration-01/r4-scan-01` 8/8、exit0、17.95秒，执行源码稳定；Job active1→0、termination_requested=true，显式受控清理成功，非自然排空。`r1-core-regression-05` 12pass/1专属真实lease子进程helper ignored（父案实际调用并通过）、exit0、7.37秒、Job自然0→0。 | 仅授原身份扫描/保护与Core回归合同；最新取消窗口7/7见下方，性能/原生及门后短收尾未验，不能外推整段时限或完成门 |
| R1最新取消/提交竞争修订 | final-cancel-red-01原件保留；final-cancel-green-01的7/7、exit0、源稳定，测试0.19秒/宿主33053.5603ms；Job受控清理1→0、termination_requested=true、drained=true，全部句柄关闭 | 只授三态CAS取消/提交竞争、原子写及Core收口合同；不授全部门后工作≤10秒、取消时延或真实committing恢复 |
| R4最新合计预算修订 | combined-budget-red-01三案RED保留；combined-budget-green-01的19/19、exit0、源稳定，测试0.53秒/宿主1011.9796ms；Job自然0→0、termination_requested=false、drained=true | 原8＋新增11合同仅授两层合计资源保护模块；性能/原生未验，4GiB/50,000节点与完整内容闭包不变 |
| 当前候选及工具 | candidate05冻结173产品/15工具，build05 exit0、80578.4374ms、Job受控1→0；native04 cancel/recover两suite/host真实通过，均自然回收，full344的60份Rust/Cargo源与当前/candidate05一致 | R1门已签；R2 query-anima-fast-full-01真实运行中，R2/R3其他原生与R4性能未签；旧native03失败及recover03禁止保留 |

本次v0.14 12:25八原稿备份、R1签收增量校验与续接摘要位于`E:/OpenSourceTeamWork/workspace/tools/launcher-reliability-20261102/planning/execution-update-20261103T042854Z/`；旧planning及失败原件只读保留。7阶段、42CASE、4完整＋4取消、阈值/资源/旧8失败行及52单元保持。

## 目标

修复CR-019暴露的实例恢复自阻挡、引擎检查长期无反馈、重装确认迟迟不出现，以及维护/启动过慢问题。在保留完整性、资料保护和真实占用限制的前提下，让检查可跟踪、可取消，修复与重建时间有分阶段测量和实际改善，并在同一个最终候选包中自动完成针对性沙盒复验。用户无需手动补测，不启动真实训练。

### 当前事实基线

| 项目 | 已核实基线与含义 |
| --- | --- |
| Git | 规划前本地及远端为`91e3d2e62a5b31865f8c56a0f321418aa887ecd3`；最后产品提交`4e1b4cc78939e8b906252b27dcc20692ad347a08`，其后仅验收文档提交，主要问题尚未修复 |
| 当前续接现场 | HEAD为R0基线`9135fad8259cdf8b41efdd79ad37ca0b0b739d83`；R1–R4必要前置增量未提交。最新层级结果/源码身份及未验项以本文件唯一“当前执行快照”为准，R1–R4均未签 |
| 最终旧候选 | FINAL06；EXE SHA256 `11804c053d8667b1c9b91512d72055481aeb27d58be2ac32d181ede42413cbca`；固定训练器源码`4e68df240c63ab7cf2156ea7fafabf18df4671e8` |
| 旧验收 | 227行：193通过、24部分通过、8失败、1受阻、1待复核；52引擎单元：3通过、8部分通过、8失败、22受阻、1未测、10待复核。52是展开视图，不与227相加 |
| 旧证据 | [正式报告](full-acceptance-20261101-report.md)；353张原图、329条精确proof；`acceptance_complete=false`，文件完整性通过不代表业务通过 |
| 原P1症状 | `core.rs`遍历其他release时调用全根`gui_rebuild::assert_ready`，撞上目标自己的pending；错误发生在任务持久化前，不能只修底层recover函数。R1修复已进入实际运行的release EXE，正式GUI重建恢复通过；合法回退恢复正分支仍缺证明 |
| 查询 | 查询任务/桥/扫描观察/共享store已落工作树；Rust10＋13＋33、Python30＋13为原身份模块通过；前端33/33及build-02通过，生产IPC/GUI/大引擎与性能仍待验 |
| 超时 | 三案900秒是验收器等待门；worker已有1800秒超时及Job回收，不覆盖此前所有准备阶段；不得把“加长前端等待”当本轮修复 |
| 性能 | 源码修复54分41.498秒、重建85分27.836秒、一次启动156930毫秒均为历史真实耗时。已证重复扫描路径，尚无完整阶段归因；不可据此承诺已实现某个倍速 |
| 未操作入口 | AI Toolkit和Anima Fast各5个具体按钮从未操作；最后三案共15个后序目标入口未进入。Kohya有历史操作，但候选适用性仍待复核 |

### 目标—验收映射

| 目标 | 完成后的业务行为 | 施工阶段 | 必须得到的证明 |
| --- | --- | --- | --- |
| T1 精确恢复 | 能从正式按钮恢复自身未完成事务；错事务和其他真实冲突仍拒绝 | R1、R5 | Core入口回归＋真实多版本故障恢复，任务持久化、绑定、资料及终态证明 |
| T2 可观察检查 | 完整检查返回任务ID，跨页可观察、可取消、同目标去重，状态含义明确 | R2、R5 | 跨Rust/Python协议回归＋四引擎真实检查/取消＋旧10按钮补测 |
| T3 重装反馈 | 点击即显示准备窗口，计划就绪才允许确认；失败或取消都有明确结果 | R3、R5 | 慢预览、错误、过期计划、取消与原生确认/焦点结果 |
| T4 可测量提速 | 降低重复读取，维护/启动满足下述目标；完整性与保护合同不弱化 | R0、R4、R5 | 阶段计时、同夹具差分、真实耗时、损坏与非目标保护回归 |
| T5 可追溯交付 | 同一最终包完成本专项必测，更新旧227/52清单的精确条目及残余缺口 | R5、R6 | 新旧用例映射、原图/JSON/SHA、回收记录、阶段push与最终报告 |

### 用户审阅总览：问题、方案与针对性实测

| 问题 | 优化方案与用户可见结果 | 必须执行的实测 | 完成判断 |
| --- | --- | --- | --- |
| 恢复未完成变更被自己的事务拦住 | 按根目录、版本、事务ID及备份严格识别，只放行当前合法恢复；其他冲突继续解释原因 | 真实多版本故障现场点击恢复→确认→重开核绑定；错误事务、其他pending、真实占用拒绝且零越权写 | CASE-R1-01…06；正式任务/receipt/终态一致，原资料保持 |
| 引擎检查长时间没有反馈 | 立即显示检查中，后台发布阶段/进度；切页可追踪，可显式取消；重复点击共用同一检查 | 四引擎各1次完整检查、1次取消；切页/重复点击/过期结果、准备与大文件扫描中取消、真实worker异常回收 | CASE-R2-01…12、R5-02；≤1秒受理，≤300秒完整检查，取消分段指标通过 |
| 重新安装迟迟没有确认窗口 | 点击即显示“正在准备”弹窗；计划就绪才启用确认，错误原位提示，取消不改安装 | 旧多包缺损场景、慢预览、失败、取消后晚到结果、切版本后确认；核亚克力风格及键盘焦点 | CASE-R3-01…05；≤300毫秒首反馈，计划身份与占用复核通过 |
| 修复、重建、启动慢，按钮迟刷新 | 先计量定位再合并同一安全阶段的重复扫描；ready/stopped直接驱动按钮 | 同夹具前后扫描量/耗时；同大小mtime篡改仍检出；真实源码修复/重建；3次启停及HTTP/API/按钮计时 | CASE-R4-01…05；修复≤15分钟、重建≤25分钟、启动≤60秒、终态到按钮≤500毫秒 |
| 部分按钮被前序失败挡住，证据不足 | 原失败逐分支复验，补AI Toolkit/Anima Fast共10个遗漏按钮；保留每个引擎真实结果 | 四引擎各5类入口、小源码缺损修复与导入probe；受影响目标补安装，代表目标做独立重建；最终同包空根安装启停 | CASE-R5-01…07、R6-01…03；截图＋结构化断言＋进程回收，不以代表目标替其他目标授pass |

全部计划共42个CASE模板，按目标/故障点展开实际实例；不用模板数量冒充已执行次数。旧227行与52引擎单元用于追溯和保留未闭缺口，不要求无关历史通过项再全量重跑。

## 范围与约束

### 本轮包含

1. 上述四类产品问题及其共用的任务、取消、进度、检查结果和保护扫描路径；保持现有业务与亚克力视觉体系。
2. 旧8个失败行`APP-ENV-004 / ENV-MAIN-01 / ENV-MAIN-06 / GUI-LIFE-05 / ENG-01 / ENG-02 / ENG-04 / ENG-09`的逐分支映射、定位与针对性复验；共享父行不能用一个成功子分支整体覆盖。
3. 四引擎真实完整检查、只读取消、运行检查、单个可恢复源码缺损修复，以及重装计划/取消；AI Toolkit与Anima Fast各5个从未操作按钮必须实际触发。原13×4矩阵逐单元记录新事实。
4. 同一个最终包的新空根主程序安装、服务网页与API、停止/重新启动和关闭到托盘/退出回归；旧隔离根上的事务恢复和重型引擎维护另标复用根，不能冒充从零安装。
5. 不默认重跑227行所有历史无关通过项；R0须对所有未闭条目建立影响映射。相关fail/blocked/partial/pending必须补测，未受影响条目只继承原包/证据身份。新问题影响面扩大时补最短相关链。

普通用户入口继续保留一个“检查修复”主操作，重装等低频操作仍在高级选项。任务ID、单飞、容量、状态机和扫描阶段属于内部实现及日志证据；不增加要求用户理解的技术按钮，不改已固定的亚克力布局与侧栏交互。

### 固定边界

- 不开启训练、不加载大模型、不下载训练模型、不修改驱动；真实依赖导入不等于GPU或训练通过。
- 不恢复任何产品下载预算/额度/账本；本任务的测试资源限制只属于开发执行，不能出现在用户安装流程。
- 不清理或改写CR-019失败、旧EXE、冻结输入和证据包；新attempt、新输出目录，旧失败与新结果并列。
- 不以修改测试器、放宽900秒等待或略过SHA校验形成通过；不得把快照标为完整健康，不用跨操作mtime/size缓存代替完整校验。
- 网页服务运行时允许只读检查、计划预览和无冲突独立引擎安装；目标训练/占用/已有变更任务才限制该目标修改。主程序本体变更继续执行必要停服务规则。
- 不改用户已有安装、模型、资料、窗口和服务；只在新归属沙盒操作，仅回收自己持有的PID代次/Job/监听器。保留所有无关脏文件和untracked；不`reset/clean/add -A/force push`。
- 干净Windows、缺WebView2首装和GPU资源事实按原范围保留，本专项不伪称解决或重新执行已结案VM探针；不公共发布、不使用生产密钥、付费云或未授权服务器。

### 体验与性能目标（执行目标，尚非测得结果）

| 指标 | 计划验收目标 | 测量口径 |
| --- | --- | --- |
| 操作反馈/重装准备弹窗 | 点击后≤300毫秒出现状态或窗口 | 真实DOM动作到可见结果；轻操作至少3样本，逐样本列值，不以截图时间推断 |
| 完整检查受理 | ≤1秒返回任务ID和初始状态 | 从请求发出计时，不等待基础Python或环境全扫描；受理不代表检查通过 |
| 进度 | 活跃长阶段≤1秒发布一次观测或心跳 | 实际文件/字节/阶段与等待心跳分列；不伪造百分比，锁等待注明等待原因 |
| 取消 | ≤1秒确认已接受；可取消扫描≤5秒停止；自有worker/Job≤10秒回收 | 端到端请求到各终态分开计时；提交不可中断段必须真实标明，进入安全边界后收尾，不能提前显示已取消 |
| 单引擎完整检查 | 每个实际完整引擎≤300秒 | 单GUI、无并行重磁盘任务；完整SHA、缺损/多余文件检查保持 |
| 普通源码修复 | ≤15分钟 | 同等目标/保护树、固定归档、缓存状态与机器负载记录，含必要提交保护 |
| 新实例重建 | ≤25分钟 | 同类主程序实例，含验证和提交；下载冷/热分别计，不隐藏必要步骤 |
| 启动到可用 | ≤60秒；ready事件到网页按钮、停止到启动按钮≤500毫秒 | 正式启动前检查保留；HTML与`/api/version`语义200＋监听归属，后端日志成功不能替代UI结果 |

R0测量后保留基线和目标差距。目标无法满足时先定位、改进并报告真实结果；不得由执行者自行放宽或删除指标。若必须改变用户审核后的指标/范围，记录CR并按会话授权处理。本表不把相同硬件、负载或可达性能假设写成事实。

## 执行阶段

阶段稳定为R0→R1→R2→R3→R4→R5→R6。代码调研、协议设计和测试编写可分工；唯一集成者收口。全程只允许一个正式GUI验收会话，真实安装/完整扫描串行。每阶段完成必要验证、更新状态、一次精准commit/push并核远端后自动推进；执行授权到位后不重复请求阶段审批。

阶段签收顺序与开发依赖分开：R1真实恢复若暴露必须依赖R2/R4的分块取消或扫描基础改造，允许先做这些共用能力的只读诊断、小合同和最小代码修复，再回到同一R1完成门复测；不提前签R2/R4，不并发重案，不放宽R1安全、性能或总时限。这项依赖处理不增加实测轮次。

### R0 基线与测量

- 目的：确认当前现场与旧证据，将未知瓶颈变成可测量数据，先验证危险前提。
- 开工清单：执行授权已明确；Git/分支/脏文件/端口及自有根身份已核；历史证据只读；本轮资源剩余额度和磁盘余量已记录；暂无自有旧活案待收尾。
- 输出：`baseline.json`、`issue-map.json`、`resources.json`、阶段计时/文件数/实际读取字节设计、最小探针报告。旧227/52未闭项逐一标受影响与证据身份，不先授pass。
- 步骤：①核旧失败的精确root/release/instance/transaction与源码；②建立新标记根，必要时按正式安装或可验证的root恢复工序准备夹具，不复制带旧绝对路径的venv充新根；③先用小夹具复现Core自阻挡、JSON/进度协议、哈希取消、候选排除/所有权变化；④有界采样旧查询/扫描路径并加入阶段观测；⑤冻结前后对照方法、目标、最终用例映射。
- 验证：优先复用已有失败原件；新采样最多120秒一段，结束受控回收。不得为复现54/85分钟历史耗时无差别重跑两套重环境。小夹具不能当真实性能证据。
- 完成门`RP-EXIT-R0`：真实前置和资源可用、危险假设有小型证据、回归和计时可执行。若P1事务或扫描保护语义无法说明，保留失败并退回设计，不进入危险写入。
- 证据：`<run>/R0/`。失败处置：保存快照/原输出，不破坏旧失败；可继续与阻断无关的只读分析。

### R1 恢复自阻挡

- 目的：恢复自身事务，同时保持对其他事务与占用的限制。
- 开工清单：R0通过；目标事务及备份可精确验证；测试覆盖Core正式入口，而不只底层recover；基线用户资料与绑定可恢复。harness预算修订已核；此前两份原生会话均已结束，续接先复核终态与进程归属，不能再次运行旧脚本。
- 输出：Core/重建事务冲突判定修复、精确恢复上下文、拒绝/幂等回归。
- 步骤：①恢复前校验root、release、事务ID、类型、计划摘要与快照；②全根检查只豁免唯一目标事务；③保留同release其他pending、其他release、资料绑定/壳更新/基础Python/登记/真实锁限制；④正确持久化操作与失败状态，恢复执行仍完整验证；⑤使用原多版本committing场景走真实按钮“复验并恢复此事务→确认恢复”。
- 验证：匹配事务成功；错ID/错版本/错根/损坏快照/同名异事务拒绝；真实lease拒绝；重复恢复幂等；故障和取消后pending保留、资料及非目标绑定不变。关键拒绝用小夹具，成功链用真实候选。
- 历史v0.13剩余最小补验（当前由v0.15门回执替代，原断言保留）：继承已验主恢复/拒绝参数；历史terminal-rollback-02缺保护SHA、03长路径失败保留。code-tests-04“仅格式通过”属于旧快照：当前04单合同已证明Core终态控制夹具registry=new两次幂等、registry=old拒绝零写，r1-core-regression-05已12pass/1专属lease helper ignored；不无修改重复它们，也不将合成proof当可信健康或committing恢复。final-cancel-green-01的7/7原证据保留；短收尾与controlled修复已补扫描36/36、binding1/1及Rust全套344/0/15、Clippy/fmt通过，candidate04已冻结/构建。11:30原生02因预览目标显示fail而未confirm/cancel；Root先修App/bridge并以candidate05/newattempt03补正式0B回退：真实受控提交形成pending，重开恢复核committing→committed。旧native-rollback-01仅locator失败，不判回退执行失败；不手写pending或放大等待，无法安全中断则保留blocked。
- 增量断言：合法目标事务缺registry/profile/必要目录、错marker、终态绑定不一致、其他事务损坏仍须写前拒绝；不按release跳过全根保护。取消覆盖creating/building/validating、prepare_commit持久化前及finish切registry前，通过正式OperationManager.cancel验证写前不提交、合法pending与准确终态；原子写之后按实际提交结果收尾，不将成功改取消。候选实例扫描现已接入实际OperationManager CancelToken并在r4-scan-01的8项定向合同验证，资料逐块检查保留；QueryObserver合同仍只授查询作用域，不能替代修改操作。finish最后registration_revalidate、完整字节/语义复验与Core成功收口的CAS竞争已由当前模块/完整Rust验证；旧checkpoint和R4通过不独立证明该窗口，当前证明仍不外推整段原生时限。R1整链≤5秒/≤10秒仍须原生定向实测。
- harness时限门：host已注入实时`suite_budget_ms`，完成预检/CDP后多次核剩余时间，Node不超过1600秒并预留主动取消/回收；恢复确认前至少留60秒，可用预算不足60秒在写入前拒绝，1800秒总边界不扩大。41项及45项两组工具合同和文件封存由`harness-review-01.json`核对；只证明工具合同。同步OS I/O仍可能阻塞，缺少独立全局watchdog的边界必须保留：后续补保护时只针对自有进程，按实际提交/恢复协议收尾，不能盲杀或把预算计算当硬时限已全面验证。
- 完成门`RP-EXIT-R1`：正式入口通过且P1关闭，磁盘任务、registry/binding、receipt、恢复终态有证据。不能删除guard或先清pending凑通过。
- 证据：`<run>/R1/`。失败处置：保留事务与现场，修复后新attempt；未关闭P1禁止签修复完成或进入依赖它的重建验收。

### R2 可取消引擎检查任务

- 目的：完整检查可见、可跟踪、可取消、可复用同一在途查询。
- 开工清单：R1通过；先核现有OperationManager的持锁/写入语义，不把只读检查误接成全局变更锁；Rust/Python协议和旧接口兼容策略明确。
- 输出：只读检查任务类型/DTO、分阶段进度、总期限与CancelToken贯通、单飞/订阅管理、前端任务状态联动、双语文字。
- 外部候选与当前产品：candidate03独立32合同只属历史身份；当前接入已落未提交工作树。scan10/bridge13/tasks33原模块证据保留，最新R4扫描8/8、Core回归12pass/1专属helper ignored及前端33/33/build-02通过对应身份验证。compile-02旧回收失败保留；compile-03及R4编译Job受控清理1→0、Core及前端自然0→0分列，不能用旧“未编译”要求无修改重跑。
- 已有微型验证与缺口：Rust10＋13＋33、Python30＋13原证据保留；shared/32MiB已有合同。当前前端33/33及唯一build-02通过，取消IPC未送达/响应丢失/权威成功/显式重试及Activity pending按钮已有隔离合同；生产IPC/原生整链、端到端取消/回收时延及大引擎性能待验。full/files_only均完整内容闭包、不运行import/GPU。
- 本阶段剩余工作：保留旧模块及旧R4扫描/Core回归的原身份通过证据；保留当前R1提交门7/7及R4合计MAX_TREE/50k限制19/19执行身份、已冻结rollback02工具/candidate03与build03构建结果；短收尾及controlled扫描修复已通过当前模块/全套验证并进入candidate04；原生02在预览目标显示失败、未confirm/cancel；修复App/bridge后candidate05/newattempt03补生产IPC/原生。store按完整target隔离、组件同root/release/engine取消收尾期阻止重装绕inspection；取消失败保留意图、显式重试单飞、权威终态释放。Catalog验签/同步OS I/O边界仍需按实际作用域核对，不能由R4局部通过外推全链时限；既有CASE及大型轮次不增加。
- 容量合同（待验证实现初值）：resolver入口32、已解析不同身份在途4、重扫描执行槽1；四个不同身份占满后，重复请求仍可进入有界解析并加入已有任务，新唯一目标返回结构化busy。终态历史64、alias128、事件128/任务、订阅32/任务且全局256、结果4MiB/任务且总存储16MiB；活动task/alias不得为历史腾位被淘汰，无可淘汰项则有界拒绝。身份解析失败必须保留可收口句柄；child wait、stdin关闭、stdout/stderr reader实际join及Job active0分别证明。数值只用于内部资源保护，不成为产品下载额度；以CASE-R2-02/10/11参数化小合同验证，不增加重装轮次。
- 步骤：①快速概况仅展示安装/绑定/代次/pending/最近校验及占用，明确“尚未重新校验”；②受理后立即返回任务ID，完整工作异步执行；③总期限从请求入口开始，涵盖排队、基础Python核验、工具锁/缓存发布、worker输入输出/解析及回收；④哈希文件及分块读取中检查取消、限频发布进度，stdout结构化进度与最终JSON严格分帧，stderr为脱敏日志，管道读取与缓冲须有界；⑤同根/release/engine/action/检查范围/instance/generation/配方身份在后台单飞，改变身份使旧结果失效；⑥取消为任务级显式操作，关页/关闭订阅不隐式取消共享任务，最后一个订阅离开也不自动杀任务，界面显示影响范围；⑦取消与成功竞争由同一权威终态线性化，实际已成功返回already-terminal，不将完成任务改成cancelled；只读取消无安装提交阶段，修改操作另依R1原子提交合同。跨页重连、历史/终态、worker异常/超时/无进度均有状态，ready结果不能覆盖新dirty/占用；⑧主页面及日志复用同一状态源。
- 验证：任务ID及时返回、四引擎真实完整检查、同目标连点和多视图订阅不多开worker、切页及新generation旧结果拒绝、准备阶段和哈希大文件中取消、协议坏行/EOF/断连、主服务运行时只读及无冲突目标允许。已有`spawn_blocking`、避开Engine mutex和worker回收须保留，不重复当新成果。
- 完成门`RP-EXIT-R2`：任务/取消/超时合同回归通过，至少一个真实大引擎满足查询目标及可取消行为；其余四引擎矩阵在R5集中收口。任务终态与安装完整性、运行占用分别展示。
- 证据：`<run>/R2/`。失败处置：只读失败不改dirty/generation/receipt/绑定；自身日志/任务记录和固定工具缓存写入须明确列白名单，不能宣称磁盘绝对零写入；查询终态等待worker回收后发布。

### R3 重装预览弹窗

- 目的：点击立即有反馈，计划生成不再阻挡确认窗出现。
- 开工清单：R2通过；预览使用可取消上下文；确认执行仍采用后端当前计划摘要和占用核验，UI提前展示不代表提前允许写入。
- 输出：准备中/可确认/受阻/错误/取消的亚克力弹窗状态机、焦点/Esc及中英文。App/Engine接线已由当前统一build-02覆盖，前端33/33含实际Activity SFC合同；原生准备窗/取消/确认/键盘/归焦仍未验。
- 步骤：①同步开准备窗；②异步读取历史和预览，展示真实阶段和必要信息；③只有ready且plan摘要有效时允许确认；④错误/受阻原位解释，不能悄悄跳到高级页；⑤关闭正在准备的弹窗或按Esc属于显式取消，停止整个共享预览任务，并提前显示影响范围、丢弃迟到结果；普通切页或退订不隐式取消；⑥目录、版本、实例或计划改变必须失效并重算，保持取消优先焦点、键盘限制和归焦。
- 验证：慢预览、失败、blocked、过期结果、双击、切目录及正常确认；主程序/引擎分别覆盖受理前关闭/Esc立即重开、取消IPC在途重开、plan_install/plan_repair复用、取消终态后重开，重装不能先绕去full inspection；取消中提示等待、不新建第二扫描/可确认计划。补取消未送达且后台running、后台已受理但响应丢失两类，保留意图、显式重试单飞、权威成功/取消收口。切页继续共享，切目标不误阻，旧取消失败不覆盖新页面。原多包损坏真实复测，确认前无变更、确认后只有目标操作。
- 完成门`RP-EXIT-R3`：满足反馈目标，真实计划确认/取消均通过，异常不静默、不绕过backend确认。完成施工快检后继续R4，不要求用户手验。
- 证据：`<run>/R3/`。失败处置：不替换生产invoke为mock来证明原生通过；保留harness与产品失败分别归因。

### R4 扫描与启停性能

- 目的：减少可证明的重复工作，保持保护能力，并缩短维护和启动等待。
- 开工清单：R0测量与R1–R3合同通过；优化前后可复用同一冻结夹具/缓存/负载记录；不在重型真实案中并发第二套扫描。
- 输出：分阶段耗时/扫描计数/增量I/O、扫描结果复用与失效合同、源码保护范围改进、候选重建减少重复读取、启停状态与取消响应修复。
- 步骤：①按测量选择真实耗时段；②同一持锁操作、同一不可变观察阶段合并枚举/哈希；写入、运行探针或身份变化后不得盲用旧结果；③源码修复排除独立引擎实体前复用严格所有权/锁/receipt机制，并证明变更写路径被约束，保留控制记录与未知目录检查，不仅凭`t...`名字排除；控制摘要不证明整个引擎字节未变，不能据此宣称全树前后SHA相同，无法证明等价保护先保留完整扫描；④保留其他GUI、资料、Python、源码、候选及提交前必要保护，防扫描时外部变更；⑤明确运行探针是否产生允许缓存，未授权新文件仍拒；⑥启动完整检查由可观察阶段执行，ready和stopped事件直接驱动按钮，不等待无关全量inspect，实际监听/HTML/API通过后才ready。
- 验证：新旧保护判定小夹具差分；同大小/mtime内容替换、额外文件/链接/所有权receipt变化、扫描中改写、探针前后变化拒绝；真实源码修复、主重建、启动/停止均计时并核资料/非目标保持。阶段进度可见不算性能达标。
- 完成门`RP-EXIT-R4`：保护与拒绝语义不弱化；小夹具差分及真实关键路径通过，达到目标或明确记录未达。性能指标未达不得标done并跳过，继续有依据优化；确需调整审核指标按CR处理。
- 证据：`<run>/R4/`。失败处置：先保留前后计时/输入/原因，再做最小修复；不提高资源预算或用无限并行掩盖耗时。

#### R4嵌套取消与阶段计量（待实现/实测）

新发现的R4嵌套取消盲区，尚未修复/实测：gui_registration_integrity普通Python verify、gui_entry_probe原/副本source verify、runtime_view递归复制、Operation控制记录读取（scan_observation目前仅Query TLS）、engine_namespaces控制读取/摘要、instances内存树语义及probe静态文件读取，逐项贯通外层Operation token，并在真实首块/首节点屏障触发取消；清理阶段不中断。计量分plan、before-observe、可信闭包、validator、复制、副本校验、entry probe、after-observe、最终门。暂不删除execute→finish第二validator/probe，before/after完整扫描保留；并入现有CASE-R1-06/R2-07/R2-09/R4-05参数，不新增CASE或重型轮次。这组全链指标继续阻断R4/R5和最终交付。

R1业务门不覆盖这些指标；CASE-R1-06时延维度及CASE-R2-04/11、R4-01/02/03/05继续取证，未满足阻断R2/R4/R5与最终交付。原≤5秒/≤10秒阈值不变。

### R5 最终同包定向沙盒回归

- 目的：用可核对的最终候选解决原失败和遗漏，而非只交编译通过。
- 开工清单：R1–R4通过；最终commit/训练器源码/worker/catalog/recipe与EXE可追溯；新空根及复用故障根分列；唯一GUI/归属/资源/回收方案已核。
- 输出：最终包、空根安装与启停结果、恢复/弹窗/四引擎矩阵、旧8失败与10未操作入口补验、资料差异及回收证据。
- 固定实测量：四引擎各1次完整检查＋1次取消，共4完整＋4取消。Kohya/AI Toolkit在网页服务运行时完整检查，Anima Fast/DiffSynth在停服时完整检查；各目标在另一个服务状态执行取消用例，不再追加4次完整扫描。每个目标的5类入口和小源码修复/probe分别留证，代表目标不替其他目标授pass。
- 步骤：①冻结新候选，记录EXE和实际分发文件SHA；②新空根经正式按钮安装主程序、启动、打开系统浏览器核HTML/API、停止、重开；③原ENG-01安装UI失败目标AI Toolkit/DiffSynth在新自有目标根补正式安装收尾，其余引擎复用经核身份的安装根；四引擎串行完整检查、5类目标入口、probe及小源码缺损修复，独立重建取至少一个受影响代表目标；④真实恢复和多包重装场景、取消/过期/占用/独立目标并行允许分支；⑤合并测量主修复/重建/启动性能，旧同包证据按影响分析保留，不替代新改路径；⑥整理精确失败行/变体/引擎映射并核用户资料原文件集合。
- 验证：详配套矩阵。重装预览/取消不能算重装执行成功，正式主重建至少一次；独立引擎新实例重建的成功分支用受影响最少目标代表，未重跑的目标保持具体证据边界。正常运行更新缓存与原资料保护分列，保留旧全文件集合比较fail，不能全局忽略config新文件。
- 完成门`RP-EXIT-R5`：本专项必测全部实际通过，8失败行的相关原分支有新结果、10按钮真实操作、四引擎完整检查及取消可用、关键资料/绑定/进程保护与性能目标通过。未到、blocked、pending不得凑绿；未受影响历史缺口仍按原状态保留。
- 证据：`<run>/R5/`。失败处置：自主诊断/最小修复/重建，新的EXE身份触发受影响链补测，不能混用旧新包为“同包全通过”。存在未闭P1不发布可交付结论。

### R6 交付

- 目的：交付可使用的修复包、可审查的新结果与稳定开发基线。
- 开工清单：R5通过；无本轮自有活动任务；关键原图/原始报告已收集，逐项新旧映射可追溯。
- 输出：一份最终报告、一份机器矩阵、可离线打开的截图索引、资源/清理摘要、EXE/安装器/便携包SHA和各阶段远端保存回执。
- 步骤：①收口新用例与旧227/52汇总，分别写`repair_campaign_complete`与全局`acceptance_complete`，不得因专项完成自动将全局置true；②记录残余partial/pending/不可达/干净OS边界，不将旧包待复核自动继承通过；③仅将可分发代码/脱敏小索引进Git，截图及重资产在外部证据；④图集实际打开、失败筛选/原图加载、包内外完整性复核各按需要一次；⑤退出唯一GUI、收回自有Job/worker/listener，保留用户窗口/服务；⑥精准push并核远端完整SHA。
- 验证：文档/JSON/实际截图数量与SHA相符，所有结果可追溯当前真实包；正常入口不带调试参数。安装状态不代表训练通过。
- 完成门`RP-EXIT-R6`：R0–R5及本阶段全部通过，阶段基线保存与最终交付齐备才可标本专项complete。任何必测fail/not-run/blocked均为incomplete，不让用户代验后再称完成。
- 证据：`<run>/R6/`。失败处置：证据包工具错误先修工具、保留原失败；不能改业务状态消除验包错误；远端保存失败不得虚报push。

## 每阶段开工、完成和失败共用清单

1. 读本阶段及配套矩阵对应CASE，核上一阶段完成门、当前用户指令、分支/工作树、代码/EXE身份、已有活动任务。
2. 核本阶段证据目录不碰撞、沙盒绝对路径和归属、磁盘/累计资源剩余、需要恢复的fixture备份、精确进程回收能力；未满足先写preflight failure，停止有风险动作。
3. 执行本阶段列出的最小验证；UI/IPC数据结构修改做`npm run build`，Rust改动做`cargo fmt --check`与受影响`cargo test`，共享操作/恢复变更在最终候选前跑完整Rust回归及严格Clippy。Python改动用已核匹配版本运行受影响`mikazuki/launcher/tests`，不使用宿主缺依赖失败掩盖产品结论。
4. 真实UI脚本复用旧OwnedNative/CDP/UIA能力但先审过期locator、root、EXE和任务归属；只能观察生产IPC结果，不能以mock替代实测。快检按影响面，不每小改动铺全套六类测试。
5. 完成记录必须含`phase / covered_case_ids / changed_files / validation / failures / residual_risks / source_commit / exe_sha256 / evidence / next_action`；模板复用既有[完成门](00_预检证据/stage-completion-gate-template.md)与[失败报告](00_预检证据/failure-report-template.md)。本轮新记录在外部根，旧模板不倒填。
6. 失败先保原件、区分产品/控制器/前置、修最小影响并补验；不设置“失败两次即停止”等内部审批门。真实授权不足、不可隔离资料风险、硬资源不足时说明具体来源，保留未完成状态；独立无风险工作可以继续。
7. 每阶段一次精确commit/普通push/远端核对，不代码/文档双重循环提交；GitHub网络逐命令代理`http://127.0.0.1:11809`，不改全局配置。不得夹带自然语言标注、Agent等无关文档。

## 决策记录

- 已验证事实：FINAL06/CR-019及已复现RED原件不改；真实主恢复、终态回退04控制合同、旧模块及前端33/33/build-02保留各自身份。短提交收尾及controlled扫描修复已完成，precommit扫描36/36、binding1/1、完整Rust344pass/0fail/15ignored、Clippy02/fmt01通过且执行源稳定；Rust全套Job受控1→0，Clippy自然0→0。candidate04冻结173/15并构建成功83063.3ms，仅授构建身份。11:30快照：原生02 fail；select-root/history通过，正式预览已ready，但目标实例字段未正确显示，断言失败时尚未confirm/cancel。suite资料保护true；host node_exit1，产品graceful exit0、job_drained=true、job_close_cleanup_required=false、CDP reclaimed=true；post-close完整操作摘要仍有unknown，不能授整体验收通过。Root定位App读取plan.old_binding而回退JSON使用plan.target_binding，bridge类型缺target_binding；此UI失败不解锁recover，R1–R4门均未签。full-rust01的socket WouldBlock测试helper失败、clippy01失败及源漂移单列保留，均非UI失败；旧compile-02回收、rollback03长路径和外层GBK打印失败仍保留。
- 当前假设：拟定性能目标在当前机器有实现空间，需R2–R5真实结果验证。R0原型仅证明协议、取消和单飞方案可行；OperationManager持久化要求WorkspaceMutation，不直接复用为只读合同，R2采用独立查询管理器，接口依据本run R0/query-task-design.md。
- 固定决策：一次唯一总控；R0–R6不随意改名；不真实训练；保完整性与用户资料；同目标冲突控制；一GUI及重操作串行；阶段push；失败证据保留；专项与全局完成分开。
- 待解问题：三案慢查询的阶段占比、85分钟主重建的主导耗时、普通重装原未出窗的具体返回状态，以及历史未计资源/峰值。R2接口设计已落盘；新增重下载0、E本run≤200MiB、F新增≤80GiB并逐重案核上界。未知量保持unknown，由对应阶段实测解决，不先要求用户另找机器。

## 关键制品、环境与资源

- 关键代码：`desktop-launcher/src-tauri/src/{core,engine_query_runtime,query_tasks,query_ipc,engine_bridge_query,engine_bridge_query_tests,scan_observation,managed_child,gui_rebuild,gui_binding_switch,instances,python_integrity,source_integrity,main}.rs`；`desktop-launcher/src/{App,EnginePanel,LogPanel,MainReinstallDialog,EngineQueryActivity}.vue`、`engine-query.ts`、`i18n.ts`；`mikazuki/launcher/{control,runtime,worker}.py`及查询测试。当前执行源SHA在precommit-scan-01/verification-summary-01.json及candidate-freeze-04中按执行身份记录；本轮before-manifest只冻结8份文档，未改产品源。
- 历史证据根：`E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101`；历史独立根：`F:/NextTrainerLauncherSandbox/full-acceptance-20261101`。只读引用旧原件，改故障夹具前必须新备份并记录身份。
- 当前新证据根：`E:/OpenSourceTeamWork/workspace/tools/launcher-reliability-20261102/run-20261102T130200Z/R0…R6/`；新沙盒：`F:/NextTrainerLauncherSandbox/reliability-20261102/run-20261102T130200Z/`。两根创建前已核无碰撞，均有独立归属标记；已完成小探针及一次空根原生导航采集，不是安装或产品恢复验收完成。
- 资源：沿用原计划累计网络≤200GiB、F峰值≤300GiB且余≥100GiB、E新增≤5GiB且余≥20GiB；历史未计余额`unknown`，R0已完成可核账本核实，不把unknown当无限。专项优先复用固定SHA原始归档；R0核账后进一步收紧为新增重下载0、F增量≤80GiB、E本run≤200MiB（测得指定旧/新证据根约4.694GiB，原5GiB名义余约313MiB），均受原硬边界约束；未计历史与峰值继续unknown，每次重案另核当前根、缓存和暂存/备份上界，不能静默扩大。
- 统计口径：200MiB统计本run的E盘证据根`E:/OpenSourceTeamWork/workspace/tools/launcher-reliability-20261102/run-20261102T130200Z/`；规划修订原件在同父目录`planning/`分列计量，并计入原E新增/余量检查。仓库Cargo/npm构建产物另列磁盘增量与余量，不能假称没有占盘。冻结R0审计中初始20GiB/1GiB上限只作历史，不回写原件、不据此扩大当前限制。缺少固定SHA缓存时先记录该案前置不足，不能暗中新下载。以上均为开发资源治理，不是产品额度功能。
- 时限：小探针每案≤120秒；轻UI快案≤10分钟；单引擎完整检查目标300秒、外部保护≤360秒含回收；源码修复单案保护≤20分钟、安装/实例重建/变更恢复≤30分钟含回收；每个串行测试组≤2小时。耗时校验放在可取消阶段，原子提交收尾设计≤10秒；超过收尾或外部门仍未结束即记fail/needs-recovery，停止新增操作，按已验证持久恢复协议收尾，尚不能证明安全终止则保留现场记blocked，不无限等待或盲杀。终止仅本轮自有进程，保留pending和原件。时限从含准备的请求入口计，产品总期限与外部保护门分列；错误/timeout保持fail。R0抽样不重复完整旧85分钟重建。
- 步数：每CASE只执行矩阵规定动作；故障一次只改一个精确备份文件。旧/新小夹具对照各一遍，重型真实成功案各一次；失败后依据新修改补验，不能为凑统计反复全量跑。
- 清理：先正常取消/退出再核进程代次、Job和端口；只处理归属明确的临时文件。保留旧失败、新成功、唯一截图/日志、SHA/任务终态；不删除原树或跟随链接清理。证据对日志脱敏，Git不含模型、venv、缓存、凭据、真实资料或大日志。

### 历史v0.13集成验证入口（当前由顶部v0.14替代）

1. R1最新合同：`R2/rust-integration-01/final-cancel-green-01`的7/7、exit0、源稳定，Job受控1→0。真实OperationManager已覆盖取消先赢、提交先赢、重复取消、原子写I/O失败、无registry写入的Core收口与query取消兼容；修前RED保留。CASE-R1-06仍partial，合同不证明全部门后工作都满足短收尾。
2. R4最新合同：`R2/rust-integration-01/combined-budget-green-01`的19/19、exit0、源稳定，Job自然0→0。boundary用本次非目标实际SHA树统计＋候选metadata预检；正式SHA/preservation用fresh非目标metadata统计＋候选实际读取余量；validate前后observe各用本次非目标实际SHA统计，不跨probe。根节点/空目录计入，checked_add合计、增长最多超读1字节，原4GiB/50,000节点不变；metadata不授内容完整性，CASE-R4-05仅模块partial。
3. 当前模块与候选身份：`R1/precommit-scan-01/verification-summary-01.json`汇总precommit扫描36/36、binding1/1、严格Clippy02/fmt01、完整Rust344pass/0fail/15ignored；均exit0、执行源稳定。Rust全套Job受控1→0、Clippy自然0→0。full-rust01的socket非阻塞helper失败及clippy01的5项lint失败/执行源漂移保留，非UI失败；修后不删原件。candidate-freeze-04冻结173产品/15工具，source-inputs SHA `24c6a6743c3e3048b8fe7a7b80cba6e8e6ae620c94a9179bd5141077198c0afb`、tool-inputs SHA `1c36f2cd08429cfe4423bb20aeb84053f88c21b60f25cfa1ce922edd83aeba26`。
4. 短收尾修复与原生边界：回退finish保留独立可信SHA/probe/registration_revalidate，最后assert_usable及语义复验移到CAS前，CAS后仅registry/intent写；source/Python/instances及安装/重建调用链接同Operation token，已有Query错误优先，完整SHA/未知文件拒绝/原合计预算不降。新增6＋8合同及扩展binding合同已包含在上述通过中，仅证明模块。11:30快照：原生02 fail；select-root/history通过，正式预览已ready，但目标实例字段未正确显示，断言失败时尚未confirm/cancel。suite资料保护true；host node_exit1，产品graceful exit0、job_drained=true、job_close_cleanup_required=false、CDP reclaimed=true；post-close完整操作摘要仍有unknown，不能授整体验收通过。Root定位App读取plan.old_binding而回退JSON使用plan.target_binding，bridge类型缺target_binding；此UI失败不解锁recover，R1–R4门均未签。

历史v0.13原生失败及SHA索引在`planning/execution-update-20261103T033000Z/execution-snapshot.json`；模块/构建索引和candidate03/04冻结原件独立保留。以下原生02及candidate04段落保持当时身份；App/bridge已修、candidate05已建，当前唯一动作见顶部v0.14及末尾。旧主恢复、旧模块全套和前端build-02不因文档更新重复运行。

### 历史v0.13：原生02失败与当时下一候选

11:30快照：原生02 fail；select-root/history通过，正式预览已ready，但目标实例字段未正确显示，断言失败时尚未confirm/cancel。suite资料保护true；host node_exit1，产品graceful exit0、job_drained=true、job_close_cleanup_required=false、CDP reclaimed=true；post-close完整操作摘要仍有unknown，不能授整体验收通过。Root定位App读取plan.old_binding而回退JSON使用plan.target_binding，bridge类型缺target_binding；此UI失败不解锁recover，R1–R4门均未签。

历史v0.13证据：本run `R1/native-rollback-02/rollback-report.json`、`host-status.json`及`005-FAILED-real-zero-byte-rollback-preview-and-confirm.png`；suite `cancel_attempted=false`，精确operation ID缺失，host post-close汇总保持partial-or-fail。不得把退出时shutdown或旧committed intent当本次UI取消/恢复证明。当时计划App/bridge修复、candidate05及newattempt03；当前已推进至顶部v0.14，旧02保留fail。

### candidate04构建产物（11:25快照，仅身份）

build04于2026-11-03 11:16:34完成，83063.3043ms、exit0、输入稳定且分发输入匹配，Job受控1→0；构建回执本身`product_acceptance=not-run`，后续原生状态另取native-rollback-02回执，不把构建字段倒写为原生结果。

| 产物 | SHA256 |
| --- | --- |
| EXE | `cca893effdbe6c42c51424e4436959a0f49d6c42fce50e04e535635fc4cfd0dc` |
| portable | `2ce76fbabb300d4b0d5d6b11c00240ce027b11a0e710bf6f89c0ae197e4915ce` |
| setup | `ba273d4979dc1b8da00cf2a33635f20d70783ef9f42d9127b0f51c58170b5a25` |

输出根：`F:/NextTrainerLauncherSandbox/reliability-20261102/run-20261102T130200Z/build-R1-04`；构建回执：本run `R1/build-04/execution.json`；新规划快照独立保存于本次planning目录，不能覆盖03或失败原件。

### 历史v0.14 candidate05与原生03/04证据身份（recover当时pending）

- App使用`plan.target_binding`，bridge补齐同名字段；VNode目标显示4/4，`R1/rollback-target-display-01/frontend-build-01/execution.json` exit0、源稳定、Job自然0→0。App SHA `aa986e9607a91da529a80e5b038fb84d916134e98e3a9fa1d29b72f1f2a83357`，bridge SHA `f43071f967e980d366aef5da6612d99bcecf3ff6ae858e7e86124b749901a4f9`。本层不继承旧33/33、build-02或Rust结果为改后全部源码的全套结论。
- `R1/candidate-freeze-05/freeze.json` complete，173产品输入/15工具；source-inputs SHA `76f291bdd0b2c1d33e0e634567043e925ab621549edc630ec0d77f1aec5f4de8`，tool-inputs SHA `5fd4fe38375bd68937ae01ee464950d62236b321d693c9b157499579fbb5f7ae`。`R1/build-05/execution.json` exit0、80578.4374ms、源稳定/分发匹配，Job受控1→0，仅授构建身份。

| candidate05产物 | SHA256 |
| --- | --- |
| EXE | `0fef848a8d7c9dffc5d9770d8457dde6be12eb8dd58d8a6d5d04599b5fd21637` |
| portable | `3227481527b881d94183cbd01dc2d26cda4eafe68590a1eaff7c793bbc8ab228` |
| setup | `cfdfa0b4bc265b444f754777510ecf97f8b7dcd3fa46a055abab4b4ac95bc973` |

- 输出沙盒`F:/NextTrainerLauncherSandbox/reliability-20261102/run-20261102T130200Z/build-R1-05/`。native03正式选根/历史/preview/confirm通过，唯一操作`download-1793678350-249172-0`；工具误要求logs_read持久日志而fail，`cancel_attempted=false`。suite profiles/states保护true；host graceful exit0、Job自然排空/no-force/CDP reclaimed true，但postclose `expected_controls=false`，整体仍fail。退出shutdown取消不授UI取消，**recover03禁止**，原件`R1/native-rollback-03/`只读保留。
- `OperationManager.operation_events`是权威进程内操作事件；App.addLog的`sessionId=null/persisted=false`界面日志不保证落盘，前置扫描可合法没有Engine logger，禁止为工具通过给产品增加日志。新工具`R1/rollback-harness-04/`及`native_rollback_session_04.py`改用正式事件、同ID内存/磁盘、真实分组及唯一根running，原committing/registry/只点击一次条件不变；Node9/Python8合同及语法pass仅授工具。**native04真实UI取消suite/host双pass，Root已启动同candidate05新进程recover04，结果pending，不重开。** 操作`download-1793679259-261344-0`，真实新pending`gui-rebuild-rollback-1793679282-261344-0`；两端cancelled/cancel_requested，registry未改，suite资料保护true；host node_exit0、graceful exit0、Job自然before0/drainedtrue/close_cleanupfalse、CDP reclaimed true，postclose terminal/controls/protection及passed均true；430.295秒含准备。最终scan→CAS边界及恢复/时限另证，旧回执unknown不倒写。
- R2 `R2/harness/`多根宿主fixture-selftest-02 29/29、query-tool-tests-02四项合同及语法通过；R3 `R3/harness/reliability_main_preview_suite.mjs` SHA `2b6148eb889d953f42698769bd12b06d6c646533fcdd0d29944043977dfcedf0`，16/16合同/两语法通过。R2/R3仅工具已交，真实GUI未跑，不能授42CASE通过。

### v0.15 R1签收与当前R2入口

R0/R1 done，RP-EXIT-R1按正式恢复缺陷及保护范围签收；R2可取消引擎检查任务active（in progress），R3必要前置in progress，R4–R6 pending。candidate05下native04真实UI取消留下合法committing事务，新进程正式GUI recover04 succeeded、intent committed并绑定g1208b56f57f3e752，正式IPC重复恢复也succeeded。两原生suite/host均pass，资料/控制保护及自然Job/CDP回收通过。当前full Rust344pass/0fail/15ignored，60份Rust/Cargo输入与当前及candidate05一致。R1-04按参数证据pass-with-boundary，不夸全GUI矩阵；R1-06最终CAS合同及实际命中原生window通过，分块取消/性能时限仍属R2/R4，未外推。Anima Fast停服full单配置实测suite/host通过，首反馈1.9ms、任务ID可见上界17.1ms、完整检查保守285776.1982–285935.7808ms，worker/readers回收及控制/资料保护通过；仅授该配置，取消与余三引擎未验。旧native02/03失败保留，recover03禁止。R2–R4门未签，嵌套Operation取消盲区仍待修。R1阶段Git保存待做，当前增量未提交/未push；整个专项/既有active Goal尚未完成。

Anima Fast停服full单配置实测suite/host通过，首反馈1.9ms、任务ID可见上界17.1ms、完整检查保守285776.1982–285935.7808ms，worker/readers回收及控制/资料保护通过；仅授该配置，取消与余三引擎未验。 证据：本run `R2/query-anima-fast-full-01/native-report.json`、`host-status.json`、`0007-full-workflow.json`，真实query ID `query-407f0-18e46e65cb6206c8-0000000000000001`。6 checks通过且unknown/page_errors为空；host290.1410803855397秒、exit0、自然Job/CDP回收。报告acceptance_complete仅此一配置，不作整个专项完成；未另授独立probe/取消分支。

证据：本run `R1/stage-evidence-audit-02.json/md`、`R1/stage-completion-02.json`及`R1/native-rollback-recovery-04/`。主GUI操作`download-1793679717-267288-0`与重复IPC操作`download-1793679812-267288-1`分列；真实事务`gui-rebuild-rollback-1793679282-261344-0` committed，registry回到g1208b56f57f3e752。65保护文件＝61 profiles＋3 instance states＋1 release receipt及完整文件集合保护通过；两host均exit0/Job自然0/CDP reclaimed。recover host174.6860019925516秒含prepare，GUI check95.633秒；原回执cancel receipt unknown保留，不用shutdown授UI取消。R1-04参数pass-with-boundary；R1-06最终CAS及实际命中window通过，最终scan→CAS原生窄竞争与≤5/≤10秒不外推，按R2/R4继续。Root后精准stage commit/push，R2/R3前置源码不授阶段通过。

### 实测精简与复用规则

- 同一最终EXE、相同fixture/配置/服务状态且间无影响改动的真实session，可同时覆盖多个CASE，并逐项引用同一断言/截图Pointer；例如R2大引擎、R4-01与R5-02可共享适用的完整检查证据。场景或包身份不符则补最短受影响链，不以共享降低断言要求。
- 四完整＋四取消只统计四引擎独立query验收实例。安装/修复/重建的必要内部校验不是额外要求重跑的query，也不能自动证明检查按钮或进度UI通过。
- 原生可见状态按必要变化拍图，一张原图可被多个断言引用。模块/工具合同保存真实输出、退出码、输入/源SHA与回收；`screenshots=[]`并注明不适用，无需伪造界面图。
- 旧353图不机械复制到E盘；新索引引用原件，离线交付图集按现有F增量及E证据上限选择位置并计量。历史未计流量/峰值继续unknown；R0已有核账保留，每个新重案只补当前余量/增量/暂存上界检查，不重扫旧资产重建账本。

## 进度台账

| 阶段 | 状态 | 输出/验证现状 |
| --- | --- | --- |
| R0 基线与测量 | done | 六探针、旧未闭项映射、资源核账、单调钟/I/O校准、120秒截尾采样和9次原生导航完成；RP-EXIT-R0通过，证据见本run R0/stage-completion.json；非产品修复通过 |
| R1 恢复自阻挡 | done | audit02确认旧两项minimum supplement实际齐备，completion02签RP-EXIT-R1；正式Core参数/真实lease、当前full344及native04取消/恢复/重复通过。R1-04参数pass-with-boundary，R1-06时限/全链取消留R2/R4；阶段commit/push待Root |
| R2 可取消引擎检查任务 | in progress | 当前active；query-anima-fast-full-01停服full单配置6 checks与suite/host通过、完整检查保守≤285.936秒；只授Anima该配置，取消/其他引擎/完整链路与时限仍未闭，门未签 |
| R3 重装预览弹窗 | in progress | 旧33/33/build-02保留；target_binding VNode4/4与frontend-build-01通过；main-preview工具16/16合同/两语法通过、未GUI；原生取消重开/多包损坏/焦点/首反馈仍待验，门未签 |
| R4 扫描与启停性能 | pending | 两层合计预算19/19及controlled扫描修订已获模块验证；性能/原生时限未验，门未签 |
| R5 最终同包定向沙盒回归 | pending | 本阶段CASE全部not-run，不套用旧通过 |
| R6 交付 | pending | 未形成最终同包交付及阶段push回执 |

整体进度：R0/R1 done，RP-EXIT-R1按正式恢复缺陷及保护范围签收；R2可取消引擎检查任务active（in progress），R3必要前置in progress，R4–R6 pending。candidate05下native04真实UI取消留下合法committing事务，新进程正式GUI recover04 succeeded、intent committed并绑定g1208b56f57f3e752，正式IPC重复恢复也succeeded。两原生suite/host均pass，资料/控制保护及自然Job/CDP回收通过。当前full Rust344pass/0fail/15ignored，60份Rust/Cargo输入与当前及candidate05一致。R1-04按参数证据pass-with-boundary，不夸全GUI矩阵；R1-06最终CAS合同及实际命中原生window通过，分块取消/性能时限仍属R2/R4，未外推。Anima Fast停服full单配置实测suite/host通过，首反馈1.9ms、任务ID可见上界17.1ms、完整检查保守285776.1982–285935.7808ms，worker/readers回收及控制/资料保护通过；仅授该配置，取消与余三引擎未验。旧native02/03失败保留，recover03禁止。R2–R4门未签，嵌套Operation取消盲区仍待修。R1阶段Git保存待做，当前增量未提交/未push；整个专项/既有active Goal尚未完成。 约60%准备、最晚70%前保存目标/已完成/决策/关键文件/待办/风险的续接摘要。

历史连续性：R0回执在`R0/git-save-receipt.json`；当前增量未提交。旧60/61项、缺SHA/长路径/locator失败及compile-02回收失败原件保留；compile-03受控清理和前端外层打印失败分列。本文档整理不授任何阶段完成，也不把工具Goal标complete。

## 下一步动作

后续续接的唯一下一动作：由Root按原阶段授权核对R1精准变更集并保存commit/普通push及远端SHA回执；本轮文档审核不执行git保存、GUI、构建或新测试。R1业务门通过不等于远端阶段基线已保存，含R2/R3必要前置源码不代表其阶段通过。Anima full原案已结束，不等待exec96794、不重复该案；42CASE、七阶段、4完整＋4取消、原阈值/资源、旧8失败行/10未操作按钮/52单元保持。
