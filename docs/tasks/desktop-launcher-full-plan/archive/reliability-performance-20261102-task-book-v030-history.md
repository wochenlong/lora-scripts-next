# CR-020：启动器可靠性与性能修复长程任务书

## 当前执行续接（v0.30-executing）

本轮已恢复既有 Goal 的完整 CR-020 施工；下方 v0.29“仅文档”是上一轮快照。R0/R1 done，R2/R3 in progress，R4–R6 pending，仅 R0/R1 门已签，专项与全局仍 incomplete。

candidate10 原预览业务 fail 保留。只读诊断定位第四 write_root：Rust `state/engines` 混合分隔符与 Python 分量路径字符串不等；生产形态 fixture 红测 1 fail 复现同错误。已将 capture 改为`join("state").join("engines")`，严格摘要/固定锁/路径/未知及链接拒绝不变；定向 10/0/0、fmt 通过。当前 `engine_namespaces.rs` SHA256 `c64a2825aea447af4c970ce46e0b911f1f235151ad376552e5f21405c1809c04`。

完整 `producer-owner-path-full-rust-01 --all-targets` 在主控采样时运行，exec session `4392` 仅为该时点句柄，结果尚须主控收取；随后严格 Clippy。candidate11 脚本已准备，未构建/冻结，正式原生尚未验，不能外推旧候选或合同通过。

唯一下一动作：主控先收取已启动的 producer-owner-path-full-rust-01 真实结果，核 exit、源码 SHA、Job/残留身份与日志；exec session 4392 仅为本次采样时句柄，不作为永久可复用句柄。完整回归通过后执行严格 producer-owner-path-clippy-01；各质量门与当前源码一致后才构建/冻结 candidate11，并显式绑定后继 v8 新批次进行正式只读预览。预览真正通过前不推进三取消、强杀恢复或 A/B/C；通过后继续原 CR-020 至 R6，不缩减任务。

本轮新台账与续接：`<run>/R2/execution-resume-20261103-08/execution-ledger.json`、`continuation-current.md`；07 原件及 08/09/10 失败原时钟保持。原 42 CASE、性能及 R2–R6 完整范围继续执行，不让用户补测。


## 当前审阅与执行基线（v0.29）

R0/R1 done，R2/R3 in progress，R4–R6 pending；仅 RP-EXIT-R0/R1 已签，专项与全局验收均 incomplete。candidate10 已构建冻结并完成 v7 绑定；定向 7/0/0、完整 Rust 434/0/15、fmt 与严格 Clippy 通过，仅属于对应冻结输入。真实预览 legacy-v7-preview-only-01 在确认前 fail，错误为“恢复候选计划与固定根/编译锁或原文摘要不符”；具体失败字段尚未定位。confirmed=false、无工具写 invoke、未产生 worker；真实关闭/退出、自然 exit0/Job 排空及独立失败保护比较通过，不能授业务、worker/reader 取消或性能通过。

本层为 v0.29 文档归一化，保留既有执行授权和 Goal，不创建、重置或标记工具 Goal 完成。本轮只整理文档。下方 v0.26 历史快照、旧阶段记录及“08 未构建/10 待构建”等描述仅是原时间点事实，不能作为现行操作指令。07/execution-ledger.json 和 continuation-current.md 尚停在 10 构建中；本次保留原件，最新事实以 candidate10 admission、v7 binding、native-report 与 host-status 为准。

当前唯一下一步：先只读拆分 candidate10 预览的组合校验拒绝，逐字段比较历史 plan 自摘要、schema/kind/rebuild、release/engine/profile、固定 recipe/lock、四 write_roots、profile_writes 与 main_env_fallback，定位具体不匹配项并落盘。当前只证实组合校验拒绝，不能预断是摘要、根或锁错误。定位后按原授权最小修复及正反例合同→当前输入质量门→冻结后继候选与显式 supersedes 新批次→正式只读预览；预览真正通过后才续三取消、强杀恢复及 A/B/C，继而完成 R2–R6。禁止删除/隔离保留候选、改历史 plan/journal、伪造 receipt/pending 或直接刷新原失败时钟重跑。

### 最新证据与审阅顺序

先审阅本任务书“问题、方案与验收目标”和“执行阶段”，再看独立验收矩阵与 Goal；内部事务和身份约束不新增用户按钮。

- 最新包：candidate10，EXE SHA256 `d3b3d9327ed4c5579fede3ad7556febe234ffa6a2bd7358a4feee1d3749f9d7d`；admission SHA256 `d1a481c5fb8ebf53155985d2fe11a6be017684c8a0245290f0d90e49273eef74`，构建时 175 个源码输入匹配。
- 真包原件：`<run>/R2/legacy-v7-preview-only-01/native-report.json`，SHA256 `d518ccd4f6cd0551d3623cad70980e1e88b5cb34b927543448306934345cf827`；引用 `/case_status`、`/failure_stage`、`/checks/0/detail`、`/confirmed`、`/write_invoke_used_by_harness`、`/preparation_query/worker`。
- 失败安全/退出原件：同目录 `host-status.json`，SHA256 `39f117fbde04518686c2471ad3ff5fa29083836e291d90bb9f721d8644afabdb`；只授 `/failed_preview_safety_protection/passed`、`/close/exit_code`、`/close/job_drained` 的限定结论。`reader_threads_proven=false`、`business_case_passed=false` 保持。
- 绑定：`<run>/R2/execution-resume-20261103-07/candidate10-v7-binding.json`；原案 CASE 起点 `1793707471921`、截止 `1793707831921`，链起点 `1793707467598.6416`，均保留。09 和更早失败原件不改，后继实现用新身份和 supersedes，不能刷新原 attempt。
- 本次八文档原稿、输入 SHA、保护集合及文档验证统一在 `E:/OpenSourceTeamWork/workspace/tools/launcher-reliability-20261102/planning/review-plan-v029-20261103T121203Z`。`<run>` 为 `E:/OpenSourceTeamWork/workspace/tools/launcher-reliability-20261102/run-20261102T130200Z`。

## 历史文档交付快照（v0.26-review）

本轮整理问题、优化方案、针对性实测与Goal提示词；文档工作不追加产品修复、构建、沙盒操作、commit或push。既有修复、执行授权、active Goal及阶段进度保留；已在途外部工具的轻合同收口单列，不冒充产品验收。

