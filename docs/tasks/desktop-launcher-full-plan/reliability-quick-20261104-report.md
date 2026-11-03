# 启动器快速修复实测记录

更新：2026-11-04。范围按用户最新授权，只测试本轮问题及直接关联流程；不开启训练、不下载或加载训练模型。

| 项目 | 当前结果 | 证据与说明 |
| --- | --- | --- |
| Windows 预览路径被误拒 | 已修复，定向通过 | 生产形态红测复现；逐分量构造 `state/engines` 路径后10项定向通过；candidate11真实查询越过原错误并成功生成计划 |
| 前端误拒第2版修复计划 | 真实复验通过 | candidate12从正式按钮生成计划、显示详情并取消；安装控制和资料零改动，自然退出、Job排空通过；candidate11失败原件保留 |
| 可见进度与真实取消 | 待测 | 仅代表任务与关联入口 |
| 实际修复与完成旧安装 | 待测 | 仅自有故障沙盒，保原journal和用户资料 |
| 服务启停及按钮刷新 | 待测 | 同包、真实HTML/API与监听进程，记录实际时延 |

当前候选为 **candidate12**，正式离线构建成功，用时约179秒。前端类型检查与Vite编译通过；175个源码输入、交付清单和便携包内EXE校验一致。构建自有Job已排空，编译辅助进程的强制回收单独记录。

- 便携包：`F:/NextTrainerLauncherSandbox/reliability-20261102/run-20261102T130200Z/build-R2-12/NextTrainerLauncher-0.2.0-windows-x64-portable.zip`。
- EXE SHA256：`124f5aaefe2a94e421a2a0b853fa615496677e692d38678e40dcb470cd8d1fe1`。
- 证据根：`E:/OpenSourceTeamWork/workspace/tools/launcher-reliability-20261102/run-20261102T130200Z`，下称 `<run>`。
- 构建与冻结：`<run>/R2/build-12/execution.json`、`<run>/R2/candidate-freeze-12/admission.json`。
- 原预览失败：`<run>/R2/legacy-v8-preview-only-01/native-report.json`；后端succeeded、41.3秒，前端因schema不符拒绝，不计业务通过。
- 修复后预览：`<run>/R2/legacy-v9-preview-only-01/`；`native-report.json`、`host-status.json`与`v5-chain-result.json`均通过，计划截图为`0004-fault-formal-ready-plan.png`。
- Q1远端基线：`f6936b56ae50799c479b477590e1d87c19b4791f`，已通过代理push并核远端SHA；后续schema修复尚未提交。

本轮复用已通过的10项Rust定向测试、fmt及严格Clippy。两次整套Rust180秒超时均保留，按快速范围不再要求重跑，也不计通过。

未测范围：四引擎完整扫描/重建矩阵、三阶段取消与强杀恢复全套、GPU及真实训练、历史227行全量验收。打开外部浏览器按钮以最终实际操作记录为准，不能用“已启用”代替点击通过。
