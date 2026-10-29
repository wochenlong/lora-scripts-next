# 阶段 M5：独立壳与 Windows 分发执行前清单

> **现行 v0.6 / [CR-006](../00_预检证据/change-control-governance.md#cr-006连续施工完成后统一沙盒验证与汇报)：** M1–M5 连续施工、最少快检、一次阶段基线后自动继续，M6 统一沙盒与最终汇报；不再等待候选/成本审核。四引擎仅冒烟，真实环境/GPU/训练项 skip+CR-004。以下原生、系统与故障验证内容供 M6 按影响合并选取，不是中间阶段实测门；产品保护和历史失败保留。本次侧聊只改文档，不启动执行。

- Plan ID：`desktop-launcher-full-20261028`；Version：`0.6`；2026-10-29；状态：`pending`；Execution readiness：`approved for execution`。
- Required task book（必读任务书）：[M5 长程任务书](../02_长程任务书/阶段M5_独立壳与Windows分发_目标M5_长程任务书.md)。
- 唯一进度：[总控](../00_总控目标索引.md)；D1–D6 沿用已确定的实施选择；本轮不打包、不安装、不签名/发布。

## 通用硬门槛

- [ ] 已读取 README、manifest、总控、本阶段目标/任务书及[唯一规格](../../../design/desktop-launcher-next-design.md) §8–12。
- [ ] 已读取[测试证据治理](../00_预检证据/testing-and-evidence-governance.md)、[风险授权治理](../00_预检证据/risk-and-authorization-governance.md)、[Git 基线治理](../00_预检证据/git-baseline-governance.md)和gate/change-control规则。
- [ ] 用户 CR-006 已明确连续施工；M0 已完成，前序相关施工接口/快检与阶段基线按总控核对；无需候选/成本后再次审批。
- [ ] 已记录分支/HEAD/origin及dirty/untracked归属、制品和工作树hash；不覆盖已有成果、不夹带无关改动。
- [ ] 已核对本阶段构建/小夹具的空间和账本余额；P1 干净 OS/缺 WebView2 实际资源检查移到 M6 系统专项前，不阻断 M5 施工。
- [ ] 已确定run-id、元证据/重型绝对根与归属标记；只有获批执行后才创建，本轮不创建F盘沙盒。
- [ ] 施工只做受影响编译/类型检查与最少回归/小夹具；综合实测留 M6，一次基线后自动继续，不强制六类齐跑或多轮审计。
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
- [ ] 已将干净 Windows/缺 WebView2、非管理员/中文空格路径和真实占用的系统专项安排在 M6；资源不足只影响对应专项，原 blocked 与失败保留，不把新目录/PATH 当干净 OS。
- [ ] M6同一候选制品manifest/SHA可冻结；所有开发之后仍以最终同包从零验证GUI/分发关键链，四引擎按CR-004仅冒烟，不做GPU重验。
- [ ] 已冻结trainer_source_commit/launcher_build_commit/catalog_digest/recipe_digest/package SHA；含feature源码与编译前端，不用原main/dev加开发overlay；S文档可后提交但包不变，M6核run文件与receipt来源。

## 证据、禁止事项与失败处理

- 元证据：`E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/<run-id>/M5/`；重型根拟`F:/NextTrainerLauncherSandbox/<run-id>/`。
- 禁止：trial改控制状态、壳未确认就迁移、只备份EXE不备份状态、JSON重序列化冒充原字节恢复、复制大模型作壳备份。
- 禁止：关闭外部服务、全局代理/PATH/驱动改动、无授权生产签名/上传、缺维护者身份仍称发布完成、以M5冒充M6。
- 对应系统资源缺失不启动该系统动作，保留事实并继续 M5 编码/helper/打包；到 M6 完成可执行链后统一报告资源边界，不额外设置阶段审批。
- 失败回退：还原旧EXE和精确可读状态；无法还原保持新壳只读恢复，修复该缺陷并保留现场，不阻止独立施工；最终不能宣称该路径已通过，不让旧壳碰未知schema。
- 施工退出：功能输出、必要快检和一次阶段基线齐备后自动继续；final_validation=pending M6，真实综合验证不作中间前置。
- Git 保存：阶段代码与状态可同次提交，精确暂存后普通 push 并核远端 SHA；一次阶段保存即可，不强制 C/S 双重推送。
- 唯一总控记录候选身份/限制/远端回执，M6仍pending；改包后重新生成身份并重跑受影响专项和最终链路。

唯一下一步：按本阶段功能清单完成 M5 施工和最小快检，保存一次开发基线后自动推进 M6；不等待候选/成本审核。