- **问题范围：** 恢复自阻挡、检查无反馈且不能取消、重装确认窗迟出、维护与启停慢；补原8失败行、AI Toolkit/Anima Fast共10遗漏按钮。T1–T5、R0–R6、42 CASE、52引擎展开及26条历史未闭项不缩减。
- **质量事实：** `uv-resource-fmt-02` exit0；`uv-resource-full-rust-03` 实际415通过/0失败/15忽略，两者均在本次错误出口修复之前。`legacy-errors-focused-01` 为7通过/2失败/2忽略，两个新增夹具问题已改但未复跑；四文件错误合同修复后的六合同、整树fmt/完整Rust/严格Clippy均待验证，不能沿用旧通过。
- **新增P1与方案：** `ControlledProcessReapFailed`在通用终态、deadline/rollback、旧resume watchdog及持久化失败出口曾被改写。四文件已作最小修复，尚待验证；正常落盘保持`Failed/worker_reap_failed`，持久化失败保typed错误并说明未保存、保留旧attached现场，不伪报恢复成功。详任务书RP-REAP-ERROR-01。
- **候选与工具：** candidate07已构建但固定uv EXE的67,598,848 B超过旧32MiB门，产品原生not-run；candidate08未构建。v4原46项工具合同通过仍绑定07；v5的verification-03已通过31项Node＋67项Python纯合同、14条Node语法及16份Python AST/compile检查，工具源码前后SHA一致、v4原件未变；仅证明外部工具。08身份接入、复验冻结与产品原生均未验，不可直接原生。回执为`<run>/R2/execution-resume-20261103-03/native-tool-preparation-v5/verification-03/verification.json`。
- **执行边界：** R0/R1 done，R2/R3 in progress，R4–R6 pending；仅RP-EXIT-R0/R1已签。专项和全局验收均incomplete。不训练、不加载/下载训练模型、不恢复产品下载预算；测试资源上界仅约束本次Agent操作。

本次八文档原稿、保护SHA、文档校验及审阅证据：`E:/OpenSourceTeamWork/workspace/tools/launcher-reliability-20261102/planning/review-plan-v026-20261103T104556Z/`。实际执行台账：`E:/OpenSourceTeamWork/workspace/tools/launcher-reliability-20261102/run-20261102T130200Z/R2/execution-resume-20261103-06/execution-ledger.json`；原审查及修复回执与测试原件分别保留，不覆盖旧失败。既有远端核验回执为同目录`remote-before.json`：2026-11-03T10:34:46Z的远端/本地均为`d409b00bac3bcb3e7ef56b424c8946f240e0a38f`，本次文档交付未新发起网络Git。

## 计划元数据

- Plan ID：`desktop-launcher-reliability-20261102`；父计划：`desktop-launcher-full-20261028`；变更：CR-020。
- Version：`0.29`；Last updated：2026-11-03（Asia/Shanghai；v0.29 文档归一化）。
- Canonical progress file：[00_总控目标索引.md](00_总控目标索引.md)。本文件是其专项详细台账，只有一份总进度。
- Related handoff file：`<run>/R2/execution-resume-20261103-07/continuation-current.md`；同目录机器台账仍停在 10 构建中，需与开篇 v0.29 原件对照；旧 review 续接仅作历史。
- Current branch：`feat/desktop-launcher`；工作副本：`E:/OpenSourceTeamWork/workspace/branches/dev`；本次实核HEAD：`d409b00bac3bcb3e7ef56b424c8946f240e0a38f`。
- Current active phase：R2 可取消引擎检查任务；Execution readiness：`executing`（既有授权和阶段状态保留；本次仅文档交付）。执行先读开篇 v0.29 的最新原件及单一下一动作。
- 规模/模式：既有Full体系的Standard增量归一化。目标、阶段任务、开工清单与完成门合并在本文件；实测独立放入[验收矩阵](reliability-performance-20261102-acceptance.md)，预检、最小探针与最终文档复盘合并在[开工复盘](reliability-performance-20261102-readiness.md)。不新增平行计划。

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

## 审阅重点

本专项沿用已有可靠性计划，新增问题按原编号续接，不重做已完成阶段。普通用户仍使用“检查修复”等现有按钮；新增的任务ID、事务和资源校验是内部实现，不增加用户必须理解的操作。

审阅时优先看下方“问题、方案与验收目标”表、R2/R3/R4的用户可见结果、R5同包实测范围和性能阈值。详细 Job/uv/旧环境内容是保证取消和恢复可实测的依赖，不能代替四类原问题的完成验收。完整CASE、截图与日志要求见独立验收矩阵。

## 目标

解决恢复自阻挡、检查无反馈且不能取消、重装弹窗迟出、维护与启停慢四类问题。普通用户继续使用“检查修复”等现有入口；长操作及时反馈、进度可信、可以安全取消，服务就绪/停止后按钮及时切换。由Agent完成针对性真包验收并交付截图、原始日志和文件保护证据，不把剩余实测交回用户。

### 问题、方案与验收目标

| 目标 | 具体方案与用户可见结果 | 针对性验证及完成门 |
| --- | --- | --- |
| T1 恢复事务可以恢复自身 | 仅为根、版本、事务ID、类型、计划与备份全部匹配的当前事务放行；其他事务/真实占用继续拒绝 | 正式Core及GUI恢复→终态→幂等；错误身份、其他pending和真实lease拒绝且零越权写；R1、CASE-R1-01…06 |
| T2 检查及时反馈、可追踪可取消 | 后台检查任务返回稳定ID，分阶段进度，同目标共用一次检查；切页可订阅，显式取消影响整个任务；概况与完整健康分开 | 四引擎各完整检查1次＋取消1次，跨页/单飞/迟到结果/worker异常；R2、R5，CASE-R2-01…12 |
| T3 重装点击立即出现确认窗 | 先显示准备弹窗，异步生成真实计划；ready且身份有效才可确认，错误在窗内说明 | 原多包缺损路径、准备/取消/Escape/焦点/晚到结果、中英文亚克力；R3，CASE-R3-01…05 |
| T4 维护与启停更快 | 先计量阶段、扫描文件/字节，再合并同一安全观察阶段的重复工作；ready/stopped事件直接更新按钮 | 完整性差分、源码修复、主重建、3次启停与HTML/API/监听归属；R4，CASE-R4-01…05 |
| T5 旧失败有新结果且可追溯 | 逐分支补原8失败行、AI Toolkit/Anima Fast各5未操作按钮，冻结一个最终包回归 | 新旧映射、四引擎13×4单元、空根主安装与服务、截图索引及阶段push；R5/R6 |

