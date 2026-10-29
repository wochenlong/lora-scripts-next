# 目标 M5：独立壳与 Windows 分发实施验收计划

> **现行 v0.6 / [CR-006](../00_预检证据/change-control-governance.md#cr-006连续施工完成后统一沙盒验证与汇报)：** M1–M5 连续施工、最少快检、一次阶段基线后自动继续，M6 统一沙盒与最终汇报；不再等待候选/成本审核。四引擎仅冒烟，真实环境/GPU/训练项 skip+CR-004。以下原生、系统与故障验证内容供 M6 按影响合并选取，不是中间阶段实测门；产品保护和历史失败保留。本次侧聊只改文档，不启动执行。

- Plan ID：`desktop-launcher-full-20261028`；Version：`0.6`；更新：2026-10-29。
- 阶段：M5 独立壳与Windows分发；状态：`pending`；Execution readiness：`approved for execution`。
- 唯一进度：[总控目标索引](../00_总控目标索引.md)；唯一规格：[后续设计书](../../../design/desktop-launcher-next-design.md) §8–12。
- D1–D6 沿用已确定的实施选择；本阶段规划不授权创建生产密钥、发布资产或本轮实现。

## 目标、范围与依赖

回答：独立壳能否在 Windows 文件占用/首启失败/格式不兼容时精确恢复，并提供普通用户可用的安装包和便携包？
纳入：独立 helper（更新辅助程序）、只读 recovery trial（恢复试运行）、原字节快照、独立格式迁移、WebView2、安装器/便携包和分发专项预验收。
不纳入：以包生成代替上线、以测试签名代替维护者身份、自动迁移训练资料，以及替代 M6 所有开发结束后同一制品从零完整复验。
前置：M4 相关施工接口与快检齐备，壳/资料状态合同稳定。CR-006 将干净 Windows/缺 WebView2 实际资源检查移至 M6 对应系统专项前；资源不足不阻断 M5 编码/helper/安装包构建，原 P1 blocked 及失败继续保留，不冒充实测通过。
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
| M5-A8 | 构建可交付安装器/便携包并冻结 M6 身份；干净 OS/非管理员/缺 WebView2 与真实占用专项统一留 M6 | 把构建成功写成系统验收通过，或把缺测试资源变成 M5 停工门 |

同包前置：helper/签名/恢复须由同一交付二进制在显式隔离会话实际走共用执行路径；测试配置只读且后端固定根/端点/公钥/动作白名单，普通根拒测试资产，不收任意URL/命令。另SHA构建只补协议证据，不抵M6最终包A4/A8；无可审通路且无生产资源则必要格blocked。
源码身份门：冻结 `trainer_source_commit + launcher_build_commit + catalog_digest + recipe_digest + package SHA`；训练器归档含已推送feature实现及编译前端，不以原main/dev加开发overlay验收。S状态文档可后于build commit，不能改变包身份；M6实际run模块须匹配receipt锁定源码。

## 测试与证据

| 类别 | 按影响选择；真实综合验证留 M6 |
| --- | --- |
| unit（单元） | helper 状态机、快照集合、令牌/PID 绑定、超时与恢复分支 |
| contract（合同） | 壳资产签名、updater/installer 互斥、trial 只读边界与格式迁移协议 |
| integration（集成） | 真实 EXE 等待/替换/新壳确认/失败还原；与操作/迁移互斥 |
| gray（新旧对照） | 旧壳/新壳、旧/新状态、portable/installer、WebView2 有/无 |
| real（真实） | Windows 原生文件占用、普通用户安装/卸载保留资料、真实 helper 和 GUI 恢复 |
| Zero-Short（从新机短验） | 留 M6：合法干净 Windows/缺 WebView2 资源可用时验证；缺资源记该专项 blocked/not-run，继续其余链路，新根/PATH 不能代替 OS 条件 |

证据根：`E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/<run-id>/M5/`；保留包/EXE 身份、原字节前后比较、helper/trial 日志、机器快照、原生截图、许可和签名状态。
重型根拟 `F:/NextTrainerLauncherSandbox/<run-id>/`，本轮不创建；VM 快照、系统安装动作、下载/磁盘/最长试验时长及生产签名条件均以授权治理为准。
施工完成门：功能产物齐备、必要编译/类型检查与最少相关回归或小夹具通过，一次阶段 commit/普通 push/远端核对后继续；final_validation=pending M6。无需逐阶段真实矩阵或独立多轮复审。
- Git 保存：阶段代码与状态可同次提交，精确暂存后普通 push 并核远端 SHA；一次阶段保存即可，不强制 C/S 双重推送。
失败回退：恢复原 EXE 与精确控制状态；trial 不可读保持只读恢复；WebView2/签名/渠道缺失单列 not-run/blocked，不以开发包冒充生产发布。
残余风险：维护者签名身份/密钥/渠道、Windows 代码签名信誉和离线 WebView2 许可；缺生产资源时不得声明发布完成，M6 也不得因此省略。
