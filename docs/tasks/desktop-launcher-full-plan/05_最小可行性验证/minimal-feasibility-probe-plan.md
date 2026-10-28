# 最小可行性验证计划

- Plan ID：`desktop-launcher-full-20261028`；版本0.1；2026-10-29执行回填；状态：`blocked`（M0资源）。
- 执行结果：[实际报告](feasibility-probe-report.md)。已创建F沙盒并执行M0资源/安全探针；未下载模型、未安装引擎、未跑GPU。以下矩阵保留执行合同和首次起草时假设，不能替代最新结果。
- 唯一进度：[总控](../00_总控目标索引.md)；报告使用[探针模板](../00_预检证据/feasibility-probe-report-template.md)。GATE-11和GATE-14当前blocked；用户执行授权已生效。

## 1. 探针目的与执行次序

先验证最可能使计划失败的资源/路径/所有权假设，再进入开发。用户已启动M0安全准备和本节资源探针；M0完成报告刷新开工复盘，关闭阻塞后进入M1。M2引擎布局探针先于引擎修改。资源受阻不等于豁免关键探针或预先通过开工门。

## 2. 关键假设

| ID | 假设及失效后果 | 已有证据/缺口 | 探针/归属 |
| --- | --- | --- | --- |
| H1/P1 | 可取得真正干净Windows及缺WebView2条件；否则A1/M6不能完成 | 本轮未发现WindowsSandbox/vmconnect/VBoxManage/vmrun命令路径，vmcompute停止；不能据此断言所有VM均未装，OS资源仍unknown | P1，M0 |
| H2/P1 | 四引擎合法最小模型/数据在16G GPU和200GiB网络/300GiB峰值内可行 | 仅GPU16380MiB/驱动591.86与磁盘快照；模型许可/大小/显存未解析 | P2，M0先确认资产/最低显存/资源路径可行；完整模型加载/反向探针分别作为M2/M3前置门，不将架构未测项算pass |
| H3/P1 | 独立GPU根能完全隔离开发解释器/缓存且可CUDA | 普通Windows Sandbox显示GPU不证明CUDA | P3，M0 |
| H4/P1 | RuntimeLayout可保持junction安全且基础Python稳定 | 静态已知Fast resolve越界与run/.python生命周期冲突；未真实安装复现 | P4，M0安全夹具→M2完整门 |
| H5/P1 | GUI坏时控制worker仍可工作，且新inspect不写资料 | 旧status/preflight存在写入，部分repair force install、Kohya main_env冲突 | P5，M0合同清点→M2适配前验证 |
| H6/P1 | 取消/提交/精准修复事务可证明恢复；壳更新能回旧可读状态 | 旧长锁与拟定helper/新schema方案未经过本轮实测 | P6/P7，M1/M5前置最小样机 |

## 3. 探针矩阵与限额

以下“拟新增探针脚本”是M0准备产物，当前不存在时先实现并审查参数、路径和写入边界，再核对帮助/合同执行；不是现成产品命令。已有只读命令可以直接使用，但本轮不重复运行。每条输出保存到 `<元证据>/<run-id>/M0/probes/<probe-id>/` 或所属阶段对应目录。

