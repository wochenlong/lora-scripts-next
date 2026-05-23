# 整合包打包注意事项与 Git 更新方案

本文记录 Windows 便携整合包的打包契约，以及将整合包改为“保留 `.git`、支持一键 Git 更新”后的实现方案。

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
  Download-Anima-Model.bat
  install_xformers.bat
  python_embeded/
  SD-Trainer/
  sd-models/
  output/
  logs/
  huggingface/
```

这些路径被用户快捷方式、启动脚本和文档绑定，不要随意改名。

## 构建来源要求

不要把维护者当前开发工作区原样打进整合包。构建时应使用干净来源：

1. 从 `origin/main` 或指定 release tag 创建干净 clone / worktree。
2. 确认没有未提交改动。
3. 保留主仓 `.git`。
4. 确保 remote 指向 `https://github.com/wochenlong/lora-scripts-next.git`。
5. 不要带入本机 `doc/`、`data/`、`benchmark/`、`.vscode/`、`.cursor/`、临时草稿等目录。

`vendor/sd-scripts` 已经是主仓 tracked 普通目录，不是子模块，会随主仓更新。

## 子模块策略

当前唯一子模块是：

```text
mikazuki/dataset-tag-editor
```

它已很久不更新，后续计划移除。现阶段更新脚本可继续尝试：

```bat
git submodule update --init --recursive
```

但该子模块更新失败只能作为 warning，不应阻断主仓更新。用户训练主流程不应因为标签编辑器子模块失败而无法完成代码更新。

## 用户数据保护

这些目录或文件视为用户数据，更新时不得覆盖：

```text
sd-models/
output/
logs/
huggingface/
train/
config/
toml/autosave/
assets/config.json
config/.update_cache.json
sd-trainer-log.txt
```

其中 `config/` 整体按用户目录处理。后续如果需要发布默认配置，应放在 `assets/defaults/` 或其他只读模板目录，启动时仅在目标不存在时复制到 `config/`，不能覆盖用户已有文件。

## 更新脚本流程

`Update-SD-Trainer.bat` 推荐流程：

```text
1. 定位 <PortableRoot>/SD-Trainer
2. 如果不存在 SD-Trainer/.git：
   - 说明旧版发布包不能 git pull
   - 引导下载最新 Release
   - 不显示“更新完成”
3. 检查 git 是否可用
4. 提示用户先关闭 WebUI
5. git fetch origin
6. 备份本地改动：
   - git stash push -u -m "portable-updater-<timestamp>"
   - 若无改动则跳过
7. 切换到 main：
   - git checkout main
8. 快进更新：
   - git pull --ff-only origin main
9. 更新子模块：
   - dataset-tag-editor 失败只 warning
10. 刷新根目录启动器：
   - scripts/portable/sync_portable_root_launchers.bat --nopause
11. 同步依赖：
   - 运行 setup_environment.py 或专门的依赖同步脚本
12. 输出当前版本和成功提示
```

不要只执行裸 `git pull`。裸 `git pull` 会依赖当前分支、当前 remote 和用户本地状态，失败时对小白不友好。

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

不要在失败后显示 `Done / 更新完成`。

## 测试清单

发布前至少验证：

- 纯旧 7z、无 `.git`：更新脚本给出下载新版提示并失败退出。
- 新 7z、有 `.git`：更新脚本能拉取 `origin/main`。
- 工作区有用户数据：`sd-models/`、`output/`、`logs/`、`config/` 更新后不丢失。
- 工作区有本地改动：更新脚本能 stash 或给出明确提示。
- `dataset-tag-editor` 子模块更新失败：只 warning，不阻断主更新。
- 更新后根目录 `run_gui.bat` 被刷新。
- 更新后仍能启动 WebUI。

## 后续清理

- 移除 `mikazuki/dataset-tag-editor` 子模块，降低更新复杂度。
- 将官方默认配置与用户配置分离，避免 `config/` 参与 Git 冲突。
- 给 `Update-SD-Trainer.bat` 增加更清晰的进度和错误码。