性能指标是验收目标，不能写成已经取得的成绩：首反馈/准备窗≤300ms；任务受理≤1s；活跃阶段进度/心跳≤1s；取消受理≤1s、扫描停止≤5s、自有Job排空≤10s；各引擎完整检查≤300s；小源码修复≤15min；主实例重建≤25min；启动至HTML/API语义200且打开网页入口可见≤60s；ready到网页按钮、停止到启动按钮≤500ms。轻操作至少3个真实样本，重操作各1次；起止点与外部门详矩阵。不得自行降指标、缩小故障输入或略过完整性校验。

## 历史实现快照（截至 v0.26；现行以开篇 v0.29 为准）

本节以当前工作树、实际执行原件和实施者交接为准；本次修订前的八份原稿逐字归档在当前review目录的`before/`及`before-manifest.json`，更早版本仍在原review目录。保留原时间、旧失败、原报告和原始证据，不倒写历史。

| 范围 | 已核事实与证据身份 | 尚未完成 |
| --- | --- | --- |
| 历史全量验收CR-019 | 227行：193 pass、24 partial、8 fail、1 blocked、1 pending-review；52是四引擎展开，不能与227相加。旧包FINAL06、原结论保留 | 本专项完成不自动把全局验收改为通过 |
| R0/R1 | 已签RP-EXIT-R0/R1，R1恢复主路径与拒绝/幂等证据属candidate05；R1保存基线为上述完整HEAD，push回执`<run>/R1/git-save-receipt.json` | 远端同SHA已核回执见开篇，本轮未新联网；R1签收不覆盖扫描/Job时延和所有GUI变体 |
| 旧main安装续办 | candidate06确认取消/基础Python验证中取消限定通过；成功续办在import exit1，原journal、current dev、61份profiles及两份receipt保护保持 | 成功提交、重开和服务链未通过；不能用目录存在代表安装健康 |
| 最新依赖诊断 | `<run>/R2/legacy-import-diagnostic-02/`同解释器、`-I -B`与预期根实际报`ModuleNotFoundError: No module named 'pip'`；site-packages仅两份venv骨架文件，依赖未装 | 缺依赖须独立修复；旧空logger吞正文是另一可观测性问题，不再把真实根因写unknown |
| 错误与阶段显示增量 | RP-DIAG已透传Logger、有界stderr尾部；修后定向Rust5/5、日志8/8及严格Clippy通过。RP-PROGRESS实际生产函数＋Vue refs3/3、前端build通过 | 增量未commit/push；07已构建但未原生，08未构建。较早Rust368/0/15仅为历史；full02原输入结果及当前漂移见下行 |
| R2/R3 | candidate05停服Anima完整检查≤285.936s仅授该配置；运行态取消01/02失败保留。R3 r301在故障删除前由工具误拒；后继v2工具合同通过且已冻结 | 其他引擎、Anima运行态取消、事件→DOM、真实两包弹窗未闭；工具合同不等于产品通过 |
| 最新产品与联合验证 | `uv-resource-fmt-02` exit0；`uv-resource-full-rust-03` 实际415通过/0失败/15忽略，两者均在本次错误出口修复之前。`legacy-errors-focused-01` 为7通过/2失败/2忽略，两个新增夹具问题已改但未复跑；四文件错误合同修复后的六合同、整树fmt/完整Rust/严格Clippy均待验证，不能沿用旧通过。 | 旧15忽略项另列；full03强制收尾的vctip.exe属构建工具，不能授产品自然回收；原生/性能/最终包未验 |
| RP-LEGACY-UV-01与工具 | 资源合同3/3通过保留原身份；candidate07已构建但固定uv EXE的67,598,848 B超过旧32MiB门，产品原生not-run；candidate08未构建。v4原46项工具合同通过仍绑定07；v5的verification-03已通过31项Node＋67项Python纯合同、14条Node语法及16份Python AST/compile检查，工具源码前后SHA一致、v4原件未变；仅证明外部工具。08身份接入、复验冻结与产品原生均未验，不可直接原生。回执为`<run>/R2/execution-resume-20261103-03/native-tool-preparation-v5/verification-03/verification.json`。 | 正式计划、原生修复/续办/服务未验 |
| RP-PIPE-01修复及限定通过 | 原03失败保留；fix04实际join10.6999ms、unjoined=false、writer仍活；最新full02仍执行同名测试通过 | 仅授管道合同；PendingManagedQuery外部writer持有、真实IPC/Job及GUI取消参数继续待验 |

历史执行续接证据：`<run>/R2/execution-checkpoint-20261103T145207/continuation.md`；后继实施台账见开篇，新审阅快照及下一步见本次v0.26 review目录的`continuation.md`。`<run>`固定为`E:/OpenSourceTeamWork/workspace/tools/launcher-reliability-20261102/run-20261102T130200Z`。

## 范围与约束

1. 保持现有一个“检查修复”主入口、亚克力视觉、侧栏与中英切换；内部任务/实例/代次不增加成用户必须理解的按钮。
2. 旧8失败行是`APP-ENV-004、ENV-MAIN-01、ENV-MAIN-06、GUI-LIFE-05、ENG-01、ENG-02、ENG-04、ENG-09`。每个原分支有新结果后才更新对应结论，不把它们误说成8个独立根因。
3. 原24 partial、1 blocked、1 pending-review逐ID处置见矩阵“历史未闭项处置台账”；同包补测、共用证据和历史保留分列。`APP-HOME-014`取消启动显式映射，源码不可达`GUI-LIFE-07`及非受管旧配方/测试会话等缺口保持，不因专项通过关闭全局验收。AI Toolkit与Anima Fast各`ENG-06…10`：收起结果、高级选项、仅检查文件、重新安装环境、运行检查，逐目标真实操作。52单元和额外未闭项映射沿验收矩阵，不凭一个子分支通过把父项全部授pass。
4. 网页服务运行时允许只读检查、计划预览及无冲突的独立引擎安装；目标训练/占用/已有修改任务才限制目标修改。主程序本体变更保留必要的服务排斥。
5. 不开启真实训练、不加载或下载训练模型、不改驱动；import/probe不等于训练或GPU通过。不恢复产品下载预算、计数器或额度UI。
6. 只操作具有明确归属和备份的自有沙盒；保留用户安装、资料、模型、窗口、服务、旧失败和无关dirty/untracked。不reset/clean/add -A/force push，不公共发布，不用生产密钥、付费云或未授权服务器。

