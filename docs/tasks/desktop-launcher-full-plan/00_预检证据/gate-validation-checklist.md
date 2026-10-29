# 编号化门禁审查清单

> 当前修订0.3：CR-002已由用户明确批准；P1实际资源就绪承接M5相关系统动作/专项前，历史运行blocked保持。CR-001不变，M6同包从零硬门完整保留。以下0.2语境由本次时点修订覆盖；其他门继续有效。

> 当前修订0.2（2026-10-29）：用户已批准[CR-001资源受限GPU验收skip](../00_预检证据/change-control-governance.md#cr-001用户批准跳过受资源限制的gpu验收)，实际Goal已恢复active。仅豁免列明的Fast/DiffSynth GPU/完整模型训练子项，其他必测和干净Windows保留；旧0.1阻塞/无豁免文字是历史，不覆盖本修订。阶段完成必须明确授权skip边界，不能报GPU全通过。

Plan `desktop-launcher-full-20261028` / v0.3；2026-10-29执行回填；Execution readiness：`executing`（CR-002后M0退出收尾）。用户已授权并建立实际Goal；任何文档结构pass均不代表产品或资源实测pass。

## 计划就绪门 GATE-00–GATE-14

| Gate ID | 描述 | 必需证据 | 当前状态 | 说明与退回路径 |
| --- | --- | --- | --- | --- |
| GATE-00 | 来源与现场事实可信 | preflight-source-review、branch/HEAD/92文件快照 | pass | 规划所需事实已读；issue只用保存快照 |
| GATE-01 | 计划根/证据根/授权边界明确 | manifest、风险治理、M0/audit-freeze | pass | 用户已启动0.1及推荐方案/预算，排除项不变 |
| GATE-02 | 总目标可验收 | 总控目标、A1–A10追踪 | pass | 最终四引擎/干净OS/远端基线都有硬门 |
| GATE-03 | 范围、顺序和保护明确 | M0–M6依赖、范围/变更治理 | pass | 无私自放开平台/真实资料 |
| GATE-04 | 每目标有具体产物 | 7份目标计划及索引 | pass | 文档覆盖，不代表实现完成 |
| GATE-05 | 每目标有测试和证据 | 6类测试/验收映射 | pass | 必测not-run不可算done |
| GATE-06 | 每阶段可独立指导施工 | 7份长程任务书 | pass | Phase有输出/验收/证据/失败处理 |
| GATE-07 | 完成门、失败和保存闭环 | 任务书、完成模板、Git协议 | pass | C/S提交回执、失败阻断下阶段 |
| GATE-08 | 每阶段有硬前置清单 | 7份开工清单 | pass | M0可批准安全准备，M1需M0门通过 |
| GATE-09 | 证据与测试状态真实 | testing-and-evidence-governance | pass | 区分pass/fail/not-run/blocked等 |
| GATE-10 | 清理/预算不破坏现场 | 风险/测试治理、清理模板 | pass（规则） | 额度已随执行指令生效；实账和有条件串行预算路径已独审，后续每阶段获取前继续关闭依赖锁 |
| GATE-11 | 高风险前提最小实证 | probe-plan/report、资源清单、P1–P7结果、CR-001/002 | pass-with-boundary（M0范围） | P1实际就绪延期M5，原blocked留证；预算可行路径已独审；指定GPUskip/P3分期，P4/P5安全基线有界；exit-M0-final-review-CR002.md已核无本阶段未关P0/P1 |
| GATE-12 | Goal无缺项且与主计划一致 | Goal、用户指令、独立审查、静态验证 | pass（执行记录） | 沿用实际Goal，工具blocked偏差如实记载；按用户继续开发及0.3/CR-001/002执行；不代表阶段或产品通过 |
| GATE-13 | 变更/权限/反漂移治理完整 | change-control、risk、用户审计单 | pass | 用户批准与资源差额显式记录 |
| GATE-14 | 开工前最终复盘与用户批准 | 06复盘、用户审核、M0最小证据 | pass-with-boundary（进入M1前验证范围） | CR-002已获批并同步M5承接；最终独审已通过，C/S未齐前EXIT-M0仍pending |

分期说明：文档审计通过可以批准M0准备与探针，不能绕过GATE-11/14。M0保留合法资产/预算可行性和安全布局/能力清点事实；P1干净OS实际就绪依CR-002在M5相关系统动作/专项前实证，原M0失败不改pass；M1的P6取消事务样机、M2的P4/P5真实布局/worker、M5的P7壳恢复样机在对应主实现前各自再过技术门。未来功能尚未实现的验证不倒填M0已过。GATE-14在M0只可对“进入M1且后续技术门继续阻断”的范围给pass-with-boundary，不能一次替所有未来阶段签收。

## 阶段退出门

| Gate ID | 阶段 | 当前状态 | 必需证据/禁止越门 |
| --- | --- | --- | --- |
| EXIT-M0 | 审核冻结与开发基线 | pending | 审核/备份/构建/WIP已保存；P1按CR-002承接M5，其余M0最终复审/完成报告/C与S远端回执齐后才解锁M1 |
| EXIT-M1 | 可靠安装与精准修复 | pending | 实际取消/网络/Range/中断恢复/GUI精准修复/无P0P1/完成清理/C与S回执 |
| EXIT-M2 | 首批引擎真实闭环 | pending | RuntimeLayout/worker只读与坏GUI独立/两引擎GPU短训练和修复/完成清理/C与S回执 |
| EXIT-M3 | 四引擎与可信更新 | pending | 另两引擎GPU真实闭环/四引擎身份/签名历史与离线矩阵/完成清理/C与S回执 |
| EXIT-M4 | 资料导入与兼容回退 | pending | 源不变/路径与冲突/中断/schema三元绑定回退/完成清理/C与S回执 |
| EXIT-M5 | 独立壳与Windows分发 | pending | CR-002承接P1合法可用干净OS必须在相应系统动作/专项前闭合，无资源停门；helper精确状态恢复/安装器WebView2专项/冻结交付集合/生产身份边界/完成清理/C与S回执 |
| EXIT-M6 | 从零沙盒最终验收 | pending | 同包双轨A1–A10全pass/四引擎重装训练/权重/退出保护/最终材料清理/C与S完整远端回执 |

通用条件：必测真实证据、独立审查、无未解决P0/P1、阶段完成报告/清理报告/资源账本、精确commit/push且远端SHA确认。推送失败即未完成，产品通过不抵扣Git保存门。最终M6仅允许CR-001明确授权的GPU子项skip，其他必测不得靠缺资源或历史报告越门。所有执行进度只在总控更新。