| 探针 | 方法/命令 | 限额/输出与判据 | 失败退回与清理 |
| --- | --- | --- | --- |
| P1 干净OS资源 | 只读 `Get-ComputerInfo`、`Get-CimInstance Win32_ComputerSystem`、`Get-Service vmcompute`、`Get-Command WindowsSandbox,vmconnect,VBoxManage,vmrun -ErrorAction SilentlyContinue`；核查已有镜像/许可和可运行VM，禁止为探查启动未知服务 | ≤15分钟，无GPU；M0仅资产元信息，取得OS资源后验证真实缺Python/uv/训练器/缓存/WebView2的基线；未取得则blocked | 给出缺镜像/虚拟化/权利/安装条件的具体差额；不把未发现命令当作“没装VM”；OS下载需先入总预算 |
| P2 固定资产和容量 | 拟新增资产解析脚本读取四引擎固定recipe、wheel/Python/补丁/模型/数据/OS/WebView2清单；核对来源许可、固定摘要、实测/保守大小与解压/环境/快照峰值 | ≤30分钟、网络元数据≤100MiB；输出 `asset-lock.json/resource-projection.json/license-map.json`，按各卷和所有重试计量；超过总预算停止 | 资产无大小/哈希则不承诺可复现；超限先报告，不偷偷删组件或换弱模型 |
| P3 GPU最小可行性 | `nvidia-smi --query-gpu=name,uuid,memory.total,driver_version --format=csv` 只读；批准后在F新根用最小受管Torch环境验证设备、分配/计算小张量和同步结果，不借开发缓存，不下载四引擎完整模型 | M0网络总≤10GiB、GPU总≤10分钟、F新增预估≤30GiB；输出独立CUDA微探针/显存，不证明架构能训练。最低显存/配置来自P2可信资料；完整模型加载/反向探针分别在M2/M3预算内先于正式适配验收执行 | CUDA微探针失败则M0 blocked；架构资源不能可靠推定可行时列具体blocker；可行但未实测架构保持pending，不能填四引擎GPU pass |
| P4 路径与Python生命周期 | 拟新增最小RuntimeLayout夹具：中文空格根、run→profile联接、稳定Python/venv；在授权沙盒比较旧解析失败条件及新合同预期；测试run重建、路径越界/外部链接拒绝、基础Python引用 | ≤20分钟，无GPU、下载≤200MiB、F≤1GiB；M0先做不安装引擎的安全夹具，M2修改前再验证真实引擎路径；输出布局/解释器归属/前后树摘要 | 未过先修合同，不删resolve/relative_to路径保护；清理只移链接不遍历目标 |
| P5 只读与独立worker | 静态列出旧API写入及能力差异；最小标准库worker在GUI缺包情况下读固定布局并返回版本化合同；inspect前后字节树对比，受管Kohya禁止main_env写入，网页/桌面变更锁互斥 | ≤20分钟、无GPU/网络、F≤500MiB；只对合成夹具操作；M0输出能力/写入清单，M2完整适配前运行真正worker探针 | GUI/Torch导入依赖、隐式写入或锁冲突即P1；不得仅包装旧GET/status并标只读 |
| P6 取消与修复事务 | M1前最小本地HTTP/慢子进程样机：下载/解压/依赖/提交控制点、独立取消；依赖文件已改且state未提交注入退出，验证dirty/generation、同路径字节快照恢复与非目标摘要 | ≤20分钟，无GPU/外部网络，F≤1GiB；明确取消响应上限/提交延迟记录（由M0合同冻结），输出时序/进程树/锁/指针/恢复字节 | 取消被长锁阻塞或恢复只改状态即失败，回操作/事务设计；不杀外部同名程序 |
| P7 壳更新兼容 | M5前两个最小测试壳+独立helper，本地可信测试资产；文件占用、首启失败、令牌超时、schema不兼容；验证只读recovery-mode未写控制状态与失败后旧字节可读；设计最终同二进制的沙盒受限测试配置通路 | ≤20分钟，无GPU/外部网络，F≤1GiB；样机不同SHA只补协议证据；最终M6 A4/A8须同一二进制+只读受限配置（仅新标记根显式启用、默认生产根不变），摘要入证据 | 无法恢复精确状态即阻塞M5；最终无可审核同制品通路且无生产资源则A4/A8 blocked；D5内置+手动不豁免，不自动上线或创建生产密钥 |

P1–P5的M0准备总新增网络≤10GiB/GPU≤10分钟；各行上限同时受总额限制，不按行加总突破。资源清单需大模型才能验证且M0限额不够时，保留解析证据和具体差额供变更审批；不以“预算不够”豁免H2。P6/P7归所属阶段预算，不能用探针名义额外计量。所有F占用计入300GiB峰值、OS虚拟盘也计入。

## 4. 真实命令记录合同

探针实现后记录精确脚本commit/hash、参数、工作目录、受管根、解释器路径、stdout/stderr/退出码和原始时间。只读系统采集输出先脱敏机器/用户名；不得导出凭据、历史或真实用户文件。模型/数据清单必须提供来源、许可、SHA256、架构/精度和预计显存；没有这些不开始GPU下载/训练。

## 5. 通过、失败与复盘

P1/P2确认可用资源、合法资产/最低显存和预算预测，P3只证明独立CUDA微探针；三者使M0可判断后续资源路径是否可行，不证明完整模型架构已通过。完整模型加载/反向探针留在M2/M3预算内的阶段前置门，未测项保持pending；若P2不能给出可信可行路径则具体阻塞而非先下载四模型。P4/P5在M0只关闭安全夹具/合同清点门，M2真实布局和worker门仍待执行；M0不先实现完整引擎。M0通过后更新完成证据、GATE-11与开工复盘，不因本计划文件已存在就把GATE-14改pass。P6/P7必须在其阶段主要实现/验收前闭合；任何失败影响规格时走变更治理，保留旧证据与假设被推翻的原因。

每个探针使用[报告模板](../00_预检证据/feasibility-probe-report-template.md)；失败使用[failure report](../00_预检证据/failure-report-template.md)，清理使用[清理报告](../00_预检证据/evidence-cleanup-report-template.md)。保留首次raw、状态摘要和最小复现；不能跟随junction删除或删除真实资料。未执行/资源unknown明确写not-run/blocked，不填写pass或waived。

唯一下一步：按实际报告补齐M0实测资源、依赖/预算可行路径与CUDA微探针，资源门关闭后复审M0→M1；不重复申请已生效的执行授权。
