# 阶段 M5：独立壳与 Windows 分发长程任务书

> **现行 v0.6 / [CR-006](../00_预检证据/change-control-governance.md#cr-006连续施工完成后统一沙盒验证与汇报)：** M1–M5 连续施工、最少快检、一次阶段基线后自动继续，M6 统一沙盒与最终汇报；不再等待候选/成本审核。四引擎仅冒烟，真实环境/GPU/训练项 skip+CR-004。以下原生、系统与故障验证内容供 M6 按影响合并选取，不是中间阶段实测门；产品保护和历史失败保留。本次侧聊只改文档，不启动执行。

## 本阶段现行施工与验收安排

- M5 完成功能实现与最小快速检查即可保存阶段基线并继续 M6；真实综合验收统一留到 M6。
- 编译/类型检查与受影响回归按需选择；contract/integration 采用小夹具，不要求逐阶段原生实装、六类测试齐跑或多轮审计。
- 一般失败自主排查、修复并继续；暂停有风险的具体操作，仍推进独立施工。无模型/GPU需求，不改产品资料和信任守护。
- 施工状态与 `final_validation=pending M6` 分开记录；最终仅由 M6 的实际结果签验收，不能把快检冒充实测。
- 干净 Windows/缺 WebView2 资源只约束对应系统专项；资源不足记录 blocked，完成其余可执行链后统一报告。

## 计划元数据

- Plan ID：`desktop-launcher-full-20261028`；Version：`0.6`；Last updated：2026-10-29 Asia/Shanghai。
- Canonical progress file：`E:/OpenSourceTeamWork/workspace/branches/dev/docs/tasks/desktop-launcher-full-plan/00_总控目标索引.md`。
- Related handoff file：`none`；Current branch：`feat/desktop-launcher`。
- Current active phase：`none`；本阶段及各 Phase：`pending`；Execution readiness：`approved for execution`。
- 目标：[M5 实施验收计划](../01_目标计划书/06_目标M5_独立壳与Windows分发_实施验收计划.md)；开工前读取[阶段清单](../04_阶段开工清单/阶段M5_独立壳与Windows分发_执行前清单.md)。
- 唯一规格：[后续设计书](../../../design/desktop-launcher-next-design.md) §8–12；D1–D6 沿用已确定实施选择。

## 目标

实现独立壳的可信替换、只读试运行和精确状态恢复，形成普通用户安装器/便携包及中文交付材料；以构建和最小协议检查冻结 M6 统一沙盒验证的候选制品。

## 范围与约束

- In scope（纳入）：独立 helper、升级互斥、原字节快照、trial 确认、壳/数据迁移分离、WebView2 与 Windows 分发。
- Out of scope（不纳入）：生产密钥代建/代用、公共发布上传、任意全局配置改动、把本阶段专项测试当成 M6 最终完成。
- 前置：M4 相关施工接口与快检齐备，状态兼容合同明确；M5 不依赖干净 OS 资源先完成代码/helper/分发构建。
- 遵循[测试证据治理](../00_预检证据/testing-and-evidence-governance.md)、[资源授权治理](../00_预检证据/risk-and-authorization-governance.md)、[Git 基线治理](../00_预检证据/git-baseline-governance.md)。
- 本次侧聊只改文档，未构建/运行/提交；未来主执行者按既定授权连续施工、打包及阶段保存，生产发布仍需另行授权。
- 未来执行只作用批准沙盒/VM；只等待归属明确的 PID/创建时间，不按进程名或端口杀其他程序；不复制模型/数据集作为壳升级备份。

## 执行阶段

各 Phase 保留产品输出与行为要求。施工期只做编译/类型检查、相关最小回归或小夹具；Validation 中的原生实装、系统环境、完整故障组合统一留 M6 合并选取，不阻断本阶段施工保存和后续编码。

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

### Phase 6：分发构建快检与阶段保存

- Purpose：完成 M5 全部施工，冻结 M6 统一验证所需制品和身份。
- Outputs：helper、EXE、安装器/便携包、中文材料与来源清单；最小构建/协议结果和阶段基线回执。
- Completion criteria：M5 功能和必要快检齐备，一次精确 commit/普通 push/远端 SHA 核对；construction_status=done、final_validation=pending M6，自动继续。
- Validation：核对包组成/许可/元数据及最少 helper/trial/精确恢复小夹具；原生替换、系统/缺 WebView2 与占用故障统一留 M6 合并选取，不在本阶段重复实装。
- M6 输入：冻结 trainer_source_commit、launcher_build_commit、catalog_digest、recipe_digest、package_sha256；实际运行模块来自 receipt 锁定候选，不用旧 main/dev 加开发 overlay。
- 系统资源：CR-006 将 P1 干净 Windows/缺 WebView2 实际就绪移到 M6 对应系统专项前；原 blocked/失败保留，不阻断本阶段编码/helper/打包或退出施工。
- 身份门：A4/A8 最终同二进制实测；测试通路只作用显式新标记沙盒，普通根拒测试信任，不自动生产发布。
- Evidence：`<run-id>/M5/phase6/` 保存构建摘要、制品清单与一次基线回执；真实系统结果留 M6。
- Failure handling：构建/协议错误自主修复，暂时网络失败保留待补状态并继续可做工作；真实风险只暂停对应动作。M6 修复改包后只补受影响链，不沿用旧包结论。

## 测试选择、最终验证参考与资源

| 类别 | 按影响选择；真实综合验证留 M6 |
| --- | --- |
| unit | 更新状态机、锁归属、快照集合、令牌/PID、超时和恢复分支 |
| contract | 资产身份、helper/trial 协议、只读权限、壳确认与格式迁移分离 |
| integration | 真实 EXE 替换、GUI 自检、控制状态精确恢复、安装器/迁移互斥 |
| gray | 旧/新壳与 schema、installer/portable、WebView2有/无、失败前后字节对照 |
| real | Windows 原生文件占用、非管理员安装/卸载保留资料、helper/原生恢复界面 |
| Zero-Short | 留 M6：合法干净 Windows/缺 WebView2 资源可用时执行；缺资源仅阻断该专项，完成其余链路后统一报告，新根不能冒充 OS 条件 |

- 机器/OS镜像许可、VM快照、WebView2来源、下载/磁盘峰值、最长自检/系统试验时长与回收策略按授权治理登记；数值未定不执行。
- 阶段新增网络提案≤5GiB，无额外GPU训练额度；OS/安装器/WebView2及重试均计量，资产不适合阶段或总预算先停并报告差额。
- 只读硬件识别不证明干净OS；M6保留最终同包从零GUI/分发验证，四引擎按CR-004仅冒烟，不再另建GPU根或做引擎重装训练。
- 轻证据根：`E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/<run-id>/M5/`；重型根拟 `F:/NextTrainerLauncherSandbox/<run-id>/`，本轮不创建。
- 清理先登记包身份/原字节/失败日志；只删批准根中的可重建候选或临时 VM，保留当前/回退壳、资料与唯一故障证据，不跟随联接。

## 决策记录

- Verified facts（已验证事实）：0.2 未证明独立壳更新或干净 Windows；设计要求只读 trial、精确状态快照和独立格式迁移。
- Active assumptions（实施假设）：D5 签名清单先、M5独立壳；Windows x64/用户可写安装器+portable；生产资源由维护者另行提供。
- Locked decisions（已锁定边界）：M5 完成功能/构建/最小快检后继续；M6 在全部施工后统一做最终同包沙盒验证。
- Open questions（待确认）：OS/VM与WebView2介质、签名身份/生产渠道、trial允许写集、自检超时和最小可恢复状态集合。

## 关键制品与环境

- 必读：唯一总控/manifest、M5目标/清单、唯一规格、测试证据/授权/Git/变更控制治理。
- 主要代码域：Tauri/Rust 更新核心、独立 helper、打包配置、三页壳更新分组及中文说明；M0 冻结后按实况确定文件。
- 关键产物：helper/壳/installer/portable 身份、快照原字节、trial日志、格式迁移事务、M6候选交付 manifest。
- 真实验证：干净 Windows/缺 WebView2 条件必须有真实机器证据；资源不足最终单列 blocked/not-run，四引擎仅冒烟，不建 GPU 轨。

## 进度台账

- Overall progress：本阶段尚未施工，已获准按依赖连续推进，Phase 1–6 全部 `pending`。
- 本节为步骤占位；唯一进度、变更/验证/风险、提交/远端 SHA 统一维护于总控 M5 条目。
- Validation status：helper/系统分发/真实占用/独立复审/commit/push 均 `not-run`；生产发布未开始。
- Residual risks：缺OS/签名资源、只读trial越权、精确恢复不全、安装包身份变化；必要门缺失不能靠文档标pass。

## 下一步动作

M4 相关施工和快检齐备后完成 M5 helper/独立壳/分发构建与最小协议检查，一次保存阶段基线后继续 M6；无需再次审核或等待干净 OS 资源才能编码。
