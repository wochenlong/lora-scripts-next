# 桌面启动器最小可行性验证

日期：2026-10-28。依据：issue #516 与 `docs/design/desktop-launcher-reference-research-2026-10-28.md`。

## 当前目标与范围

用户已授权继续调研报告中的下一步：制作 Tauri 2 + Vue 3 验证样包，验证训练器缺失或损坏时仍能打开桌面窗口、选目录、独立下载基础工具并恢复真实训练器。该阶段为 Lite research/prototype（轻量调研原型），源码和官方工具合同驱动；不锁定正式架构，不表示完成 #516。

正式工作副本 `E:/OpenSourceTeamWork/workspace/branches/dev`，`dev` 为 `9ca2de963122f34599e34e5ff382199de9188811`，本轮已再次核对远端一致。原有 C# `launcher/` 保留，原型新增到 `desktop-launcher/`。原有未跟踪文档保留，不提交或发布。

## 验收追踪

| 编号 | 验证目标 | 方法 | 状态 |
| --- | --- | --- | --- |
| P1 | Tauri 原生窗口不依赖系统 Python/uv | release EXE + PATH 限制启动 + WebView2 实测 | pass：debug 与最终 release 均通过 |
| P2 | 选择全新目录，缺失训练器时能检查和引导 | 原生 IPC 调用与界面检查 | pass：路径输入、三页检查，12 项 native UI 检查 |
| P3 | 自管 uv/Python，不污染系统安装 | 固定 uv 校验；uv Python --no-bin --no-registry；检查目录 | pass：PATH 仅 Windows 系统目录仍下载并运行自管工具 |
| P4 | 固定源码及前端恢复 | 固定提交 archive SHA256、临时目录解压和完整性清单 | pass：真实下载、校验、恢复源码与 dist |
| P5 | 真实训练器启动 | 完整 requirements 环境、子进程存活及 /api/version 语义响应 | pass：CLI smoke 与最终原生按钮均通过，HTML/JS/CSS 真实 HTTP 200 |
| P6 | 损坏可检测、可重试恢复 | 删除样包专属 gui.py / 环境解释器后重跑 | pass：源码、venv、基础 Python 三类损坏恢复及备份文件 SHA256 均通过 |
| P7 | 用户现有目录、其他进程不受影响 | 拒绝接管非空无标记目录、目录锁、子进程归属审查 | pass：2 个保护性测试、独立审查、Job 成员核验、停止与 WM_CLOSE 后进程/端口回收 |

## 实施决策

- 只支持 Windows x64 原型；900×600，中性灰工程风，导航为启动/版本管理/环境管理。
- 固定 `uv 0.11.16`、自管 CPython 3.10.19、训练器 `dev@9ca2de96`。源码 Git 中包含前端 dist，因此运行时无需 Node。
- 每个选定目录都是独立原型工作区，内部有 tools/python/cache/versions/environments/backups；拒绝接管现有开发目录和未标记的非空文件夹。
- 更新源码先验证下载哈希，再完整解压到新目录；旧源码移动到 backups 保留用户生成的数据。环境修复同样保留旧环境。当前不会自动迁移用户数据。
- 安装按钮均明确触发联网；不在打开窗口时自动安装。完整主程序环境不包含 Torch/训练引擎安装。
- 版本并存、main/dev 切换、精准组件修复、断点续传、启动器自身更新签名、GPU训练、干净机器验收属于后续工作。

## 证据位置

原始下载与运行证据存于 `E:/OpenSourceTeamWork/workspace/tools/launcher-prototype-20261028/`；证据与运行时文件不纳入仓库。固定资产来源见该目录 `assets/asset-validation.json`。uv 哈希有官方独立校验文件；源码归档哈希为固定 commit 的 HTTPS 首次下载后测得。

## 当前执行记录

