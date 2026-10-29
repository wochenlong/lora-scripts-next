# Windows 开发候选构建

`build_windows_candidate.py` 负责生成 Windows x64 的 NSIS 安装器、便携 ZIP 和身份清单。它不上传制品，不使用维护者私钥，也不把构建通过写成系统或训练验收完成。普通用户运行包内 EXE/helper 不需要系统 Python/uv；构建机需要 Python 3.11+、Rust MSVC、Node 以及已准备的依赖缓存。

先协调当前 Cargo 施工，冻结源文件，准备与 `catalog/gui-cp310-win-x64-v1.json` 完全吻合的训练器前端 ZIP。脚本使用已安装的 `node_modules`、Cargo 锁定离线缓存、Tauri 官方 NSIS 与 `nsis_tauri_utils.dll` 缓存。工具缓存缺失时预检拒绝构建，应由单独有来源和下载计量的依赖准备流程补齐。构建子进程使用离线选项和拒绝出站的代理，不临时下载依赖；工具缓存前后记录哈希与字节数，出现新字节则拒绝冻结候选。NSIS 的 `downloadBootstrapper` 在用户安装时按官方渠道获取 WebView2，构建本身不执行安装器或下载运行时。

在仓库根执行预检；路径替换为本次固定输入与仓库之外的新输出目录：

```powershell
python desktop-launcher/scripts/build_windows_candidate.py --frontend 'F:\固定输入\frontend.zip' --output 'F:\候选\本次唯一构建目录' --preflight-only
```

预检通过后移除 `--preflight-only` 执行构建。默认要求启动器相关编译/打包输入在 Git 中干净；无关未跟踪资料只记录、不阻断，也不加入制品。施工阶段可显式添加 `--allow-dirty`，此时包中标记 `launcher_worktree_dirty=true` 并保存逐文件输入摘要。编入壳的 Python worker/config 同样纳入身份冻结，四个指定引擎的固定锁必须齐备。输出目录存在即拒绝覆盖，失败日志与候选保留；修复后使用新的目录重新运行。脚本自己的文件锁防止重复运行脚本，仍须与手工 Cargo 构建协调。

构建按固定顺序进行：helper 的 locked/offline release → SHA256 与长度注入主壳 → 提取本机依赖许可 → 主壳与桌面前端 → 同包 `build-manifest.json` → NSIS → 便携 ZIP。NSIS `currentUser` 使用当前用户可写位置与 HKCU，提供简体中文及英文；WebView2 为官方在线引导。打包禁用二进制补丁，安装器和便携包包含相同的主 EXE/helper。

包中包含主壳、独立 helper、根 `LICENSE`/`NOTICE.md`、`LICENSES/**`、中文安装恢复说明和构建 manifest。外层 `delivery-manifest.json`/`SHA256SUMS.txt` 保存安装器与便携 ZIP 的 SHA256；`source-inputs.json` 保存构建输入的逐文件身份，`logs/` 保存各命令原始输出。包内清单不记录自身或外层 ZIP 的递归摘要。

清单分别记录 trainer source commit、launcher build commit 与当前源码摘要、catalog/recipe/公开签名夹具摘要、工具版本、helper/EXE 身份、生产 catalog 签名和 Windows 代码签名状态。源码施工候选不得冒充最终已提交基线；最终验收前还须把训练器固定源更新到已推送的完整 feature commit，并重建对应配方/前端/索引。四引擎实际安装与 GPU/训练仍为 `skip + CR-004`，干净 Windows 和缺 WebView2 为 `not-run`，实际同包结果由 M6 写入证据。
