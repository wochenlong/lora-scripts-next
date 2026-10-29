# 阶段 M5：独立壳与 Windows 分发长程任务书

> **现行验证 v0.5 / CR-004：** 四引擎只做冒烟，其他测试按改动影响面精简并复用有效证据；下文旧验证强度在冲突处服从[CR-004](../00_预检证据/change-control-governance.md#cr-004四引擎仅冒烟及精简验证)。CR-003 候选审核停止点、CR-002 OS 门及最终同包从零 GUI/分发保留，不开四引擎/GPU实测轨。

> 历史修订：0.3，2026-10-29，适用[CR-001用户GPU测试豁免](../00_预检证据/change-control-governance.md#cr-001用户批准跳过受资源限制的gpu验收)。Fast固定驱动不满足的GPU层、DiffSynth完整BF16模型/训练/权重子项授权`skip`，不作pass；Kohya/AI Toolkit及DiffSynth普通小张量等本机可执行验证保留。M0独立P3不再单独重试，CUDA验证进入对应引擎真实配方。干净Windows/安全/安装修复/同制品/阶段push均未豁免。CR-001边界继续有效；CR-002仅调整P1时点，其他合同继续有效；实时状态只见总控。

> 0.3时点修订：[CR-002](../00_预检证据/change-control-governance.md)已由用户明确批准，原文“批准调整，继续开发（推荐）”。仅将P1合法可用干净Windows/缺WebView2资源实际就绪移至M5相应系统动作及Phase6分发专项验证开始前。原结果`blocked`及失败证据保留，`deferred by CR-002`仅是延期调度，不计pass/skip。其余M0真实证据、独审、完成报告及代码C/状态S普通推送和远端核验齐备，真实退出M0后才可开M1；M6最终同包双轨/A1–A10未豁免硬门、CR-001与原预算均不变。下文起草语境与旧时点按本段及直接更新条款解释，实时状态只见总控。

## 计划元数据

- Plan ID：`desktop-launcher-full-20261028`；Version：`0.3`；Last updated：2026-10-29 Asia/Shanghai。
- Canonical progress file：`E:/OpenSourceTeamWork/workspace/branches/dev/docs/tasks/desktop-launcher-full-plan/00_总控目标索引.md`。
- Related handoff file：`none`；Current branch：`feat/desktop-launcher`。
- Current active phase：`none`；本阶段及各 Phase：`pending`；Execution readiness：`drafting`。
- 目标：[M5 实施验收计划](../01_目标计划书/06_目标M5_独立壳与Windows分发_实施验收计划.md)；开工前读取[阶段清单](../04_阶段开工清单/阶段M5_独立壳与Windows分发_执行前清单.md)。
- 唯一规格：[后续设计书](../../../design/desktop-launcher-next-design.md) §8–12；D1–D6 推荐仅为待审核假设。

## 目标

实现独立壳的可信替换、只读试运行和精确状态恢复，形成普通用户安装器/便携包及中文交付材料；以分发专项预验收冻结 M6 后续完整从零复验的候选制品。

## 范围与约束

- In scope（纳入）：独立 helper、升级互斥、原字节快照、trial 确认、壳/数据迁移分离、WebView2 与 Windows 分发。
- Out of scope（不纳入）：生产密钥代建/代用、公共发布上传、任意全局配置改动、把本阶段专项测试当成 M6 最终完成。
- 前置：M4 证据/独立复审/Git 退出门通过；状态兼容规则和分发机器矩阵已冻结；运行及系统动作在批准范围。
- 遵循[测试证据治理](../00_预检证据/testing-and-evidence-governance.md)、[资源授权治理](../00_预检证据/risk-and-authorization-governance.md)、[Git 基线治理](../00_预检证据/git-baseline-governance.md)。
- 本轮只规划，不生成安装包、不安装 WebView2、不创建沙盒、不修改状态或签名、不 commit/push。
- 未来执行只作用批准沙盒/VM；只等待归属明确的 PID/创建时间，不按进程名或端口杀其他程序；不复制模型/数据集作为壳升级备份。

## 执行阶段

### Phase 1：冻结更新身份、互斥和快照集合

- Purpose（目的）：让壳替换的事务边界和恢复材料在发生任何修改前已经明确。
- Outputs（输出）：独立壳资产/签名身份、更新状态机、安装器/壳/资料变更共用锁、控制状态枚举和快照原字节清单。
- Completion criteria（完成标准）：列全 registry/绑定、profile 描述、壳配置、未完成操作索引和待升级控制文件；快照保留原字节/哈希和恢复位置。
- Validation（验证）：未知 schema、配置可选项、残留操作和 profile 多版本夹具；证明漏路径会拒绝更新而非推测恢复。
- Evidence（证据）：`<run-id>/M5/phase1/` 保存协议、路径/锁矩阵、原字节清单、兼容表及资产身份。
- Failure handling（失败处理）：快照不全、未能停变更或资产不可信即停止更新；不以重新序列化 JSON 充当精确备份。

### Phase 2：实现独立 helper 与真实替换

- Purpose：在训练器或 GUI 环境损坏、当前 EXE 被占用时仍能可靠完成替换或恢复。
- Outputs：独立轻量 helper、事务目录、明确 PID 等待、替换/失败恢复、超时和崩溃重启现场判定。
- Completion criteria：helper 不依赖训练器 Python/GUI/待覆盖 EXE 模块；持更新锁后停全部变更；只操作清单中的文件与受管进程。
- Validation：Windows 原生 EXE 占用、读写权限、替换中断、helper 强退、外部同名进程和外部监听器 sentinel。
- Evidence：`<run-id>/M5/phase2/` 保存 helper 包身份、进程归属/创建时间、操作记录和替换前后哈希。
- Failure handling：保留事务意图和原 EXE，重启核对现场后恢复；不能通过结束同名程序、关闭外部服务或忽略替换失败继续。

### Phase 3：只读试运行与壳确认

- Purpose：在新壳尚未被接受时，验证真实窗口和恢复入口可用且不污染控制状态。
- Outputs：recovery mode（只读恢复模式）、事务 ID/随机令牌/进程身份握手、自检超时与还原流程。
- Completion criteria：trial 只读 registry/receipt/profile/config/操作记录，仅独立更新事务目录写日志；不得启动训练器、修复、安装或迁移。
- Validation：真实 GUI 渲染/恢复入口；错误令牌/PID、超时/崩溃/入口异常；试运行前后枚举控制文件原字节比对。
- Evidence：`<run-id>/M5/phase3/` 保存握手脱敏记录、原生截图、自检结果、每个控制文件字节/哈希对照。
- Failure handling：自检失败还原旧壳并保持原状态；试运行发生任何越权写入记 P0/P1，停止更新链修复后重验。

### Phase 4：分离格式迁移与恢复

- Purpose：防止“新壳启动成功”掩盖状态升级不可回退的问题。
- Outputs：壳确认后单独格式迁移事务、同锁保护、版本拒写和失败精确恢复；必要时维持新壳恢复模式。
- Completion criteria：确认前无不可逆迁移；迁移失败先还原控制状态原字节再回旧壳；不能恢复时不声称旧壳可安全读取。
- Validation：壳提交前后与格式迁移各写点强退/取消、旧壳不识别 schema、快照损坏/缺项、重复恢复和操作互斥。
- Evidence：`<run-id>/M5/phase4/` 保存壳/迁移两个事务、控制状态恢复证据、旧壳真实读取/启动结果。
- Failure handling：恢复材料不完整时留新壳只读恢复，不尝试旧壳写新格式；保留失败现场、用户资料和两套程序。

### Phase 5：生成 Windows 分发候选与中文材料

- Purpose：使普通用户拿到安装器或便携包时知道如何安装、恢复和定位故障。
- Outputs：普通用户安装器、portable、可信 WebView2 在线/离线引导、哈希/许可/依赖/构建信息、中文安装/恢复/卸载保留资料说明。
- 源码身份门：训练器从已推送feature完整commit打包源码/编译前端，含worker/引擎/路径实现；固定 `trainer_source_commit + launcher_build_commit + catalog_digest + recipe_digest + package SHA`，测试catalog不得冒充经验证main。
- 同包前置：同一交付二进制提供显式沙盒会话，只读测试配置由后端校验新根/固定端点/公钥/动作白名单；UI不能传任意URL/密钥/命令，普通根默认拒测试资产，生产信任不变。
- Completion criteria：优先用户可写目录；壳无需系统 Python/uv；包明确记录 catalog 签名和 Windows 代码签名的各自身份/状态。
- Validation：核对包组成、路径、许可与版本元数据；测试身份只用于夹具；维护者生产签名/渠道有无分别写证据和边界。
- Evidence：`<run-id>/M5/phase5/` 保存包 manifest/哈希、小型许可清单与说明；大包留重型根并记录定位。
- Failure handling：缺生产身份/渠道不冒充发布完成；可以保留可验证的开发候选与测试结果，正式准备缺口按授权治理报告。

### Phase 6：分发专项预验收、独立复审与推送

- 前置：承接CR-002的P1必须在相应系统动作及本Phase专项开始前实证就绪：合法可用、可启动的干净Windows，真实无Python/uv/训练器/缓存且缺WebView2基线、普通用户与恢复条件。M0原许可/启动blocked及失败保留；延期调度不计pass/skip，未齐不得开始对应专项或退出M5。
- Purpose：验证分发特有故障，固定 M6 将使用的候选包；不提前挪用最终从零验收结论。
- Outputs：干净 Windows 普通用户/缺 WebView2/中文空格路径、安装器和 portable 专项结果，壳更新故障矩阵，候选包身份与阶段报告。
- M6输入：核验实际run模块文件来自receipt锁定候选源码，禁止原main/dev加开发repo overlay；后续S状态文档提交可晚于build commit，只要源码/依赖/包字节未变，不因此重标包身份。
- Completion criteria：CR-002承接的P1已真实闭合，M5-A1–A8专项门有证据，无本阶段未关闭P0/P1；按Git治理完成代码C/状态S普通push并核对远端完整SHA。M6保持pending，全部开发结束后以最终同一包重建两轨基线并完整复验，CR-001边界不变。
- 身份门：签名/helper替换/恢复使用同SHA交付二进制共用路径；另SHA测试构建只补协议，不抵M6最终包A4/A8；无同包可审通路且无生产资源则对应格blocked。
- Validation：真实 OS/VM 配置与前置缺失留证；真实原生窗口/恢复；复审者核对 trial 写集和原字节；`ls-remote` 验证功能分支完整 SHA。
- Evidence：`<run-id>/M5/phase6/` 保存 OS/VM 身份、专项报告/review、候选包 SHA、提交/推送回执和 M6 输入 manifest。
- Failure handling：P1的OS/许可/缺组件基线或必要资产仍缺，停止相应系统动作和本Phase专项，保留blocked，不得把资源再次推迟到M6或签收M5。M6发现问题回修后生成新包、重跑受影响专项及最终链路，不沿用旧包通过结论。

代码提交 C 与状态提交 S 必须按 Git 治理分别普通推送和核对；保存仓库外 `baseline-final.json` 后才准阶段 done。任一回执缺失维持 in progress/blocked。

## 测试矩阵与资源

| 类别 | 本阶段强制内容 |
| --- | --- |
| unit | 更新状态机、锁归属、快照集合、令牌/PID、超时和恢复分支 |
| contract | 资产身份、helper/trial 协议、只读权限、壳确认与格式迁移分离 |
| integration | 真实 EXE 替换、GUI 自检、控制状态精确恢复、安装器/迁移互斥 |
| gray | 旧/新壳与 schema、installer/portable、WebView2有/无、失败前后字节对照 |
| real | Windows 原生文件占用、非管理员安装/卸载保留资料、helper/原生恢复界面 |
| Zero-Short | 先关闭CR-002承接的P1，再做真实干净OS缺WebView2分发专项；清空目录不能模拟OS，不代替M6最终同包从零全链路 |

- 机器/OS镜像许可、VM快照、WebView2来源、下载/磁盘峰值、最长自检/系统试验时长与回收策略按授权治理登记；数值未定不执行。
- 阶段新增网络提案≤5GiB，无额外GPU训练额度；OS/安装器/WebView2及重试均计量，资产不适合阶段或总预算先停并报告差额。
- 只读硬件识别不证明干净OS；M6保留最终同包从零GUI/分发验证，四引擎按CR-004仅冒烟，不再另建GPU根或做引擎重装训练。
- 轻证据根：`E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/<run-id>/M5/`；重型根拟 `F:/NextTrainerLauncherSandbox/<run-id>/`，本轮不创建。
- 清理先登记包身份/原字节/失败日志；只删批准根中的可重建候选或临时 VM，保留当前/回退壳、资料与唯一故障证据，不跟随联接。

## 决策记录

- Verified facts（已验证事实）：0.2 未证明独立壳更新或干净 Windows；设计要求只读 trial、精确状态快照和独立格式迁移。
- Active assumptions（待审核假设）：D5 签名清单先、M5独立壳；Windows x64/用户可写安装器+portable；生产资源由维护者另行提供。
- Locked decisions（已锁定边界）：本轮只规划；M5仅专项预验收；M6必须在全部开发阶段之后使用同一最终制品从零完整复验。
- Open questions（待确认）：OS/VM与WebView2介质、签名身份/生产渠道、trial允许写集、自检超时和最小可恢复状态集合。

## 关键制品与环境

- 必读：唯一总控/manifest、M5目标/清单、唯一规格、测试证据/授权/Git/变更控制治理。
- 主要代码域：Tauri/Rust 更新核心、独立 helper、打包配置、三页壳更新分组及中文说明；M0 冻结后按实况确定文件。
- 关键产物：helper/壳/installer/portable 身份、快照原字节、trial日志、格式迁移事务、M6候选交付 manifest。
- 真实验证：普通用户 Windows 与缺 WebView2 条件必须有机器证据；VM不能CUDA不伪装成GPU机，GPU轨留M6真实执行。

## 进度台账

- Overall progress：本阶段只有文档草案，Phase 1–6 全部 `pending`。
- 本节为步骤占位；唯一进度、变更/验证/风险、提交/远端 SHA 统一维护于总控 M5 条目。
- Validation status：helper/系统分发/真实占用/独立复审/commit/push 均 `not-run`；生产发布未开始。
- Residual risks：缺OS/签名资源、只读trial越权、精确恢复不全、安装包身份变化；必要门缺失不能靠文档标pass。

## 下一步动作

用户审核本计划且 M4 退出门通过后，按 M5 开工清单形成一次列明系统镜像、helper试验边界和维护者资源状态的预检结果；此前保持 `drafting/pending`。
