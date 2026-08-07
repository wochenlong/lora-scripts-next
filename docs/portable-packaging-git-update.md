# 整合包打包注意事项与 Git 更新方案

本文记录 Windows 便携整合包的打包契约，以及将整合包改为"保留 `.git`、支持一键 Git 更新"后的实现方案。

> **团队约定与变迁记录**：[Discussion #73 — 整合包更新机制](https://github.com/wochenlong/lora-scripts-next/discussions/73)（双通道、bootstrap、`UPDATER_VERSION` 演进索引）

> **v2.5.2 用户**：若出现「能开网页但无法开始训练」，请升级到 **v2.5.3**（见 [`portable-upgrade-2.5.2-to-2.5.3.md`](portable-upgrade-2.5.2-to-2.5.3.md)，[Issue #54](https://github.com/wochenlong/lora-scripts-next/issues/54)）。

## 目标

- 整合包仍保持双击 `run_gui.bat` 即可启动。
- 新版整合包内的 `SD-Trainer/` 是一个可更新的 Git 仓库。
- `Update-SD-Trainer.bat` 面向小白用户，尽量把 Git 错误翻译成明确中文提示。
- 用户数据永远优先，更新代码时不能覆盖用户模型、输出、日志、自动保存配置。

## 稳定目录契约

发布包根目录必须保持：

```text
<PortableRoot>/
  run_gui.bat
  run_gui_portable.bat
  Update-SD-Trainer.bat
  Update-SD-Trainer-Release.bat
  Download-Anima-Model.bat
  install_xformers.bat
  python_embeded/
  SD-Trainer/
    sd-models/          # 模型（内置文件选择器 cwd 相对路径）
    output/             # 训练输出
    logs/
    train/
  sd-models/            # junction -> SD-Trainer/sd-models（兼容旧路径）
  output/               # junction -> SD-Trainer/output
  logs/                 # junction -> SD-Trainer/logs
  huggingface/
  tagger-models/
  tagger-models/wd14/
  tagger-models/vlm/
```

这些路径被用户快捷方式、启动脚本和文档绑定，不要随意改名。

## 构建来源要求

不要把维护者当前开发工作区原样打进整合包。构建时应使用干净来源：

1. 从 `origin/main` 或指定 release tag 创建干净 clone / worktree。
2. 确认没有未提交改动。
3. 保留主仓 `.git`。
4. 确保 remote 指向 `https://github.com/wochenlong/lora-scripts-next.git`。
5. 不要带入本机 `doc/`、`script/`、`data/`、`benchmark/`、`.vscode/`、`.cursor/`、临时草稿等目录。
6. 默认 **lite** 包**不要**打入 `extensions/anima_lora/`（含 `.venv`）；Fast 由用户在 WebUI 首次安装。完整 **full** 包见下表 `-BundleAnimaFast`。

`vendor/sd-scripts` 已经是主仓 tracked 普通目录，不是子模块，会随主仓更新。

## 双整合包（lite / full，内测起）

| 包 | 用途 | Fast 运行时 | 打标模型 | 体积目标 |
|----|------|-------------|----------|----------|
| **lite** | GitHub Release / 预发布上传 | 不预装 | 内置 `tagger-models/wd14/wd14-convnextv2-v2` | 压缩包 **&lt; 2 GB** |
| **full** | 百度网盘等大文件渠道 | 预装 `extensions/anima_lora`（含 `.venv`） | 同上 | 数 GB～十余 GB，视 venv 而定 |

```powershell
# 轻量（默认）
.\build-scripts\build_portable.ps1 -Version 2.9.2-beta.1 -Clean

# 完整（需本机已有可用 Fast 环境）
.\build-scripts\build_portable.ps1 -Version 2.9.2-beta.1 -Clean -BundleAnimaFast `
  -AnimaFastSource "D:\path\to\extensions\anima_lora"
```

产物文件名：`Next-Trainer-v{Version}-lite.7z` / `Next-Trainer-v{Version}-full.7z`（旧 Release 可能仍为 `SD-Trainer-v*`）；`PORTABLE_BUILD` 含 `flavor=lite|full`。包内项目目录仍为 `SD-Trainer/`（启动契约）。

## Anima Fast 插件与整合包（v2.7.0+）

Anima LoRA **Fast 模式**使用可选插件 [`sorryhyun/anima_lora`](https://github.com/sorryhyun/anima_lora)（MIT），运行时安装到 `SD-Trainer/extensions/anima_lora/`，并创建独立 cu130 venv（体积可达数 GB）。

| 项 | 约定 |
|----|------|
| lite 7z | **不**预装插件；用户路径：设置 → 训练引擎 / Anima Fast 页内安装 |
| full 7z | `-BundleAnimaFast` 从维护机已就绪环境复制（含 `.venv`） |
| 打包排除（默认） | `build-scripts/build_portable.ps1`、`03-copy-project.ps1` 排除整个 `extensions/` |
| 用户数据 | 用户安装后的 `extensions/anima_lora/` 视为本地数据；Git 更新勿覆盖（`.gitignore` 已忽略 `.venv/`、`source/`） |
| 文档 | [`docs/anima-fast.md`](anima-fast.md)、[`NOTICE.md`](../NOTICE.md) § Anima LoRA Fast Mode |

主 venv（`python_embeded`）仍负责标准 Kohya Anima LoRA / Finetune；Fast 训练**不**占用主 venv。

**打标模型（v2.7.0+ 整合包）**：离线 WD 默认模型预置在 **`tagger-models/wd14/wd14-convnextv2-v2/`**（`MIKAZUKI_TAGGER_MODELS_DIR`），构建时不再把同体积 ONNX 重复打进 `huggingface/hub/`。用户训练用 HF 缓存仍走根目录 `huggingface/`。

## 子模块策略

当前唯一子模块是：

```text
mikazuki/dataset-tag-editor
```

它已很久不更新，后续计划移除。现阶段更新脚本可继续尝试：

```bat
git submodule update --init --recursive --depth=1
```

但该子模块更新失败只能作为 warning，不应阻断主仓更新。用户训练主流程不应因为标签编辑器子模块失败而无法完成代码更新。

## 用户数据保护

这些目录或文件视为用户数据，更新时不得覆盖：

```text
sd-models/
output/
logs/
huggingface/
tagger-models/
tagger-models/wd14/
tagger-models/vlm/
train/
config/
toml/autosave/
assets/config.json
config/.update_cache.json
sd-trainer-log.txt
```

其中 `config/` 整体按用户目录处理。后续如果需要发布默认配置，应放在 `assets/defaults/` 或其他只读模板目录，启动时仅在目标不存在时复制到 `config/`，不能覆盖用户已有文件。

## 双更新路径（Git + Release）

整合包提供两种互补的更新方式：

| 方式 | 入口 | 适用场景 |
|------|------|----------|
| **Git 更新**（原有） | `Update-SD-Trainer.bat`、`update\update_sd_trainer.bat` | 7z 内含 `SD-Trainer/.git`；网络可访问 Git；日常增量更新 |
| **Release 更新**（新增） | `Update-SD-Trainer-Release.bat`、`update\update_from_release.bat` | 无 `.git` 的旧包；Git fetch 全部失败；希望与 GitHub Release 7z 完全对齐 |

Release 更新实现：`SD-Trainer/scripts/portable/update_from_release.ps1`

**版本标识（排障用，长期约定）**：

- 整合包：`SD-Trainer/VERSION`、`SD-Trainer/PORTABLE_BUILD`（构建 commit）
- 更新器：`SD-Trainer/scripts/portable/UPDATER_VERSION`（更新脚本逻辑版本；改 bat/ps1 行为时递增）
- 更新开始时会打印：**当前 VERSION / PORTABLE_BUILD**、**线上 main VERSION / 最新 Release**、**本地与线上 UPDATER_VERSION**
- **自更新（bootstrap）**：`Update-*.bat` 会先从 GitHub `main` 拉取最新更新脚本（含镜像回退），若有变化则自动重启后再执行 Git / Release 更新；网络失败时回退到本地 bundled 脚本

1. 通过 GitHub API 获取最新 `Next-Trainer-v*.7z` 资产（兼容旧名 `SD-Trainer-v*.7z`）
2. 下载到 `update/.cache/`（含 ghfast / ghproxy 镜像回退）
3. 7-Zip 解压到临时目录
4. `robocopy` 合并 `SD-Trainer/`（使用 `/IS /IT` 强制覆盖，**不用** `/XO`），排除用户数据目录
5. 从 Release 包刷新根目录启动脚本与 `update/` 快捷方式
6. 写入 `config/.portable_release_sync.json` 记录 Release 资产 id，便于同 VERSION 重发时识别

**同 VERSION 重发（hotfix republish）**：若 GitHub Release 仍为 `v2.7.0` 但替换了 7z 资产，请用 **`Update-SD-Trainer-Release.bat`**。旧脚本因 `robocopy /XO` 会跳过「本地较新」文件导致看似更新成功但代码未变；Git 更新（`Update-SD-Trainer.bat`）仅跟随 **commit**，若修复只重打 7z 未 push 到 main，Git 路径也无法获得修复。新包内含 `SD-Trainer/PORTABLE_BUILD`（git short SHA + 构建时间）便于对比是否已同步最新构建。

**Release 合并时保留**（不覆盖）：

```text
sd-models/  output/  logs/  train/   # 整合包根：junction，指向 SD-Trainer 内同名目录
huggingface/  tagger-models/
SD-Trainer/sd-models/  SD-Trainer/output/  SD-Trainer/logs/  SD-Trainer/train/  # 实际数据
SD-Trainer/extensions/          # Anima Fast 插件（若已安装）
SD-Trainer/config/autosave/
SD-Trainer/.cache/
```

大版本升级后若 WebUI 启动失败，提示用户运行 `update\update_dependencies.bat`。

打包前验收：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File `
  .\SD-Trainer\scripts\portable\verify_portable_updaters.ps1 `
  -PortableRoot .\build\SD-Trainer-Portable
```

## 更新脚本流程

### Git 更新（`Update-SD-Trainer.bat`）

`Update-SD-Trainer.bat` 推荐流程：

```text
1. 定位 <PortableRoot>/SD-Trainer
2. 如果不存在 SD-Trainer/.git：
   - 说明旧版发布包不能 git pull
   - 引导使用 `Update-SD-Trainer-Release.bat` 或下载最新 Release
   - 不显示"更新完成"
3. 检查 git 是否可用
4. 提示用户先关闭 WebUI
5. git fetch（带镜像回退）：
   - 先直连 origin → 失败后依次尝试 ghfast.top / ghproxy / gitmirror
   - 若整合包是浅克隆，使用 `--deepen=50` 补齐部分历史，避免看不到共同祖先导致 `--ff-only` 失败
   - 每个镜像之间等待 2 秒
   - 全部失败则输出排障建议并退出
6. 备份本地改动：
   - git stash push -u -m "portable-updater-<timestamp>"
   - 若无改动则跳过
7. 快进更新（三级 fallback）：
   - git merge --ff-only "origin/<branch>"
   - git merge --ff-only FETCH_HEAD
   - git pull --ff-only --depth=1 origin <branch>
8. 更新子模块：
   - 若整合包已内置 `dataset-tag-editor/scripts/launch.py` 但没有子模块 `.git` 元数据，直接复用内置文件，跳过 clone
   - 否则直连 GitHub → 失败后依次尝试 ghfast.top / ghproxy / gitmirror
   - 镜像尝试使用临时 `git -c submodule...url=...`，不要改写 `.gitmodules`
   - dataset-tag-editor 失败只 warning，加 `--depth=1` 减少传输量
9. 刷新根目录启动器：
   - scripts/portable/sync_portable_root_launchers.bat --nopause
10. 输出当前版本和成功提示
```

不要只执行裸 `git pull`。裸 `git pull` 会依赖当前分支、当前 remote 和用户本地状态，失败时对小白不友好。

### GitHub 镜像回退策略

国内直连 GitHub 高概率 `Connection was reset`，因此 fetch 阶段采用镜像自动回退：

| 顺序 | 方式 | URL 模式 |
|------|------|----------|
| 1 | 直连 | `git fetch origin <branch>` |
| 2 | ghfast.top | `git fetch https://ghfast.top/<origin_url> <branch>` |
| 3 | ghproxy | `git fetch https://mirror.ghproxy.com/<origin_url> <branch>` |
| 4 | gitmirror | `git fetch https://hub.gitmirror.com/<origin_url> <branch>` |

镜像站点为公益服务，可能不定期下线。后续维护时如发现某站不可用，替换为当前可用的镜像即可。备用域名汇总站：<https://ghproxy.link/>

### 浅克隆更新注意事项

整合包为了控制体积，只打入 `depth=1` 的 `.git`。如果更新脚本继续使用 `git fetch --depth=1` 获取最新提交，Git 可能把本地 `HEAD` 和 `origin/main` 都视为孤立浅提交，找不到共同祖先，从而误报：

```text
fast-forward update failed
```

因此浅克隆场景必须使用 `git fetch --deepen=50`，先补齐一段历史，再执行 `git merge --ff-only`。

## 首次依赖安装测速

`setup_environment.py` 不应只测试镜像首字节延迟。PyTorch wheel 约 3 GB，首响应快不代表大文件下载快。

当前策略：

- 直接测速 `torch-2.7.0+cu128` Windows wheel。
- 每个源最多读取 32 MB。
- 单源测速最多 15 秒，慢源按已下载数据计算 MB/s。
- 按真实吞吐量排序选择 PyTorch 源，官方源也参与测速。

## 依赖同步

代码更新不等于环境更新。更新成功后需要处理：

- `requirements.txt` 新增依赖。
- `setup_environment.py` 逻辑变化。
- xformers / torch 兼容约束变化。

建议第一版复用 `setup_environment.py`，让它判断已有环境是否满足要求。后续可新增 `scripts/portable/sync_dependencies.py`，专门处理便携包依赖同步，避免无脑重装 Torch。

## 失败处理

更新失败时必须明确说明：

- 失败步骤，例如 `git fetch`、`git pull`、依赖同步。
- 旧版本仍可继续使用。
- 如果创建了 stash，告诉用户 stash 名称。
- 如果需要手动处理，提示下载最新 Release 并保留用户数据目录。
- **全部镜像 fetch 失败时**：打印具体排障建议（检查网络、配置代理、手动下载）。

不要在失败后显示 `Done / 更新完成`。

## 测试清单

发布前至少验证：

- 运行 `scripts/portable/verify_portable_updaters.ps1 -PortableRoot <构建输出>` 全部 PASS
- 纯旧 7z、无 `.git`：`Update-SD-Trainer.bat` 引导 Release 更新并失败退出；`Update-SD-Trainer-Release.bat` 可 `-DryRun` 探测 API
- 新 7z、有 `.git`：`Update-SD-Trainer.bat` 能拉取 `origin/main`
- **Release 更新**：下载 + 合并后 `VERSION` 更新，`sd-models/`、`extensions/anima_lora/`（若存在）未丢失
- **国内无代理网络**：Git 直连失败后自动通过镜像成功拉取；Release 下载镜像回退可用
- 工作区有用户数据：`sd-models/`、`output/`、`logs/`、`config/` 更新后不丢失
- 工作区有本地改动：Git 更新脚本能 stash 或给出明确提示
- `dataset-tag-editor` 子模块更新失败：只 warning，不阻断主更新
- 更新后根目录 `run_gui.bat`、`Update-SD-Trainer-Release.bat` 被刷新
- 更新后仍能启动 WebUI

## 后续清理

- 移除 `mikazuki/dataset-tag-editor` 子模块，降低更新复杂度。
- 将官方默认配置与用户配置分离，避免 `config/` 参与 Git 冲突。
- 镜像列表可考虑从远程配置文件动态获取，避免硬编码过期。
