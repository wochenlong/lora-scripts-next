# 阶段 M5：独立壳与 Windows 分发执行前清单

> 当前修订：0.3，2026-10-29，适用[CR-001用户GPU测试豁免](../00_预检证据/change-control-governance.md#cr-001用户批准跳过受资源限制的gpu验收)。Fast固定驱动不满足的GPU层、DiffSynth完整BF16模型/训练/权重子项授权`skip`，不作pass；Kohya/AI Toolkit及DiffSynth普通小张量等本机可执行验证保留。M0独立P3不再单独重试，CUDA验证进入对应引擎真实配方。干净Windows/安全/安装修复/同制品/阶段push均未豁免。CR-001边界继续有效；CR-002仅调整P1时点，其他合同继续有效；实时状态只见总控。

> 0.3时点修订：[CR-002](../00_预检证据/change-control-governance.md)已由用户明确批准，原文“批准调整，继续开发（推荐）”。仅将P1合法可用干净Windows/缺WebView2资源实际就绪移至M5相应系统动作及Phase6分发专项验证开始前。原结果`blocked`及失败证据保留，`deferred by CR-002`仅是延期调度，不计pass/skip。其余M0真实证据、独审、完成报告及代码C/状态S普通推送和远端核验齐备，真实退出M0后才可开M1；M6最终同包双轨/A1–A10未豁免硬门、CR-001与原预算均不变。下文起草语境与旧时点按本段及直接更新条款解释，实时状态只见总控。

- Plan ID：`desktop-launcher-full-20261028`；Version：`0.3`；2026-10-29；状态：`pending`；Execution readiness：`drafting`。
- Required task book（必读任务书）：[M5 长程任务书](../02_长程任务书/阶段M5_独立壳与Windows分发_目标M5_长程任务书.md)。
- 唯一进度：[总控](../00_总控目标索引.md)；D1–D6 推荐方案为待审核假设；本轮不打包、不安装、不签名/发布。

## 通用硬门槛

- [ ] 已读取 README、manifest、总控、本阶段目标/任务书及[唯一规格](../../../design/desktop-launcher-next-design.md) §8–12。
- [ ] 已读取[测试证据治理](../00_预检证据/testing-and-evidence-governance.md)、[风险授权治理](../00_预检证据/risk-and-authorization-governance.md)、[Git 基线治理](../00_预检证据/git-baseline-governance.md)和gate/change-control规则。
- [ ] 用户已批准对应计划及资源；M4证据/独立复审无P0/P1/commit/push/远端完整SHA回执齐备。
- [ ] 已记录分支/HEAD/origin及dirty/untracked归属、制品和工作树hash；不覆盖已有成果、不夹带无关改动。
- [ ] 已复核各卷峰值/剩余空间、WebView2来源、试验墙钟上限与统一资源账本余额；CR-002承接的P1许可/启动/真实干净基线须在相应系统动作及Phase6专项开始前齐备，纯代码研发不冒充该项通过。
- [ ] 已确定run-id、元证据/重型绝对根与归属标记；只有获批执行后才创建，本轮不创建F盘沙盒。
- [ ] 六类测试均有专项用例/恢复步骤，关键原字节、原始失败和进程/监听器证据可保留。
- [ ] 安装器与壳更新系统动作仅在批准OS/VM/根内，清理仅受管临时物且不跟随联接。

## M5 专属硬门槛

- [ ] helper不依赖训练器/Python/待覆盖EXE；更新/安装器/迁移互斥和停止所有变更的规则已冻结。
- [ ] 进程归属以明确PID/创建时间等校验；外部同名进程及外部监听器sentinel就绪，绝不按名字/端口误杀。
- [ ] 快照显式列registry/绑定、profile描述、壳配置、操作索引及待升级控制文件，保存独立原字节/哈希和恢复位置。
- [ ] trial只读registry/receipt/profile/config/操作记录，仅独立事务目录可写日志；训练器启动/修复/安装/迁移入口禁用。
- [ ] 事务ID/随机令牌/进程身份确认、真实GUI/恢复入口自检、超时和错误令牌失败恢复用例已定。
- [ ] 壳确认与格式迁移分为两个事务且持同锁；失败可恢复精确旧状态，否则留新壳恢复模式，不承诺旧壳可读。
- [ ] 普通用户installer与portable、缺WebView2在线/离线路径、中文安装/恢复/卸载保留资料说明有验收输入。
- [ ] catalog签名与Windows代码签名分别记录；测试密钥不可冒充生产身份，维护者生产资源缺失单列且不公共发布。
- [ ] 同SHA二进制签名/helper/恢复测试通路就绪：显式沙盒会话+只读受限配置，后端固定fixture根/端点/公钥/动作，普通根拒测试资产；另SHA构建不抵A4/A8，无通路且无生产资源blocked。
- [ ] 相应系统动作及Phase6分发专项验证开始前，CR-002承接的P1已实际就绪：合法可用、可启动的干净Windows，真实无Python/uv/训练器/缓存且缺WebView2基线、非管理员/中文空格路径、恢复条件和真实EXE占用专项资源具备。原blocked及失败留证，不把延期记pass/skip；清空目录/限制PATH不能替代OS条件。
- [ ] M6同一候选制品manifest/SHA可冻结；M5只做专项预验收，所有开发之后的M6完整从零安装与四引擎GPU重验不删减。
- [ ] 已冻结trainer_source_commit/launcher_build_commit/catalog_digest/recipe_digest/package SHA；含feature源码与编译前端，不用原main/dev加开发overlay；S文档可后提交但包不变，M6核run文件与receipt来源。

## 证据、禁止事项与失败处理

- 元证据：`E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/<run-id>/M5/`；重型根拟`F:/NextTrainerLauncherSandbox/<run-id>/`。
- 禁止：trial改控制状态、壳未确认就迁移、只备份EXE不备份状态、JSON重序列化冒充原字节恢复、复制大模型作壳备份。
- 禁止：关闭外部服务、全局代理/PATH/驱动改动、无授权生产签名/上传、缺维护者身份仍称发布完成、以M5冒充M6。
- 任一硬门槛缺失：不启动对应系统/更新动作，写`<run-id>/M5/preflight-failure-report.md`，列资源/状态、最小阻塞、恢复及保留现场。P1未齐不得开始Phase6专项或退出M5，不得再以延期带入M6。
- 失败回退：还原旧EXE和精确可读状态；无法还原保持新壳只读恢复，报告P0/P1并阻止M6，不让旧壳碰未知schema。
- 退出门：专项证据/报告完整、独立复审无P0/P1，再按Git治理commit、普通push `origin feat/desktop-launcher`并`ls-remote`核对完整SHA。
- Git门同时核对代码C与状态S两次普通推送，仓库外`baseline-final.json`留最后完整SHA回执；仅代码到远端不算完成。
- 唯一总控记录候选身份/限制/远端回执，M6仍pending；改包后重新生成身份并重跑受影响专项和最终链路。

唯一下一步：用户审核且M4退出门通过后，形成列明OS资源、helper试验边界与维护者资源状态的M5开工结论。
