# 独立壳更新辅助程序

此 crate 只依赖 Rust/Windows API、文件锁与签名/摘要库，不依赖训练器 Python、GUI venv、Tauri 或 WebView2。主壳和 helper 复用 `src-tauri/src/shell_update_protocol.rs`，避免两套恢复协议。

当前生产壳签名资产与发布渠道尚未配置，默认拒绝生产更新。已实现的同包测试政策仅允许：显式新沙盒签名会话、编译内置 Ed25519 policy、候选与会话锁定壳完全相同的 SHA/长度，以及固定的 `shell-fixture/current/NextTrainerLauncher.exe` / `shell-fixture/candidate/NextTrainerLauncher.exe`。该政策不能替换任意已安装壳，也不能接受任意 URL、密钥或命令。

构建顺序：

1. `cargo build --release --locked --offline --manifest-path desktop-launcher/shell-updater/Cargo.toml`。
2. 计算 `shell-updater/target/release/next-trainer-updater.exe` 的 SHA256 与字节数。
3. 通过构建进程环境变量 `NEXT_TRAINER_UPDATER_SHA256`、`NEXT_TRAINER_UPDATER_BYTES` 编译主壳；主壳 `build.rs` 应为这两个变量输出 `cargo:rerun-if-env-changed`。
4. 将 helper 放入主壳 EXE 同目录；主壳只启动该固定文件，并在启动前核对编译锁定的 SHA/长度。

helper 只接受 `apply <绝对事务目录>` 或 `recover <绝对事务目录>`。目录必须为受会话绑定根内的 `updates/shell/shell-update-...`。它先等待登记的父 PID/原始 FILETIME 创建时间退出，再获取同一个 `.launcher-lock`；不会按进程名或端口结束外部程序。

trial 通过固定参数 `--shell-trial <绝对事务目录>` 启动候选壳。新壳应使用独立 Tauri 分支，只注册只读状态和渲染/恢复入口握手；主变更 IPC 不可注册。请求/确认/结果文件均位于本事务目录。helper 使用 Windows JobObject 回收本 trial 子树，确认失败或控制状态变化则恢复原字节控制文件与旧壳。快照损坏时保留现场和恢复 gate，不宣称恢复成功。

控制快照涵盖 `state/**`、工作区标记、启动器 `config/**`、所有 profile 描述和 `user_data/**`、对应兼容配置，以及 release receipt/源码完整性索引；单文件 32 MiB、总量 512 MiB、最多 20000 条目。模型和数据集所在 `library` 不为壳更新复制。实际格式迁移与壳确认分开；当前无自动格式升级，确认后返回 `no_migration`，不重写既有状态。

必要快检：`cargo test --locked --offline --manifest-path desktop-launcher/shell-updater/Cargo.toml -- --nocapture`。小夹具验证协议和精确恢复；真实 Windows EXE 占用、同包 GUI trial、安装器和最终新沙盒验证由 M6 完成。