- 基线与实际启动合同已核实；现有 C# 入口不是 #516 的桌面恢复管理层。
- GUI 的 requirements guard 仍会运行；必须安装完整 requirements，并给 venv 提供 pip。
- GUI 使用 `/api/version` 检查，不以 PID 或端口响应代替实际可用。
- 工具链：Node 24.13.0、Rust 1.94.1、VS2022 BuildTools 与 WebView2 均存在。干净 Windows 机器尚未验证。
- 已新增完整 `desktop-launcher/`：Vue UI、原生 IPC、校验下载、独立工具安装、目录恢复、完整 GUI 环境安装、受管进程与语义健康检查。
- `npm run build`、`cargo test --locked`（2 项）、`cargo clippy --locked -- -D warnings`、`cargo build --release --locked` 已通过。最终 release EXE 为 12,662,272 字节，不含外部 WebView2 运行时。
- 真实安装使用 `tools/launcher-prototype-20261028/验证 空目录`，PATH 仅 Windows 系统目录；uv/Python/源码/环境/前端五项已全部实际检查通过。
- 缺失训练器的真实 WebView2 窗口已通过 12 项检查：900×600、无横向溢出、日志在窗口内、三页、路径输入和 IPC。证据位于 `ui-test/artifacts/native-missing-trainer-retry/`。
- 独立审查发现并修复：Python 目录残存时重复安装无法恢复、安装子任务退出归属不完整、仅凭同版本端口响应可能误判。现已备份损坏 Python 重装、所有子任务附到 Job Object、使用 Windows TCP owner PID 加 IsProcessInJob 核对监听归属。
- 已复核原 32 个未跟踪文件 SHA256 保留。没有改动跟踪文件或旧 C# launcher，没有提交/推送。

## 最终真实验收与问题修复

- 三种损坏分别由实际删除 `gui.py`、删除 venv `Scripts/python.exe`、移走自管 Python `python.exe` 产生；各次 inspect 真实返回失败，再执行恢复返回通过。源码恢复约 3.58 秒，热缓存环境重建约 7.97 秒，Python 重新下载并安装约 19.48 秒；这些不是冷机安装耗时承诺。
- 三类旧目录中的 sentinel 均在备份中通过 SHA256 比对；移走的原始 Python EXE 也保留且哈希一致。
- 首次真实 smoke 在 180 秒后失败：Windows venv redirector 和实际监听 Python 的 PID 不同，旧实现误判了归属。故障证据保留在 `probe/recovery-acceptance-release-20261028/`，没有将失败记录为成功。
- 修复为验证监听进程属于本次专属 Windows Job Object。最终 CLI smoke 约 8.96 秒通过，`/api/version` 为 `3.3.1-dev`，HTML 和真实 JS 正常；停止后 redirector/实际解释器和端口全部回收。证据：`probe/recovery-acceptance-fixed-final-20261028/`。
- 最终 release 的原生按钮 start/stop/restart 分别通过 18/16/18 项检查，真实 HTML、608,037 字节 JS、247,042 字节 CSS 均返回 HTTP 200。证据：`ui-test/artifacts/release-button-start/`、`release-button-stop/`、`release-button-restart/`。
- 向 PID 132036 的隐藏原生主窗口发送一次 `WM_CLOSE`，启动器、redirector 126368、listener 129660 全部退出，端口 4195 消失。证据：`evidence/native-close-cleanup.json`。最终没有保留诊断窗口或训练器服务。

## 交付与范围

最终样包目录：`E:/OpenSourceTeamWork/workspace/tools/launcher-prototype-20261028/`。

| 交付 | 路径/身份 |
| --- | --- |
| 可直接运行 EXE | `NextTrainerLauncherProbe.exe`，12,662,272 字节（约 12.1 MiB） |
| 含说明、许可、哈希清单的压缩包 | `NextTrainerLauncherProbe-0.1.0-win-x64.zip`，4,388,583 字节（约 4.2 MiB） |
| EXE SHA256 | `7adaeb2b303de46b19c1d67caaf85d4a3870b2024a0c04c96d653fc084681779` |
| ZIP SHA256 | `adc0697adaab6ae77d527af640bffd709230c1d60215b8cfde07b9e7457cf822` |
| 中文说明 | `使用说明.txt`；仓库内 `desktop-launcher/README.md` |
| 备份与恢复详细报告 | `probe/DAMAGE_RECOVERY_RESULTS.md` |

本阶段状态：**complete（最小样包验证完成）**。P1–P7 均已有执行证据；Lite 的上下文、范围、实现、验证、审查和交付门已通过。#516 的正式功能仍待开发。本阶段没有锁定正式架构、添加完整施工计划或对外发布。

已验证的“无系统 Python/uv”是 Windows 本机通过限制被测 EXE 的 PATH、使用独立目录复现的场景；不是卸载系统工具后的干净机器验收。交互式原生文件夹选择对话框未自动操作，路径输入、检查按钮与原生 IPC 已实测。GPU 训练、无 WebView2 新电脑、安装器和签名均 not-run；这些不在本次原型的验收范围。

下一步：以 #516 为依据设计正式的安装清单、版本目录与独立用户数据模型，再据此进入功能开发。
