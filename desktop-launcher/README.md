# Next Trainer 桌面启动器

**2026-10-30 / CR-009：** 用户已通过主要功能验收并批准 [D1.1 视觉与响应设计](../docs/design/desktop-launcher-starward-ui-design.md)，新版界面和启停状态同步正在施工。侧栏集中提供首页、版本、环境、日志和设置；项目 Logo 随包提供。开发进度及实测结论以[当前总控](../docs/tasks/desktop-launcher-full-plan/00_总控目标索引.md)和[实施记录](../docs/tasks/desktop-launcher-full-plan/starward-ui-implementation-report.md)为准。

CR-008 已删除下载预算的界面、设置、CLI/IPC及账本机制，没有隐藏高级开关。最终候选在 r12 完成真实网络安装、Kohya 两步训练和权重读回，随后 u13 用户沙盒通过页面提交训练；详见[原安装与训练记录](../docs/tasks/desktop-launcher-full-plan/full-real-install-followup.md)。本轮不重复下载模型或实跑四引擎训练。

对应 [需求 #516](https://github.com/wochenlong/lora-scripts-next/issues/516)。当前为 **0.2 开发版**，采用 Tauri 2、Vue 3 和 Rust，提供独立安装、main / dev 版本管理、共享用户资料、环境检查和恢复。启动器可以在训练器未安装或 Python 环境损坏时独立打开。

固定 GUI 配方使用 wheel hash 锁、基础 Python 文件清单、独立实例和单包修复预览；源码修复、登记恢复、重建/回退和持久中断恢复分别提供入口。新环境采用 `e/<短实例ID>`，旧记录继续读取原路径，详见[路径兼容补充](../docs/design/desktop-launcher-m1-instance-storage.md)。安装、源码、环境和用户资料各自管理。

M0–M6 历史施工与证据均保留在完整任务书。四引擎检查/修复按用户批准的 CR-004 精简为冒烟；Kohya 的后续实训结果不证明另外三个引擎可实训。干净 Windows、缺 WebView2 首装和生产签名渠道仍未完成验收。

## 安装与使用

运行便携包中的 `next-trainer-launcher.exe`，或使用当前用户 NSIS 安装器。运行时不需要系统 Python、uv、Node 或 Rust；Windows 需要 WebView2。NSIS 配置官方联网引导下载 WebView2，缺运行时的干净机器首装仍需另行实测。

1. 选择一个空目录，或本版启动器创建的正式工作区。暂不接管开发仓库、旧整合包或 0.1 验证样包。
2. 首次点击“安装训练器”。当前安装包默认选用内置 dev 制品，一次准备自管 uv、CPython、源码与已编译前端，以及完整主程序依赖。可以先在版本管理中选择安装 main。
3. 检查通过后点击“启动训练器”。只有受管进程存活、监听进程属于本启动器的进程组、真实 `/api/version` 返回预期版本时，才显示“服务已就绪”。随后可在浏览器打开。
4. 版本管理可安装另一条发布线。安装其他版本不会自动切换当前版本；停止运行中的训练器后，再点击“切换到此版本”。主动切换 dev 时会显示开发线风险确认。
5. 当前版本启动并通过健康检查后会记录健康状态。切换到其他版本时保留上一已健康版本，可通过“回退到此版本”切回。选择与回退复用已完整安装的版本，不重新下载同一份制品。

下载需要联网。建议预留至少 3 GiB，多个运行环境、源码和修复备份会继续占用空间。界面显示的下载量与源码展开大小来自内置清单，**不包含全部 Python、运行环境、训练引擎和模型的空间**。当前没有完整的磁盘余量预估。主程序依赖安装完整 `requirements.txt`；独立训练引擎、各引擎的 Torch 和模型权重不包含在此安装步骤中。

网络设置提供自动、系统、手动代理和直连，支持本机绕过；自动模式可继承进程代理环境变量，没有内置开发者代理地址。uv/Python/源码/wheel 按固定清单下载并核对。下载失败会保留错误与临时文件，可重新安装或重试对应修复。

## 发布清单与版本身份

[catalog/releases.json](catalog/releases.json) 是编译进 EXE 的发布清单，包含发布线、完整提交、源码归档 URL / SHA256 / 大小、uv 的 ZIP 与 EXE 哈希、自管 Python 版本、环境配方、资料 schema 和必要文件。设置中的安全与更新提供可信清单及历史入口；开发候选没有配置生产签名渠道，不能把内置清单显示当成查询到远端最新版本。

版本唯一标识为 `<发布线>-<40 位完整提交>`，不能用版本号或 8 位短提交判断两个版本相同。主要入口如下，其他历史 dev 制品以当前清单为准：

| 发布线 | 真实 VERSION | 完整提交 / release ID |
| --- | --- | --- |
| main | `3.3.1-dev` | `main-0785419e7dc1a3058bd8710a9aa933fec0aabdee` |
| dev | `3.3.1-dev` | `dev-89a3b6ca63964b3bc4549b8bda67b38c4baa1a3d` |

main 和 dev 的实际 `VERSION` 都写为 `3.3.1-dev`。main 在界面中标作稳定线，表示发布通道，不会据此把其真实版本号改成 `3.3.0` 或宣称该提交已经达到正式稳定发布标准。二者的源码、环境、安装回执和运行状态仍按完整 release ID 分别管理。

当前自管工具为 uv `0.11.16` 与 CPython `3.10.19`。源码归档、uv ZIP 和 uv.exe 校验固定 SHA256；恢复后的源码与前端资源有逐文件完整性检查。固定 GUI 配方包含 Python 依赖 hash 锁与受管包文件证明；启动前仍检查解释器归属、隔离、实际文件和关键依赖导入。

## 工作区与用户资料

```text
选择的工作区/
  .launcher-workspace                 正式工作区所有权标记
  .launcher-lock                      跨进程互斥锁
  state/
    registry.json                     当前版本、安装记录、上一已健康版本
    journal-<release-id>.json          安装与恢复阶段记录
  releases/<release-id>/
    release.json                      固定制品身份与安装回执
    app/                              源码、已编译前端、完整性清单
  environments/<release-id>/gui/       按版本隔离的主程序虚拟环境
  profiles/default/
    profile.json                      用户资料 schema
    user_data/                        共享设置、预设、凭据与任务归档
    library/
      models/                         共享训练模型目录
      tagger-models/                  共享打标模型目录
      datasets/                       共享数据集
      output/                         共享训练输出
    compat/<release-id>/              按版本保留的兼容状态
  run/<release-id>/                   可重建的运行视图
  tools/                             校验后的 uv
  python/<python-version>/           自管 CPython
  cache/                             已校验下载 ZIP 与独立 uv 缓存
  staging/                           下载、解压与运行视图准备目录
  backups/                           修复、删除与重建前保留的目录
```

`profiles/default` 独立于源码和虚拟环境。main / dev 共用其中的设置、用户预设、任务归档、模型、数据集和输出；界面会显示其绝对路径。`compat/<release-id>` 按版本保存 `assets`、`config`、`toml`、`logs`、`.runtime`、`extensions`、`train` 和 `.cache` 等兼容状态，避免把不同版本的内部状态直接混在一起。

启动时构建 `run/<release-id>` 工作目录：复制经过校验的代码，通过固定目录联接接入共享资料与按版本状态，再以该运行视图为工作目录启动训练器。对支持新合同的代码，同时设置 `NEXT_TRAINER_DATA_ROOT` 和 `NEXT_TRAINER_STATE_ROOT`；对本包两个历史提交使用兼容视图。因此切换和修复源码不需要将用户资料搬入新代码目录。

资料目录只支持当前 `default` profile。未知 schema、损坏登记、不受支持的工作区标记和不受信任的路径联接会被拒绝，保留现场供诊断；不会自动覆盖或迁移。外部模型、数据集等自定义路径仍由用户配置，不会自动复制到共享目录。

## 检查、修复与删除

“已安装”表示存在匹配内置清单的安装回执，不等于可运行。版本页分别显示源码和环境检查；启动前再次检查实际文件、解释器和服务响应。

- **准备基础工具**：检查 uv 哈希和自管 Python 的实际运行；缺失或损坏时保留旧内容后重新准备。不会使用系统 Python 兜底。
- **恢复当前版本源码**：从固定归档与已校验缓存准备完整新目录，检查后替换版本目录；旧目录移入 `backups/`。完整版本直接复用，不重复下载。共享 profile 不在源码替换范围内。
- **主程序环境**：先独立诊断，可预览单包精准修复；基础 Python 恢复、环境实例重建/回退及登记恢复通过高级入口操作。修复/重建保留备份和用户资料，不重新安装全部版本。
- **训练引擎环境**：Kohya、Anima Fast、AI Toolkit、DiffSynth 各自提供检查、安装/修复计划、重建和解释器探测。文件检查通过不等同于实际 GPU 训练通过。
- **切换 / 回退**：要求目标源码、环境和自管 Python 检查通过；运行中的训练器需先停止。上一已健康版本必须已经通过真实启动检查，回退还要求 profile schema 兼容。
- **删除版本**：当前版本和保留的回退版本禁止删除。其他受管版本的源码、环境和运行视图先移到备份，再移除安装登记；共享资料、该版本兼容状态和下载缓存保留。删除不代表立即释放所有磁盘空间。

安装有持久化阶段记录，界面会显示未完成操作；重启后可以重新检查并重试。尚未实现自动恢复到精确字节或依赖安装步骤。备份、旧运行视图和临时文件暂不自动清理。运行视图包含指向共享资料的目录联接，清理时必须避免递归跟随联接删除共享数据。

关闭启动器会结束其 Job Object（Windows 作业对象）管理的训练器和安装子任务，不会按进程名或端口清理其他程序。启动使用本机可用端口，若出现竞争则安全报错，不终止占用者。

## 开发与构建

Windows 构建需要 Node、Rust MSVC 工具链、VS2022 C++ Build Tools、Windows SDK 和 WebView2。已使用的工具链为 Node `24.13.0`、Rust `1.94.1`。JS 和 Rust 依赖由 `package-lock.json` 与 `src-tauri/Cargo.lock` 固定。

固定 GUI 候选构建还需将 `NEXT_TRAINER_BUNDLED_FRONTEND` 指向配方中声明的训练器前端 ZIP 的绝对路径。运行时会再次校验其长度和 SHA256；没有捆绑资源的普通构建仍可独立打开，但在下载前拒绝安装该候选。外部 ZIP 不提交到 Git，制品身份与构建证据位于完整任务书的 `M1/recipe/`。

```powershell
Set-Location desktop-launcher
npm ci
npm run build
cargo test --locked --manifest-path src-tauri/Cargo.toml
cargo build --release --locked --manifest-path src-tauri/Cargo.toml
```

新的正式输出为 `src-tauri/target/release/next-trainer-launcher.exe`，不再使用旧的 `next-trainer-desktop-probe.exe`。前端与发布清单嵌入 EXE，单独分发此 EXE 时无需附带 `dist/`，但它不包含 WebView2 安装器、Python 或训练器文件。修改前端后必须先重新执行 `npm run build` 再编译 Rust，避免 EXE 嵌入旧界面；修改发布清单也需重新构建 EXE。开发热更新使用 `npm run tauri dev`。

## 命令行管理与自动化

GUI EXE 同时提供 `--manage` 管理入口，与图形界面使用相同的 Rust 核心；`--probe` 是保留的旧别名。

| 调用 | 行为 |
| --- | --- |
| `--manage inspect <绝对目录>` | 检查实际安装、全部内置版本与运行状态，不安装 |
| `--manage install-release <绝对目录> <release-id>` | 下载并安装指定版本；空工作区将其设为当前版本 |
| `--manage select <绝对目录> <release-id>` | 切换到检查通过的已安装版本 |
| `--manage rollback <绝对目录>` | 切回上一已健康版本 |
| `--manage remove <绝对目录> <release-id>` | 删除允许移除的受管版本，保留资料与备份 |
| `--manage bootstrap <绝对目录>` | 检查或准备基础工具 |
| `--manage restore <绝对目录>` | 恢复当前版本源码 |
| `--manage install <绝对目录>` | 安装或修复当前版本主程序环境 |
| `--manage smoke <绝对目录>` | 启动真实训练器并等待健康检查，然后停止本次进程 |

Windows GUI EXE 从 PowerShell 直接 `& $exe ...` 调用时，终端可能提前返回。自动化应使用 `Start-Process -PassThru -Wait` 并重定向 stdout / stderr；stdout 是 JSON 报告，stderr 是日志和错误。路径包含空格时必须保留参数中的引号。例如只读检查：

```powershell
$launcherExe = (Resolve-Path '.\src-tauri\target\release\next-trainer-launcher.exe').Path
$installationRoot = 'D:\Next Trainer'
$reportPath = Join-Path $env:TEMP 'next-trainer-inspect.json'
$logPath = Join-Path $env:TEMP 'next-trainer-inspect.log'
$launcherArgs = @('--manage', 'inspect', ('"{0}"' -f $installationRoot))
$launcherProcess = Start-Process -FilePath $launcherExe -ArgumentList $launcherArgs `
    -WindowStyle Hidden -PassThru -Wait `
    -RedirectStandardOutput $reportPath -RedirectStandardError $logPath
if ($launcherProcess.ExitCode -ne 0) {
    Get-Content -LiteralPath $logPath
    throw "启动器检查失败，退出码 $($launcherProcess.ExitCode)"
}
Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
```

CLI 每次调用拥有自己的受管进程状态；图形界面启动的服务不属于另一个 CLI 进程。检查 GUI 的完整运行状态应使用该窗口中的检查入口；工作区锁会阻止其他实例同时修改同一安装目录。管理命令可下载和更改安装，使用前请按表中行为选择命令。

## 实测边界与后续范围

- 生产发布签名、生产可信更新渠道、依赖许可文本完整审结、干净 Windows 和缺 WebView2 的首装仍未完成。
- 旧资料导入提供预览与确认，不能推导任意整合包、所有插件或多 profile 都可自动迁移。
- 四引擎完整故障与 GPU 验证按用户授权边界报告；Kohya 已有实训证据，其余三引擎不宣称实训通过。非 Windows 平台不在首发范围。
- 下载预算已彻底删除。自动清理、完整磁盘峰值估算和未铺开的故障矩阵保持原边界。

M1 的网络与资料隔离合同见[网络策略与用户资料保护补充](../docs/design/desktop-launcher-m1-network-and-profile-protection.md)。当前开发结果不代表安装器、全部故障恢复或最终干净机器验收已完成。

基础 Python 的完整组件、共享引用停用和同路径恢复合同见[基础 Python 组件修复](../docs/design/desktop-launcher-m1-base-python-repair.md)。环境页可先读取组件清单与引用环境，审查后再确认恢复；不能把组件完整等同于所有引用环境已经健康。

代码许可遵循本仓库。恢复核心和资料管理为本项目实现，参考了调研项目的结构思路，没有引入绘心项目尚未明确授权的源码。参考依据见 [桌面启动器调研](../docs/design/desktop-launcher-reference-research-2026-10-28.md)。