## 执行阶段

稳定顺序：R0→R1→R2→R3→R4→R5→R6。代码分析、轻合同可分工，只有一个集成者；正式GUI和重磁盘操作各最多一个。依赖缺陷可以提前做最小共用修复，再回到原阶段验收；不提前签后续阶段。每阶段结束更新台账、精准commit、普通push并核远端完整SHA一次，然后继续。既有阶段授权不重复索取。

### R0 基线与测量

- 目的/状态：建立真实身份、旧失败映射与计量能力；`done`，原证据保留。
- 开工清单：实核Git/脏文件、目录归属与碰撞、服务/进程归属、资源余额；旧报告只读；先处理自有未终态测试。
- 步骤/输出：冻结源码/EXE/配方身份、227/52未闭映射；以小夹具验证Core恢复门、进度协议、启动前取消、共享订阅、控制文件不变、扫描差分；建立`baseline.json / issue-map.json / resources.json`及计时采集。
- 验证：CASE-R0-01…04及RP-PROBE-01…06；新单段探针≤120s，不为重现历史54/85分钟而盲跑旧重案。
- 完成门`RP-EXIT-R0`：危险前提有证据、资源及回收可执行；证据`<run>/R0/`。失败保存原件，先修设计，不进入依赖它的危险写入。

### R1 恢复自阻挡

- 目的/状态：精确恢复自身但不放宽其他事务；`done`，签收及原包身份保持。
- 开工清单：R0通过；根/版本/事务/备份/资料基线明确，正式Core与GUI链可执行，真实lease能验证。
- 步骤/输出：持工作区变更租约后仅为匹配当前恢复的事务增加例外；校验root/release/action/ID/类型/计划/备份；全根其他pending、资料/壳/Python/登记冲突仍拒绝；持久化操作、恢复终态及幂等一致。
- 验证：CASE-R1-01…06；真实“复验并恢复此事务→确认恢复”、重复恢复、错身份/损坏备份/其他pending/占用拒绝，核资料与非目标绑定不变。取消写前不提交、写后按实际成功收尾，不伪造cancelled。
- 完成门`RP-EXIT-R1`已签：正式入口、receipt/绑定/事务终态及P1资料保护已证；证据`<run>/R1/stage-evidence-audit-02.json`、`stage-completion-02.json`。≤5s/≤10s时延仍在R2/R4，未签的GUI变体保留边界。新问题先留现场再最小修复，不删除guard或pending。

### R2 可取消引擎检查任务

- 目的/状态：完整检查可观察、可取消，基础概况不冒充完整健康；`in progress`。
- 开工清单：R1通过；读任务管理/锁语义；Rust/Python帧协议、查询写入白名单、总期限与共享取消规则明确。依赖旧main失败根的续办、服务及对应运行态用例须先解除该环境阻塞；身份明确的独立健康夹具可在自身前提满足后验证只读/弹窗等独立链路，不要求先修旧main。依赖取消/恢复的变更实测须先核RP-PIPE-01适用性及尚未覆盖的Job/事务前提。
- 步骤/输出：立即返回task ID；完整检查在后台单飞，同root/release/engine/instance/generation/配方/范围才共用；切页/最后退订不自动杀任务，显式取消告知所有订阅；旧root/任务/代次结果丢弃。快速概况仅显示安装、绑定、最近检查及占用，不写healthy。
- 全链取消：从请求入口统一deadline/CancelToken，覆盖排队、catalog与前置租约、基础Python全校验、工具锁/缓存发布、worker输入输出/解析/结束及Job排空；哈希分块检查，限频真实文件/字节进度与心跳，stdout进度和终态分帧，stderr脱敏、有界。终态唯一；取消与成功按实际线性化，已成功返回already-terminal。
- 安装控制保护：查询不取得安装变更锁、不改registry、engine state/generation、receipt、pending/intent或binding；仅白名单日志、查询任务记录及固定工具缓存可写。容量和历史记录有界，活动任务不能被逐出；具体内部限制沿现有CASE-R2-02/10/11，不能变成产品下载额度。
- 既定容量合同保留：resolver入口32、不同身份在途4、重扫描槽1；满载时重复身份仍能加入已有任务，新唯一目标返回busy。终态历史64、alias128、事件128/任务、订阅32/任务且全局256、结果4MiB/任务且总存储16MiB；活动task/alias不能被历史淘汰。RP-DIAG默认日志8KiB规则保留，错误路径保有界64KiB合计尾部、stderr优先及约48KiB JSON余量；长输出必须有截断标记，不能丢末尾异常。
- 验证：CASE-R2-01…12，正式IPC、切页/重复点、迟到结果、准备/扫描/worker取消、异常回收；RP-DIAG保非零错误末尾和取消分类，RP-PROGRESS测权威事件→真实DOM两个阶段≤1s、轻量3样本。
- 完成门`RP-EXIT-R2`：合同/集成及至少一真实大引擎检查和取消达标，旧安装前置闭环；其余四引擎在R5集中收口。证据`<run>/R2/`。失败不改变安装健康，不在worker实际退出前宣告取消完成。

#### R2续验：RP-PIPE-01 管道取消修复与端到端回收

- 归属：保持CASE-R2-11的`blocked-sync-reader`参数及原测试名称，关联CASE-R2-07、R1-06、R6-03；42模板不增加。03失败原件只读保留。
- 已核诊断/实现：本机Rust1.94 ChildStdout走重叠I/O（ReadFileEx），只调用CancelSynchronousIo不能取消该读取。当前每条管道持有OwnedHandle副本，取消阶段重复CancelIoEx并保留同步取消兼容路径；必须实际join，复制失败时排空自有Child/Job。
- Phase A已完成：fix04为1/1、exit0，10.6999ms、Windows995、unjoined=false且writer仍活；之后才stop helper。不是通过提前关闭writer消除故障。full02原输入的同名测试继续通过；两批源码身份分别保留，不能把04原毫秒值移植给后继输入。
- Phase B后续执行：full02/Clippy02保留原输入，当前错误出口修复先补六合同及整树质量；按影响补正常EOF、连续输出、日志尾部、阻塞logger、读取/取消竞争与真实Job排空。正常返回或995须已join；未知错误不能授通过。`PendingManagedQuery`外部writer仍持有时的pending与10秒回收边界另按CASE-R2-11验证，不假定本修复已覆盖所有执行器。
- Phase C后续实测：在新候选正式IPC及GUI证明取消接受、扫描停止、reader/logger退出、Job排空与安装控制不变；没有真实退出前不能显示取消完成。宿主强制回收仅记录cleanup，不替代产品回收。
- 证据：`<run>/R2/pipe-reader-fix-01/reader-actual-result.json`、`R2/rust-integration-01/pipe-reader-fix-04/`、`pipe-fix-full-rust-02/`与`pipe-fix-clippy-02/`。小合同≤120秒，真实检查外门360秒含回收。失败保现场，禁止依赖未证回收能力恢复目录；前提通过后自动继续原阶段，不新增用户审批。

