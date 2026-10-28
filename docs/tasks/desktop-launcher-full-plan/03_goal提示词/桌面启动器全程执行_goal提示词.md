# 桌面启动器全程执行 Goal 提示词

> 当前修订0.2（2026-10-29）：用户已批准[CR-001资源受限GPU验收skip](../00_预检证据/change-control-governance.md#cr-001用户批准跳过受资源限制的gpu验收)，实际Goal已恢复active。仅豁免列明的Fast/DiffSynth GPU/完整模型训练子项，其他必测和干净Windows保留；旧0.1阻塞/无豁免文字是历史，不覆盖本修订。阶段完成必须明确授权skip边界，不能报GPU全通过。

Plan `desktop-launcher-full-20261028` / v0.2。实际Goal于2026-10-28建立，曾因资源设为blocked；2026-10-29用户回复CR-001后已恢复active。唯一进度为[总控索引](../00_总控目标索引.md)，M0未豁免门仍需通过才能进入M1。

## 使用与授权

先审核[用户审计单](../07_用户审计单.md)。用户明确批准计划并要求执行后，将批准版本、预算和限制写入总控；不把“写Goal”“审计Goal”当作开工。若启动消息已经明确批准并执行，不重复询问同一授权。

批准只先解锁M0安全准备和可行性探针；M0关闭资源/高风险门、更新开工复盘并完成基线push后，再持续M1–M6，不逐阶段暂停等待常规确认。

## 可复制的完整提示词

```text
/goal 执行 E:/OpenSourceTeamWork/workspace/branches/dev/docs/tasks/desktop-launcher-full-plan 中定义的“桌面启动器完整交付”全程任务，按 M0–M6 逐步完成；每阶段提交并push保存开发基线，全部开发阶段后在新沙盒中从零实测最终同一交付包。

工作副本 E:/OpenSourceTeamWork/workspace/branches/dev；预期分支 feat/desktop-launcher；预期origin https://github.com/wochenlong/lora-scripts-next.git。先核对当前状态，不从HEAD覆盖已有未提交成果，不git reset/clean，不丢失无关dirty/untracked文件。

【授权检查】
只有用户明确批准本计划版本、设计/预算边界并要求开始执行时才启动。当前若仍处审计且没有新的执行授权，只列待审项，不创建或推进实际开发Goal。当前执行消息若已明确批准，则补录授权而不再次询问。本计划批准后，范围内编码、测试、本地提交和origin/feat/desktop-launcher阶段push均为持续授权；正式发布、合并和对外消息另行处理。

【最小必读与唯一真相】
1. docs/tasks/desktop-launcher-full-plan/README.md、plan-manifest.md、00_总控目标索引.md、07_用户审计单.md。
2. docs/design/desktop-launcher-next-design.md（唯一规格）及desktop-launcher-next-review.md（D1–D6实际审核记录）。
3. 本计划00_预检证据中的gate-validation-checklist.md、testing-and-evidence-governance.md、risk-and-authorization-governance.md、git-baseline-governance.md、change-control-governance.md。
4. 05_最小可行性验证/minimal-feasibility-probe-plan.md及feasibility-probe-report.md、06_开工前最终复盘报告.md。
5. 01_目标计划书/00_目标计划书索引.md，按索引读取当前阶段目标/任务书/开工清单。不要一次加载全部代码和历史原始日志。
历史desktop-launcher-foundation-plan已完成，只作事实来源，不重开其阶段。总控索引是唯一canonical progress file，其他报告不能擅自替代。

【CR-001用户修订，优先于下文原0.1验收合同】
用户已对缺少适合Fast/DiffSynth配方的CUDA机器明确回复“没有合适机器，跳过这个测试”。Fast固定驱动不满足的GPU运算/完整模型加载/反向/短训/权重、DiffSynth完整BF16模型加载/反向/短训/权重，在M2/M3/M6分别记skip+CR-001+资源原因，不计pass、不宣称四引擎全GPU训练通过。
安装/导入/诊断/精准修复/隔离/回退及硬件限制拒绝行为仍须实现和实测。Kohya/AI Toolkit本机可执行的GPU/短训、DiffSynth普通小张量保留；不能因TE显存大就skip基础运算。M0独立P3准备不再重试，历史超时/partial保留，CUDA基础验证在相应M2/M3实际引擎配方内先验证。M0仍须关闭未豁免的干净Windows/合法安装依赖/预算/安全门，CR不自动解锁M1。
所有非CR指定的A1–A10子项、最终同包干净OS从零、原生窗口、签名/helper、资料保护、阶段commit/push继续必测。最终完成是获批调整后的工程验收完成并逐项列skip与未验证训练能力；仅允许本CR列明skip，其余not-run/unknown/blocked/skip不能算完成。总预算不增加。工具objective若仍保留v0.1，后续用户指令和本修订优先；不创建重复Goal，不篡改历史证据。

【完整顺序与阶段输出，以上CR指定GPU子项按修订执行】
M0 审核冻结与开发基线：记录批准，固定范围/预算/allowlist，保护92文件快照所代表的原有成果，核查干净Windows/GPU/模型/签名渠道资源，完成最小可行性探针与开工门；将现有底座和计划按范围提交push。
M1 可靠安装与精准修复：操作ID/事件/持久状态，独立取消和跨进程lease，真实阶段进度，网络一致语义，Range续传与缓存哈希，重启恢复，GUI锁定配方及最小依赖闭包修复，dirty/generation保护。
M2 首批引擎真实闭环：RuntimeLayout与稳定Python映射先验证；独立控制worker不依赖坏GUI；Kohya standalone与Anima Fast配方锁定、真实安装/诊断/精准修复、GPU运算和短训练，证明互不干扰。
M3 四引擎与可信更新：AI Toolkit、DiffSynth完成同一合同与GPU实测；签名清单、防重放/过期/轮换/撤销，历史receipt离线可信，非阻塞版本更新。生产未配密钥时只走已批准的内置清单/手动升级边界，不谎称生产自动更新上线。
M4 资料导入与兼容回退：只读扫描、计划预览、复制/引用、源指纹、冲突、容量与中断；profile升级绑定release+profile+environment实例，失败回旧资料；旧源和外部路径不被修改/删除，不默认接管旧venv。
M5 独立壳与Windows分发：独立helper、精确状态快照、只读新壳试运行确认、失败还原；格式迁移单独事务；普通用户安装器、便携包、WebView2引导、许可/构建身份/中文使用及排障；完成分发专项预验收并固定最终候选制品SHA。
M6 从零沙盒最终验收：在M0–M5全部通过及push之后，启动新沙盒/干净快照，仅使用最终同一包；干净Windows安装轨与独立GPU根四引擎重新安装训练轨联合覆盖A1–A10，重跑故障恢复、资料保护、更新回退、退出回收，形成最终报告和最后基线push。

【每阶段执行合同】
开工前读对应04_阶段开工清单，核对前序EXIT门和完整远端SHA。按02_长程任务书执行，维护unit/contract/integration/gray/real/Zero-Short矩阵，任何not-applicable写理由；必测not-run/unknown/blocked/skip不能算pass。
每次实质进展更新唯一总控：当前阶段、具体改动、已执行验证/失败、决策/偏差、剩余风险和唯一下一动作。阶段结束生成完成报告、独立复审、清理报告和基线回执；先验证再保存Git基线。不是只写报告或完成第一批引擎就结束。
EXIT-M0至EXIT-M6均须：规定行为实际通过；无未解决P0/P1；原始失败和修复结果留证；本阶段代码/报告commit并普通push成功；ls-remote核对远端完整SHA一致；进度状态文档也已推送。细则遵守git-baseline-governance.md，不无限自引用提交SHA。
GitHub网络每命令使用http.proxy和https.proxy=http://127.0.0.1:11809，不改全局设置。精确allowlist暂存，不git add -A，不force push，不改写已推送历史；认证/网络/非快进失败不能虚报保存成功。

【并行与上下文】
主会话负责领域理解、集成、跨模块合同、最终验收和push。尽早把互不重叠写入范围分给子代理，如Rust操作/下载、Python引擎、Vue交互/原生验收；先固定合同再并行，禁止各代理覆盖他人改动。推送与集成保持单一写入者。
不要等上下文接近极限才压缩，按约60%准备、最晚70%前完成的策略主动精简。切换前更新总控并产出续接摘要，含目标、已完成、决策原因、文件/路径、待办、风险/阻塞/待确认。续接只读最小必要上下文，不重复所有历史调研。

【资源、隔离与真实证据】
元证据 E:/OpenSourceTeamWork/workspace/tools/launcher-full-20261028/<run-id>/M0..M6；重型根按获批方案 F:/NextTrainerLauncherSandbox/<run-id>/。执行前重新核对空间/资源，使用独立缓存；预算按risk-and-authorization-governance.md累计，网络重试/VM镜像也算。
拟定总预算：网络200GiB、F峰值300GiB并留100GiB、E新增元证据5GiB并留20GiB、GPU180分钟、每次短训练20 optimizer steps或10分钟取先，同一时刻1个GPU任务，失败重试遵守文档。实际以用户批准记录为准，不自行扩大。
M0先核查合法模型/最低显存依据/容量、干净Windows资源可用，并运行独立CUDA微探针；完整模型加载/前反向分M2/M3按阶段预算在对应架构适配前验证，未测保持pending，不要求M0先下载四模型或先做完引擎。缺资源写清差额，不擅自购买云GPU、访问未授权服务器、修改真实用户资料或创建生产签名密钥。只用合成/合法许可数据。允许测试信任根须隔离且明确标测试，普通包不默认信任它。
最终“从零”要有OS/快照和软件缺失证据；隐藏PATH和空目录仅作辅助。标准Windows Sandbox的GPU能力不自动证明CUDA可用；若使用独立GPU Windows环境，报告明确联合矩阵，不能冒充同一干净系统。四引擎分别保留解释器/配方/依赖/GPU运算/训练命令/日志/可加载输出权重证据。GUI 200、模块导入或JSON healthy不能替代短训练。
最终候选包SHA固定，禁止用M2/M3已有环境代替M6重装。另SHA测试信任构建只能补协议证据，不能抵扣最终包A4/A8；最终包须同一二进制以显式受限且记录摘要的隔离新沙盒测试配置验证签名/helper，默认生产信任根不变、普通根拒绝测试资产，不开放任意URL/命令。无安全测试通路且无生产资源则必测blocked。修改制品后重新打包并重跑受影响验收，公共安装/信任合同变化重跑M6完整关键链路。核对原生窗口/按钮和HTTP/API/HTML/JS/CSS，退出验证自己的Job/监听器回收且外部服务保留。
实际安装的trainer release必须含本功能worker/路径/引擎代码：M0固定候选策略，M2/M3从已推送完整feature commit生成源码/编译前端归档并锁SHA/recipe；测试catalog显式标候选，不冒合格main。禁止原始main/dev安装加开发repo overlay或PYTHONPATH借用来抵扣验收。M5/M6记录trainer_source_commit、launcher_build_commit、catalog/recipe_digest、package SHA，实际run模块文件须来自receipt锁定归档；后续状态S提交不冒充包构建身份。
清理只针对本任务新建且已核对的绝对路径，不递归跟随junction，不删profile/外部数据/失败关键证据；空间不足优先安全保留元数据并停止相关任务。

【门禁、失败与持续执行】
M0前的文档审核通过不等于技术probe已过。先做M0获批安全准备和probe，更新GATE-11/GATE-14与开工复盘后再M1。M2路径probe不过不得简单放宽路径安全；取消不得等同长操作锁；修复不得默认强制整包重装。
普通实现选择和预算内问题自主解决，不逐阶段索要确认；进度用简短commentary持续报告，最终或真实阻塞才交付final。资源不可用、超预算、未授权P0/P1、不可恢复数据/信任风险或验收必须降级时，停止受影响操作，保留证据、同步总控并报告最小可操作阻塞。不得为满足“全程执行”伪造完成。
变更规格/预算/完成门前先建CR记录，同步设计/总控/manifest/任务/清单/Goal；用户要求的最终沙盒实测不可静默删除。修复循环有界，保留原失败。断点恢复先检查事实和未完成操作，不从头重装或重复已通过测试，除非新改动/新故障需要。

【最终完成和报告】
全部完成须7阶段done、A1–A10必测全pass、M6四引擎GPU真实训练通过、同制品干净OS从零安装通过、阶段报告和7组push回执齐备、最终远端完整SHA确认、中文交付说明和包SHA/许可齐备，无未解决P0/P1或必测not-run。
最终先同步总控/manifest/报告再保存最终基线。报告列完成项、关键文件/交付包与SHA、阶段远端SHA、真实环境与证据、失败修复、未执行/剩余限制、清理结果、生产签名/渠道是否实际就绪。只在必需项全部完成后标complete；若阻塞就如实标incomplete/blocked，不用计划或历史结果冒充本次实测。不自动合并、发布、发他人消息或关闭issue。
```

本提示词不指定token预算；执行者不得自行猜测Goal额度。实际Goal已按用户指令建立，执行者继续维护总控并按门禁推进，不能在未完成时标Goal complete。
