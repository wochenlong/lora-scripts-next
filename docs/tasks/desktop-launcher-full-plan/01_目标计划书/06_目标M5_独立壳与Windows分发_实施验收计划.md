# 目标 M5：独立壳与 Windows 分发实施验收计划

> 当前修订：0.2，2026-10-29，适用[CR-001用户GPU测试豁免](../00_预检证据/change-control-governance.md#cr-001用户批准跳过受资源限制的gpu验收)。Fast固定驱动不满足的GPU层、DiffSynth完整BF16模型/训练/权重子项授权`skip`，不作pass；Kohya/AI Toolkit及DiffSynth普通小张量等本机可执行验证保留。M0独立P3不再单独重试，CUDA验证进入对应引擎真实配方。干净Windows/安全/安装修复/同制品/阶段push均未豁免。下文0.1完成门在此明确范围内由本CR修订，其他合同继续有效；实时状态只见总控。

- Plan ID：`desktop-launcher-full-20261028`；Version：`v0.1`；更新：2026-10-28。
- 阶段：M5 独立壳与Windows分发；状态：`pending`；Execution readiness：`drafting`。
- 唯一进度：[总控目标索引](../00_总控目标索引.md)；唯一规格：[后续设计书](../../../design/desktop-launcher-next-design.md) §8–12。
- D1–D6 推荐方案仅为待审核假设；本阶段规划不授权创建生产密钥、发布资产或本轮实现。

## 目标、范围与依赖

回答：独立壳能否在 Windows 文件占用/首启失败/格式不兼容时精确恢复，并提供普通用户可用的安装包和便携包？
纳入：独立 helper（更新辅助程序）、只读 recovery trial（恢复试运行）、原字节快照、独立格式迁移、WebView2、安装器/便携包和分发专项预验收。
不纳入：以包生成代替上线、以测试签名代替维护者身份、自动迁移训练资料，以及替代 M6 所有开发结束后同一制品从零完整复验。
前置：M4 完成门通过；壳/资料状态兼容合同稳定；干净 Windows、普通用户、真实 EXE 占用与发布资源按[授权治理](../00_预检证据/risk-and-authorization-governance.md)确认。
M5 退出只解锁 M6；最终完成与发布结论须满足 M6 和维护者生产准备门。

## 验收标准

| 编号 | 可验收结果 | 失败条件 |
| --- | --- | --- |
| M5-A1 | helper 独立于训练器/Python/待覆盖 EXE；持锁停变更，等待明确 PID 退出 | 按名字杀进程、依赖坏 GUI 或任意后台进程 |
| M5-A2 | 快照显式枚举 registry/绑定、profile 描述、配置、操作索引及待升级控制文件，保存原字节/哈希 | 仅 JSON 重序列化、漏状态、备份被原位写穿 |
| M5-A3 | 新壳 trial 仅只读控制状态，独立事务目录写日志；凭事务 ID/随机令牌/进程身份确认 | 试运行启动训练器、安装/修复/迁移或修改原控制文件 |
| M5-A4 | EXE 替换或 GUI/恢复入口自检失败可恢复旧 EXE 和可读状态 | 旧 EXE 留存却不能读状态，错误宣称回退成功 |
| M5-A5 | 壳确认后格式升级是单独事务，同锁保护；失败精确恢复，不能恢复则留新壳恢复模式 | 把壳替换和资料迁移合并、不经备份不可逆升级 |
| M5-A6 | 普通用户安装器与 portable 均可启动；缺 WebView2 有可信在线/离线路径、失败日志 | 依赖系统 Python/uv、隐式全局设置、只有开发机运行 |
| M5-A7 | 包身份/哈希/许可/依赖/构建信息齐全；catalog 签名和 Windows 代码签名分别报告 | 无维护者生产身份却称正式签名发布完成 |
| M5-A8 | 干净机/非管理员/中文空格路径与真实占用故障专项通过；冻结 M6 待验同一制品 | 将本阶段专项 smoke 或旧构建证据写成 M6 最终通过 |

同包前置：helper/签名/恢复须由同一交付二进制在显式隔离会话实际走共用执行路径；测试配置只读且后端固定根/端点/公钥/动作白名单，普通根拒测试资产，不收任意URL/命令。另SHA构建只补协议证据，不抵M6最终包A4/A8；无可审通路且无生产资源则必要格blocked。
源码身份门：冻结 `trainer_source_commit + launcher_build_commit + catalog_digest + recipe_digest + package SHA`；训练器归档含已推送feature实现及编译前端，不以原main/dev加开发overlay验收。S状态文档可后于build commit，不能改变包身份；M6实际run模块须匹配receipt锁定源码。

## 测试与证据

| 类别 | 必须覆盖 |
| --- | --- |
| unit（单元） | helper 状态机、快照集合、令牌/PID 绑定、超时与恢复分支 |
| contract（合同） | 壳资产签名、updater/installer 互斥、trial 只读边界与格式迁移协议 |
| integration（集成） | 真实 EXE 等待/替换/新壳确认/失败还原；与操作/迁移互斥 |
| gray（新旧对照） | 旧壳/新壳、旧/新状态、portable/installer、WebView2 有/无 |
| real（真实） | Windows 原生文件占用、普通用户安装/卸载保留资料、真实 helper 和 GUI 恢复 |
| Zero-Short（从新机短验） | 干净 Windows 缺 WebView2 的分发专项预验收；M6 后续另做完整从零全链路 |

证据根：`E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/<run-id>/M5/`；保留包/EXE 身份、原字节前后比较、helper/trial 日志、机器快照、原生截图、许可和签名状态。
重型根拟 `F:/NextTrainerLauncherSandbox/<run-id>/`，本轮不创建；VM 快照、系统安装动作、下载/磁盘/最长试验时长及生产签名条件均以授权治理为准。
完成门：专项证据/报告完整→独立复审无 P0/P1→按[Git 基线治理](../00_预检证据/git-baseline-governance.md)范围 commit、普通 push 到 `origin feat/desktop-launcher` 并 `ls-remote` 核对；本轮不执行。
Git 退出门包括代码提交 C 与状态提交 S 的两次普通推送及完整 SHA 核对；最终仓库外 `baseline-final.json` 回执齐备才在唯一总控标 done，不能仅 C 到远端就解锁。
失败回退：恢复原 EXE 与精确控制状态；trial 不可读保持只读恢复；WebView2/签名/渠道缺失单列 not-run/blocked，不以开发包冒充生产发布。
残余风险：维护者签名身份/密钥/渠道、Windows 代码签名信誉和离线 WebView2 许可；缺生产资源时不得声明发布完成，M6 也不得因此省略。