#### R2前置：RP-REAP-ERROR-01 错误出口与未保存状态

归CASE-R1-06/R2-07/11/R6-03，不增加42模板或重型轮次。`ControlledProcessReapFailed`必须贯穿通用finalize、独立环境deadline/rollback、原SHA resume watchdog及屏障/操作终态持久化失败出口，保留`requires_new_host`，优先于Cancelled和普通超时。正常落盘时为`Failed/worker_reap_failed`；持久化失败仍返回typed回收错误，用context明确“未保存”，旧attached/非终态现场保持。`OperationManager`的`operation_state_write_failed`表示终态未保存，不能冒称磁盘已记录回收失败或恢复成功；排空未证不恢复原件。

六个合同集中维护于此，均须按修后SHA重新运行；矩阵和Goal引用本段，不另存漂移名单：

1. `lifecycle_finalize_persists_reap_failure_before_cancel_and_keeps_other_results`：生产终态落盘及取消/普通错误/成功对照。
2. `lifecycle_finalize_persistence_failure_keeps_reap_error_and_reports_unsaved_state`：终态写入失败，原磁盘记录不变、内存明确未保存。
3. `production_rollback_deadline_finalize_preserves_reap_type_and_durable_barrier`：真实rollback→deadline→终态仍保typed错误、恢复屏障及原目录/journal。
4. `production_deadline_finalize_keeps_cancel_timeout_and_success_semantics`：完整回收后仍正确区分普通取消、超时与成功。
5. `production_attention_persist_failure_keeps_reap_type_and_attached_barrier`：屏障落盘失败，旧attached原文保持、同宿主仍拒恢复。
6. `production_watchdog_reap_failure_keeps_type_and_persisted_code`：旧resume watchdog不覆盖typed回收失败及正常可落盘的稳定错误码。

原发现`<run>/R2/execution-resume-20261103-05/production-independent-review.md`，实现和SHA回执`<run>/R2/execution-resume-20261103-06/error-contract-change-receipt.md`。首轮7/2/2原件只读保留，两个夹具问题已改但未复验。六合同含合成故障，不替实际Job/reader故障、三阶段取消、drop-job-before-kill、新宿主首次按钮恢复及A→B→C闭环。每段合同≤120s，先定向后整树质量；不能用修前415通过构建放行新包。候选08 freezer必须引用修后实际质量attempt及对应输入SHA。

#### R2前置增量：RP-LEGACY-UV-01固定资源身份门（保留原设计）

现行先处理开篇 candidate10 预览拒绝；以下 08 接线与修前质量描述是历史步骤，已完成部分只核输入适用性，不重复执行。该项归CASE-R2-07/12的`legacy-offline-resource`，不增加42模板。下载ZIP的23,236,992 B与解压uv EXE的67,598,848 B是不同身份，不能混用。现有草稿统一正式`resources()`及执行前校验；后续执行先完成以下步骤：

1. 核固定EXE真实长度、配方SHA、原资源索引与归档展开上界；仅修正该固定资源的边界，保留其他文件32MiB/完整树上限、增长/取消/超时与SHA拒绝。不得取消上界或把全局限制放大来绕过。
2. 三个新增定向合同已有通过（后续输入变化时按影响补验）：正式资源函数缺归档拒绝且私有树零写；等长坏SHA拒绝且私有树零写；大于32MiB的固定长度文件可被完整读取且坏SHA/超界仍拒绝。实际fixture读取通过不等于真实可信uv或完整计划通过；实际资源另经正式预览核身份。当前三个合同3/3通过，修前fmt02/full03通过，修后完整质量not-run。
3. 按影响补格式、完整Rust及严格Clippy，明确新结果的输入SHA；修后先过RP-REAP-ERROR-01六合同，不重复修旧fmt门；可复用full02已证的八个rename窗口、三个命名Job生命周期等语义证据，仍须新集成质量通过。潜在常量断言静检问题在实现时正常修复，不将旧412项结果移植给新源码。
4. 新candidate08构建/冻结与源码清单核对后，将v5 guard、配置、回执和所有候选字面量接入08；旧07及v4原验证保留，重跑轻合同并冻结新SHA。正式只读资源计划先过且保护全集合不变，才允许写intent/移动env。
5. 历史v4 A仅支持success；v5已补专用故障工具，先核验/补齐其venv/sync/import三阶段取消与强杀/新宿主恢复轻合同、08接入及冻结。原journal仍pending且原env基线已冻结时，先逐案取消→强杀重开恢复及幂等，每案确认原env树、原journal SHA与保护控制/资料恢复一致，仅允许明确的终态事务/日志新增；任何needs_attention未清不得推进。然后才做A独立修复成功→B原SHA续办提交→C重开/main服务/停止/回dev。B前必须完成这些故障参数，禁止提交后手改pending补测；不另复制唯一失败根或扩大资源。C仅观察网页按钮不能替系统浏览器实际点击/归属与HTML/API证据，后者由R5正式验证。

证据：`<run>/R2/candidate-freeze-07/admission.json`、`legacy-resource-preflight-01/failure.json`、`legacy-resource-preflight-02/execution.json`、`resource-gate-fix-01/legacy_environment_repair.rs.before`和`execution-resume-20261103-03/native-tool-preparation-v4/verification-01/verification.json`。当前资源门仍未闭；失败留原件，不修改原journal或换小资源冒充通过。

#### R2前置：旧main环境独立修复与原安装续办

