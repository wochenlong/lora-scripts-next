# Next Trainer 桌面启动器

对应 [需求 #516](https://github.com/wochenlong/lora-scripts-next/issues/516)。当前为 **0.2 开发版**，采用 Tauri 2、Vue 3 和 Rust，提供独立安装、main / dev 版本管理、共享用户资料、环境检查和恢复。启动器可以在训练器未安装或 Python 环境损坏时独立打开。

这是桌面启动器的正式底座，尚未覆盖 #516 的全部功能。功能实现和实际验收状态分别记录；本说明不将构建成功视作新电脑、GPU 训练或全部损坏场景通过。当前进度和证据入口见 [正式化底座施工计划](../docs/tasks/desktop-launcher-foundation-plan/README.md) 与 [总控索引](../docs/tasks/desktop-launcher-foundation-plan/00_总控目标索引.md)。

当前功能分支正在执行[完整交付任务书](../docs/tasks/desktop-launcher-full-plan/00_总控目标索引.md)的 M1，尚未完成本阶段验收。固定 GUI 候选已接入 81 个 wheel 的 hash 锁、基础 Python 完整文件清单、独立实例与单包修复预览、源码分项修复和持久恢复意图。新环境采用 `e/<短实例ID>`，旧记录继续读取原路径，详见[路径兼容补充](../docs/design/desktop-launcher-m1-instance-storage.md)。这些能力仍在真实安装与故障验证中，下文旧底座能力边界以完整任务书实时进度为准。

本轮按 v0.4 / CR-003 收敛为 GUI 候选包；实际包身份、固定候选源码、中文操作步骤及同包安装/启动/修复/登记恢复结果见[候选报告](../docs/tasks/desktop-launcher-full-plan/m1-candidate-report.md)。该报告中的验收状态优先于下文历史底座说明，候选不代表完整 #516、干净系统或训练引擎验收通过。

## 安装与使用

运行构建后的 `next-trainer-launcher.exe`。运行时不需要系统 Python、uv、Node 或 Rust；Windows 需要 WebView2。当前没有附带 WebView2 安装器，首次安装到缺少 WebView2 的电脑仍需单独处理。

1. 选择一个空目录，或本版启动器创建的正式工作区。暂不接管开发仓库、旧整合包或 0.1 验证样包。
2. 首次点击“安装训练器”。当前安装包默认选用内置 dev 制品，一次准备自管 uv、CPython、源码与已编译前端，以及完整主程序依赖。可以先在版本管理中选择安装 main。
3. 检查通过后点击“启动训练器”。只有受管进程存活、监听进程属于本启动器的进程组、真实 `/api/version` 返回预期版本时，才显示“服务已就绪”。随后可在浏览器打开。
4. 版本管理可安装另一条发布线。安装其他版本不会自动切换当前版本；停止运行中的训练器后，再点击“切换到此版本”。主动切换 dev 时会显示开发线风险确认。
5. 当前版本启动并通过健康检查后会记录健康状态。切换到其他版本时保留上一已健康版本，可通过“回退到此版本”切回。选择与回退复用已完整安装的版本，不重新下载同一份制品。

下载需要联网。建议预留至少 3 GiB，多个运行环境、源码和修复备份会继续占用空间。界面显示的下载量与源码展开大小来自内置清单，**不包含全部 Python、运行环境、训练引擎和模型的空间**。当前没有完整的磁盘余量预估。主程序依赖安装完整 `requirements.txt`；独立训练引擎、各引擎的 Torch 和模型权重不包含在此安装步骤中。

下载器读取进程的 `HTTP_PROXY` / `HTTPS_PROXY` 等代理环境变量，没有内置开发者的代理地址；界面代理设置尚未接入。uv 来自官方 GitHub 发布，自管 Python 由 uv 下载，主程序依赖默认来自 PyPI。下载失败会保留错误与临时文件，可重新安装或重试对应修复。

## 发布清单与版本身份

[catalog/releases.json](catalog/releases.json) 是编译进 EXE 的发布清单，包含发布线、完整提交、源码归档 URL / SHA256 / 大小、uv 的 ZIP 与 EXE 哈希、自管 Python 版本、环境配方、资料 schema 和必要文件。界面显示“内置发布清单”，不表示已经查询远端最新版本；目前尚未实现远端清单刷新。

版本唯一标识为 `<发布线>-<40 位完整提交>`，不能用版本号或 8 位短提交判断两个版本相同。本包当前提供：

| 发布线 | 真实 VERSION | 完整提交 / release ID |
| --- | --- | --- |
| main | `3.3.1-dev` | `main-0785419e7dc1a3058bd8710a9aa933fec0aabdee` |
| dev | `3.3.1-dev` | `dev-9ca2de963122f34599e34e5ff382199de9188811` |

main 和 dev 的实际 `VERSION` 都写为 `3.3.1-dev`。main 在界面中标作稳定线，表示发布通道，不会据此把其真实版本号改成 `3.3.0` 或宣称该提交已经达到正式稳定发布标准。二者的源码、环境、安装回执和运行状态仍按完整 release ID 分别管理。

当前自管工具为 uv `0.11.16` 与 CPython `3.10.19`。源码归档、uv ZIP 和 uv.exe 校验固定 SHA256；恢复后的源码与前端资源有逐文件完整性检查。主程序环境实际检查解释器归属、隔离配置、Python 版本和关键依赖导入。完整 Python 依赖仍来自对应源码的 `requirements.txt`，尚未形成独立的全量依赖锁。

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
- **安装 / 修复运行环境**：只处理当前版本的主程序虚拟环境。损坏环境保留到备份后重建，不重新安装全部版本，也不删除共享资料。当前尚不是针对单个 Python 包的精准修复。
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

## 仍待完成的范围

- 独立训练引擎的 Python / Torch / GPU 检查、引擎安装与针对性修复；当前环境页覆盖基础工具和训练器主程序。
- 远端发布清单刷新、启动器自身更新、签名、Windows 安装器、WebView2 引导和干净机器安装体验。
- 旧整合包或已有训练器接管、旧 profile 迁移、多 profile、全部插件与数据迁移兼容性。
- 完整的下载、解压、依赖、提交故障矩阵，生产累计网络预算、自动清理与磁盘峰值估算；严格续传和独立取消已接入，验收范围见总控。
- 固定 GUI 配方、单包修复、源码组件修复和网络设置正在 M1 验证；基础 Python 共享引用修复、GPU 训练、模型下载和非 Windows 平台验收仍待完成。

M1 的网络与资料隔离合同见[网络策略与用户资料保护补充](../docs/design/desktop-launcher-m1-network-and-profile-protection.md)。当前开发结果不代表安装器、全部故障恢复或最终干净机器验收已完成。

基础 Python 的完整组件、共享引用停用和同路径恢复合同见[基础 Python 组件修复](../docs/design/desktop-launcher-m1-base-python-repair.md)。环境页可先读取组件清单与引用环境，审查后再确认恢复；不能把组件完整等同于所有引用环境已经健康。

代码许可遵循本仓库。恢复核心和资料管理为本项目实现，参考了调研项目的结构思路，没有引入绘心项目尚未明确授权的源码。参考依据见 [桌面启动器调研](../docs/design/desktop-launcher-reference-research-2026-10-28.md)。
