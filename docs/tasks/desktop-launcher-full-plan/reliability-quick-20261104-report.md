# 启动器快速修复实测记录

更新：2026-11-04。按用户授权完成针对性修复和沙盒冒烟；不开启训练、不下载或加载训练模型。

| 项目 | 结果 | 实际证据与边界 |
| --- | --- | --- |
| Windows路径误拒、修复计划显示 | 通过 | 逐分量构造路径，前端接受schema1/2；candidate12正式入口显示计划并取消，原资料保持 |
| 修复准备反馈 | 通过 | preparing DOM约1.8ms出现；资源计划准备期间确认禁用，计划约50秒生成 |
| 实际修复与取消还原 | 通过功能复核 | 修复约183.4秒succeeded；取消82ms受理、139ms子进程退出，cancelled/rolled_back；旧套件文案和阶段归因失败保留 |
| 完成原未结束安装 | 通过 | candidate12使用原journal摘要恢复，约5.56秒；正式committed，首页启动入口恢复，资料和回执保持 |
| 服务启停与状态刷新 | 通过 | candidate13启动约9.69秒；HTML和版本API均200；ready后5ms启用打开网页按钮，停止后21ms恢复启动按钮，端口释放 |
| 停止后切换版本 | 修复并通过 | 旧启动报告误将其他版本未检查当失败；停止后异步刷新轻量库存，真实按钮已切回dev |
| 四引擎入口、进度与取消 | 冒烟通过 | 四个入口均响应并取消至cancelled，回收标志通过且无残留；AI Toolkit有逐文件进度并在running取消，另外三个在queued取消。完整扫描主动停止 |
| 退出与资料保护 | 通过 | 120个资料文件逐字节保持；除registry外状态文件保持，安装回执及引擎记录未变；启动器自然exit0、Job排空、服务和调试端口回收 |

本轮最后修复仅修改停止服务后的轻量刷新，因此预览、实际修复和续办复用candidate12证据；candidate13补测服务、版本切换与引擎冒烟。

交付文件：

- 便携包：`F:/NextTrainerLauncherSandbox/reliability-20261102/run-20261102T130200Z/build-R2-13/NextTrainerLauncher-0.2.0-windows-x64-portable.zip`。
- EXE SHA256：`5c0e6015e335c0f27092acb0b660da9ac67674132c23510e15bfe0eda417abfe`。
- 正式离线构建约234秒；前端类型检查、Vite编译、175个源码输入及便携包程序校验通过。构建辅助进程回收单独记录。
- 分支：`feat/desktop-launcher`。先前阶段已push `f6936b56`、`8a620541`；本次最终commit/push和远端完整SHA见`<run>/R2/quick-final-git.json`。

证据根`<run>`为`E:/OpenSourceTeamWork/workspace/tools/launcher-reliability-20261102/run-20261102T130200Z`。

| 证据 | 路径（相对`<run>`） |
| --- | --- |
| 构建与冻结 | `R2/build-13/execution.json`、`R2/candidate-freeze-13/admission.json` |
| 正式预览与取消 | `R2/legacy-v9-preview-only-01/0004-fault-formal-ready-plan.png`及同目录report/host/chain |
| 实际修复、取消、恢复 | `R2/legacy-v9-success-01/0011-repair-operation.json`、`0012-repair-complete-protection.json`；`R2/legacy-v9-cancel-sync-01/0008-fault-cancel-stage-proof.json` |
| 原安装恢复完成 | `R2/legacy-v9-resume-01/0008-formal-recovery-complete.png`、`0009-home-start-available-without-starting.png` |
| 服务语义与时延 | `R2/legacy-v9-targeted-candidate13-01/0006-main-ready-html-api-owned-listener.json`、`0008-own-service-stopped.json` |
| 服务与版本截图 | 同目录`0007-main-service-ready.png`、`0009-main-service-stopped.png`、`0010-returned-to-original-dev.png` |
| 四引擎冒烟 | 同目录`quick-four-engine-smoke.json`、`quick-*-cancelled.png`、`0011-engine-ai-toolkit-progress.png` |
| 退出后独立保护复核 | 同目录`quick-scope-review.json`，快速范围`passed=true`，保留原套件结果 |

原`native-report.json`保留`engine progress evidence overflow`失败：长扫描超过工具1024条进度记录上限，完整扫描亦按快速范围取消。未改写原结果。最终快速结论来自真实点击、任务终态、HTML/API和退出后的独立资料比较。

未测：四引擎完整文件扫描/损坏/重建矩阵、三阶段取消和强杀恢复全套、高级破坏性按钮、外部“打开网页”按钮实际点击、GPU与真实训练、历史全量验收。两次完整Rust180秒超时原件保留；复用当前Rust输入已通过的10项定向、fmt、严格Clippy，不计整套通过。