旧main不是人为故障夹具：原离线seed失败留了venv骨架，普通legacy重装会覆盖原journal，不能用来补绿。设计附件为`<run>/R3/legacy-environment-repair-design-20261103.md`。reader04及full02/Clippy02原输入已有通过；uv后继三个资源合同已通过，修前fmt02/full03已通过，修后完整质量未验，剩余生产拼装/Job与原生完成门未闭，以下链路仍需验收，不能把代码或部分合同通过当作能力可用。

1. 固定支持`main-0785419e7dc1a3058bd8710a9aa933fec0aabdee`。requirements原始1609字节/SHA `8dc07965d650ee22c0f4f0affa01a97f01550795f79dfed4f3bb780b9c3c3ff6`已由完整SHA匹配ZIP认证，恰与内置81 wheel输入相同；保持legacy recipe，仅复用已核原始资源超集，不给旧发布伪造现代binding/代次。其他源码仍沿既有验证语义，不声称整树都由ZIP认证。
2. 后台准备窗/只读计划先核原journal SHA、源、env树、Python/uv、81资源与锁及展开资源上界。资源上界从固定归档展开、安装生成文件和备份/暂存推导；所有资源身份/大小和目录上界通过才写intent或搬env；缺资源写前拒绝，不联网补依赖、不用旧`--seed`、不复制其他根venv。
3. 固定锁顺序workspace→service，持双租约建立独立事务。原env在最终路径备份/重建，原journal、registry/current dev、源码/receipt、资料和其他控制记录保持。先可信静态完整性再实际pip check、精确版本及关键import；不执行未知.pth。新pending统一接入常规启动/修改/旧resume门，仅本事务内部精确例外，不能做全release跳过。
4. 正常失败/取消/期限先确认本事务Job的`active=0`、Child退出与reader回收，才隔离自己新env并精确恢复旧原件。排空失败为稳定`worker_reap_failed`/needs_attention，优先于Cancelled，禁止恢复原件或伪报rolled_back；旧调用方自动恢复分支须同步遵守此失败契约；全部出口与未保存边界按RP-REAP-ERROR-01验证；将排空失败持久化为恢复屏障，新进程显式recover/旧resume也不能绕过。只有重新取得可信归属并证明后代排空后，才允许受控清障和恢复。
5. 强杀恢复必须设计可重新打开的本事务命名Job或等强持久归属机制，并证明Job关闭的生命周期边界；名字/权限/唯一性和重开时机必须合同验证。每命令独立Job，持久记录`launching→attached→reaped`与Windows session；必须在恢复初始线程前持久化attached。只有可信attached且同session时，精确Open返回`ERROR_FILE_NOT_FOUND`才可结合Job销毁生命周期证明排空；launching窗的notfound仍保持needs_attention。覆盖有外部持柄可重开、无外部持柄attached后已销毁、launching未attached三个不同参数。PID不存在、双租约重新可取均不能单独证明后代排空；无法证明则保留needs_attention。不得把此保守失败当强杀恢复正向通过。Job active0也不能证明宿主reader/logger线程已退出；`requires_new_host`必须持久记录宿主PID及创建时间，由新宿主先证明旧代退出，再核命名Job排空和清障。同一活宿主、跨session、缺可信侧录均保持拒绝；受控阻塞reader验证须有界返回。
6. 事务包含prepared/备份/预留目标/building/verifying/committing/restoring及succeeded/rolled_back/aborted/needs_attention。先在预留目录写可信ownership marker再原子rename；rename前后崩溃靠两端清单与独占ownership marker判定；未知目录、碰撞或控制漂移保留现场。成功只代表env已修复，原journal不动；然后由既有resume持原SHA单独复验并提交。
7. 最小实测顺序：缺资源/计划漂移/锁冲突写前拒绝→正式只读资源预览→原journal仍pending时分别执行venv创建/依赖sync/import三个阶段取消→至少一次构建中强杀/新宿主显式恢复/幂等→A真实离线修复成功→B原SHA resume committed→C重开/选择main/真实HTML/API200/停止/切回dev。每个故障案必须先回到精确原env/journal及保护基线、无未清needs_attention，才允许下一案；B提交是消耗原pending的最后一步，禁止之后回造。每案保存原件和保护全集合，独立env修复外部门360s含回收；这是现有CASE参数，不追加四引擎重案。

本前置映射CASE-R1-02/05/06、R2-07/11/12、R4-05、R5-05/07、R6-03，不增加42模板。新模块preview接既有query任务与准备窗；执行用既有OperationHandle，不建第二套任务系统。内部资源上限及安全收尾细节按附件冻结，未验证前不操作唯一失败原件。


#### 针对性实测的观测约束（v0.26）

以下只细化已有 CASE-R1-06/R2-07/11/12/R6-03，不新增重型测试或产品按钮：

1. **精确阶段：** 不能只凭 `operation.phase` 或日志文字认定 venv/sync/import。工具须验证已attached的真实worker、PID及创建时间（FILETIME）、命名Job/Windows session与实际命令行。错过短阶段记 `unsupported（当前工具未覆盖）` 并保留证据；不能以另一个阶段的取消或操作终态 `cancelled` 代验。
2. **强杀不干扰产品回收：** 在强杀宿主前，工具释放外部持有的产品Job查询句柄（drop-job-before-kill），仅保留提前获取的精确宿主/worker进程句柄；强杀后≤10秒实际等待两者 `SIGNALED（已退出）`。工具不得调用 `TerminateJob` 制造正向通过。额外持柄分支只放小合同；fallback强制清理单独留证且本案仍fail，不授产品自然回收或恢复成功。
3. **首次恢复与幂等分列：** 新宿主第一次恢复必须由真实按钮及确认窗进入。正式恢复成功后，才对同一事务重复一次正式 `recover_legacy_environment` IPC作为补充幂等证据，显式记录 `write_invoke_used_by_harness=true`；不能沿v4整体false、不以直调IPC代替首次用户入口。
4. **工具成熟度：** v5的verification-03已通过31项Node＋67项Python纯合同、14条Node语法及16份Python AST/compile检查，工具源码前后SHA一致、v4原件未变；仅证明外部工具。08身份接入、复验冻结与产品原生均未验，不可直接原生。阶段识别、句柄释放、可信点击与恢复保护的轻合同、候选08身份接线及工具SHA冻结全部通过后才准原生；产品资源计划先通过，再按三取消→强杀重开恢复/幂等→A独立修复成功→B原SHA续办提交→C重开服务串行验证，每案先恢复精确保护基线。

### R3 重装预览弹窗

- 目的/状态：点击立即有反馈，真实计划异步生成；`in progress`，R2必要前置已部分接线但未签门。
- 开工清单：查询/取消合同可用；后端执行仍重核计划、身份与占用；v2工具旧身份及r301误拒保留；现行 candidate10/v7 已绑定并预览失败；先按开篇定位，后继工具/候选须精确匹配并冻结，不重复接线到 08；旧失败不覆盖。
- 步骤/输出：同步显示准备窗→异步阶段→ready/blocked/error；只有ready且摘要有效才允许确认。关闭/Escape显式取消预览任务并说明共享影响；仅切页退订不取消。保持取消优先焦点、键盘限制、归焦及中英文亚克力。
- 验证：CASE-R3-01…05；原多包缺损、慢计划、失败/blocked、双击、切根/版本、准备中取消/Escape立即重开、取消IPC丢失/响应丢失及迟到成功。新attempt仅改有备份的精确故障文件，结束精确恢复并核集合/SHA。
- 完成门`RP-EXIT-R3`：真实准备窗≤300ms、计划确认/取消/焦点通过，原多包分支有产品结果。证据`<run>/R3/`；工具合同或导航成功不能替原生。失败分清工具与产品，不为测试器放宽事务保护。

### R4 扫描与启停性能

- 目的/状态：减少已测重复工作并及时刷新按钮；`pending`（部分共用取消代码提前实施，不代表阶段完成）。
- 开工清单：R0计量及R1–R3依赖通过；冻结同输入/缓存/负载与采集口径；查询不触发额外全树扫描。
- 步骤/输出：计量plan/before-observe/可信闭包/validator/复制/副本核验/entry probe/after-observe/最终门；同操作同观察阶段可复用，写入、探针、绑定/代次/receipt/所有权变化必失效。不用mtime/size替SHA；未知目录/链接仍拒。排除独立引擎实体前须证明命名空间归属、控制身份及写入边界，不能仅按名字排除；无法证明保持完整扫描。
- 启停：完整启动前校验保留；HTML/API和监听归属通过才ready，ready/stopped直接驱动按钮，不等待无关完整inspect。耗时校验可取消，原子提交收尾设计≤10s；超外部门按已验证恢复协议收口，不盲杀未知进程或无限等待。
- 验证：CASE-R4-01…05，同大小/mtime内容篡改、额外文件/链接、receipt/所有权漂移、探针前后变化差分；真实源码修复、主重建及3次启停。同步OS I/O、catalog/前置租约仍有待证取消盲区，必须保留真实时限结论。
- 完成门`RP-EXIT-R4`：完整性语义不弱化，真实关键路径及性能达标。证据`<run>/R4/`；有进度不代表变快，不可比样本不算倍速。未达先定位修复，不自行降目标签done。

### R5 最终同包定向沙盒回归

- 目的/状态：最终候选解决旧失败及遗漏；`pending`。
- 开工清单：R1–R4通过；冻结build commit、实际trainer/worker来源、catalog/recipe/lock摘要、EXE/分发SHA；空根与复用故障根分列，归属/备份/资源/回收明确。
- 固定实测量：四引擎各1完整＋1取消。Kohya/AI Toolkit在服务运行时完整检查，Anima Fast/DiffSynth停服时完整检查；另一服务状态做取消，不追加4次完整扫描。每引擎五类目标入口、实际import及一个小源码缺损修复分别留证。
- 执行：新空根经正式按钮主安装→启动→打开系统浏览器→HTML/API语义200与资源→停止/重开；AI Toolkit/DiffSynth补原安装失败收尾，其余复用核身份根。四引擎重装预览/取消均操作；主程序实际重建1次，并至少一个受影响独立引擎代表实际重建。原ENG-04按失败目标补最少精确中断恢复，不扩成四目标多轮大故障。
- 验证：CASE-R5-01…07及旧8行/10按钮/52单元映射；服务运行时只读/计划/独立目标允许，占用目标修改拒绝；恢复与旧main链按正式入口。正常运行缓存变化与原用户资料保护分别报告，不能全局忽略config掩盖差异。
- 完成门`RP-EXIT-R5`：本专项必测和性能实际通过，无未闭P1；预览/取消不能算重装执行完成。证据`<run>/R5/`；包变更按影响补链，旧包适用性必须证明，不能混包冒充最终同包通过。

### R6 交付

- 目的/状态：可用包、证据和稳定远端基线；`pending`。
- 开工清单：R5通过，无自有活案；原图/JSON/日志及新旧映射可追溯。
- 输出/步骤：最终报告、机器矩阵、离线截图索引、EXE/安装器/便携包路径与SHA、阶段push回执、资源与清理摘要。实际打开图集，验证筛选、关键原图及包内外完整性；仅提交代码/脱敏小索引，重资产留外部根。
- 完成门`RP-EXIT-R6`：R0–R5及交付均通过；精确回收自有Job/worker/CDP/监听，保留用户窗口/服务。证据`<run>/R6/`；`repair_campaign_complete`与全局`acceptance_complete`分开，必测fail/blocked/not-run/pending不能记complete。远端失败如实报告，不让用户代验凑完成。

## 每阶段开工、完成和失败共用清单

1. 读取README、manifest、唯一总控、本阶段目标/步骤、实测CASE及本节；核上一门与最新用户约束、Git状态、产品/工具/EXE身份和活动任务。
2. 记录绝对根/归属、无碰撞证据目录、资源余额与暂存/回滚上界、故障备份、精确进程回收能力；硬前置不满足写preflight failure，停止依赖它的危险动作，继续独立安全分析。
3. 按影响面跑`npm run build`、Rust fmt/受影响test、Python受影响launcher测试；最终候选前必要完整Rust及严格Clippy。合同验证状态机/帧/取消/差分，真实EXE/WebView/原生菜单和生产IPC验证用户行为；不mock invoke、不手写healthy/pending/receipt。
4. 完成记录含phase、covered_case_ids、changed_files、validation、failures、residual_risks、source_commit、exe_sha256、evidence、next_action。复用[完成门](00_预检证据/stage-completion-gate-template.md)、[失败报告](00_预检证据/failure-report-template.md)与[证据治理](00_预检证据/testing-and-evidence-governance.md)，旧记录只读。
5. 失败先保原件，再分产品/工具/前置原因，最小修复后新attempt；不因内部“两次失败”停止，不降低验收。真实新增授权不足、硬资源不足或不可隔离用户资料风险才停对应动作，说明来源。
6. 阶段通过后精准add/commit/普通push一次，GitHub每条网络git均用`http.proxy/https.proxy=http://127.0.0.1:11809`，核远端完整SHA。不为记自己的commit SHA再循环提交。当前本轮是文档交付，没有执行push。

## 实测精简与复用规则

保留42模板＝R0 4＋R1 6＋R2 12＋R3 5＋R4 5＋R5 7＋R6 3；新增故障是参数，不把模板数当实际次数。小合同覆盖身份/冲突/竞争/协议，多CASE可共享同身份原生session的原图Pointer；四引擎各自的按钮、完整检查与取消必须实际操作。未受影响旧通过保留原身份和适用性，受影响失败及未闭项补最短链，不重跑无关227行。原52单元每个variant单独裁定；未复测依赖损坏、重装确认完成等分支继续留缺口。

每案记录步骤、预期/实际、task/run/instance/generation、单调钟起止、阶段、源码/包SHA、截图/日志JSON Pointer、保护文件前后集合/SHA，以及精确PID代次/Job/监听回收。原生可见变化留截图；合同/工具无UI可`screenshots=[]`并解释。快案3样本列原值/最大/中位数，不宣称p95；前后输入不可比不计算提速倍数。

## 决策记录

- Verified facts（已验证事实）：当前HEAD和dirty实际已核；R0/R1签收；旧main缺pip/依赖未装已实证；RP-DIAG/RP-PROGRESS定向检查通过但原生未证；精确requirements外部锚及81资源输入相等已证。证据见本文件当前快照与附件。
- Active assumptions（当前假设）：既定性能目标可达、81资源可在当前根完全离线构建、原子marker与命名Job生命周期可满足崩溃恢复；必须先合同/最小探针，不把设计写成事实。
- Locked decisions（固定决策）：唯一总控、R0–R6稳定、不训练、保SHA与用户资料、精确目标冲突、单GUI/重操作串行、阶段push、旧失败保留、专项/全局完成分开。
- Open questions（待解问题）：强杀后后代排空持久证明、全部同步I/O/前置取消上界、其他批次未核残留的归属、最终候选原生取消与时延、历史未核资源峰值。归R2/R4/R5，不因未知要求用户另找机器，也不当作无限资源。

## 关键制品与环境

- 代码：`desktop-launcher/src-tauri/src/{core,legacy_install_recovery,query_tasks,query_ipc,engine_bridge_query,scan_observation,managed_child,gui_rebuild,gui_binding_switch,gui_install,gui_registration_integrity,instances,python_integrity,source_integrity,log_store,main}.rs`；新文件`legacy_environment_repair.rs`已在工作树且有部分合同通过，原生闭环未完成。前端`App.vue / EnginePanel.vue / MainReinstallDialog.vue / EngineQueryActivity.vue / bridge.ts / engine-query.ts / i18n.ts`；Python `mikazuki/launcher/{control,runtime,worker}.py`及受影响测试。
- 历史证据：`E:/OpenSourceTeamWork/workspace/tools/launcher-full-acceptance-20261101/`；历史重资产：`F:/NextTrainerLauncherSandbox/full-acceptance-20261101/`。现run见上文；现沙盒为`F:/NextTrainerLauncherSandbox/reliability-20261102/run-20261102T130200Z/`。
- 当前R0核账限额：新增重下载0；F增量≤80GiB；E本run证据≤200MiB。沿用原累计网络≤200GiB、F峰值≤300GiB且余≥100GiB、E新增≤5GiB且余≥20GiB；历史缺账/峰值unknown继续保留。planning备份及Cargo/npm产物分列磁盘增量并受原E上界约束；不能从旧20GiB/1GiB初值扩大当前余额。上述是测试资源治理，不属于产品功能。
- 单案时限：小探针≤120s；轻UI≤10min；引擎检查/旧env修复外部门≤360s；源码修复≤20min；安装/实例重建/变更恢复≤30min（均含回收）；串行组≤2h。不以拆案绕时限。超过门保失败和持久恢复票据，仅按已验证协议收尾，不无限等待。
- 清理：仅删除本次精确归属、已有替代证据的重复暂存，先核绝对边界/链接；唯一失败、原env/备份和旧日志保留。资源不足先停新重操作，缺固定SHA缓存记前置不足，不暗中新下载。

## 进度台账

| 阶段（稳定名称） | 状态 | 当前完成门及保存情况 |
| --- | --- | --- |
| R0 基线与测量 | done | RP-EXIT-R0已签，已保存 |
| R1 恢复自阻挡 | done | RP-EXIT-R1已签，基线d409b00…；本轮已核既有同SHA远端回执 |
| R2 可取消引擎检查任务 | in progress | 10 定向7/完整434及fmt/Clippy、冻结和v7绑定通过；10真实预览业务fail，失败保护/退出限定pass；组合校验具体字段待定位，RP-EXIT-R2未签 |
| R3 重装预览弹窗 | in progress | 接线及工具合同已有；两包场景/焦点/反馈原生未闭，RP-EXIT-R3未签 |
| R4 扫描与启停性能 | pending | 共用取消部分提前实施；真实扫描/启停指标未验，RP-EXIT-R4未签 |
| R5 最终同包定向沙盒回归 | pending | not-run；没有当前最终包通过结论 |
| R6 交付 | pending | not-run；整个专项incomplete |

Overall progress：candidate10 输入质量、构建和 v7 绑定完成；真实预览确认前 fail。Validation result：开篇原件是最新事实，旧失败保留，R2 门未签。Residual risks：组合校验具体字段、完整保护序列化、旧 main 修复/恢复、Job/reader 取消、性能及最终同包均未闭。

## 下一步动作

先只读拆分 candidate10 预览的组合校验拒绝，逐字段比较历史 plan 自摘要、schema/kind/rebuild、release/engine/profile、固定 recipe/lock、四 write_roots、profile_writes 与 main_env_fallback，定位具体不匹配项并落盘。当前只证实组合校验拒绝，不能预断是摘要、根或锁错误。定位后按原授权最小修复及正反例合同→当前输入质量门→冻结后继候选与显式 supersedes 新批次→正式只读预览；预览真正通过后才续三取消、强杀恢复及 A/B/C，继而完成 R2–R6。禁止删除/隔离保留候选、改历史 plan/journal、伪造 receipt/pending 或直接刷新原失败时钟重跑。
