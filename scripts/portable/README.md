# 整合包（Portable）启动脚本

## 稳定目录契约（发布 7z 后勿改）

整合包根目录（用户双击处）：

```
<PortableRoot>/
  run_gui.bat              ← 用户主入口（薄转发，可随更新刷新）
  run_gui_portable.bat     ← 旧版兼容 shim（可选）
  python_embeded/          ← 嵌入式 Python（注意拼写 embeded）
  Next-Trainer/              ← 本项目副本（gui.py、setup_environment.py 在此）
```

**禁止**在发布物中改名：`python_embeded`、`Next-Trainer`、根目录 `run_gui.bat`。

## 启动链（推荐）

1. 用户双击 `<PortableRoot>/run_gui.bat`
2. 转发到 `Next-Trainer/scripts/portable/launch_portable.bat`（**随 git pull / 新 7z 更新**）
3. 首次运行调用 `Next-Trainer/setup_environment.py`，再 `python_embeded` 执行 `gui.py`

旧包若无 `scripts/portable/`，`run_gui.bat` 会回退到根目录 `run_gui_portable.bat`。

## 用户更新代码后

| 方式 | 操作 |
|------|------|
| **Next-Trainer 为 git 仓库** | 运行根目录 `Update-Next-Trainer.bat` 或 `update\update_next_trainer.bat`，然后可选运行 `Next-Trainer\scripts\portable\sync_portable_root_launchers.bat` 刷新根目录 `run_gui.bat` |
| **仅解压 7z、无 git** | 下载新版 7z，保留 `sd-models`/`output`/`logs`，替换 `Next-Trainer` 与根目录 bat（或整包覆盖后拷回数据） |

## 更新脚本版本（排障）

> 约定与历史变迁：[Discussion #73](https://github.com/wochenlong/lora-scripts-next/discussions/73)

- `Next-Trainer/scripts/portable/UPDATER_VERSION`：更新器逻辑版本（改 `Update-*.bat` / `update_from_release.ps1` 时递增）
- 运行 Git / Release 更新时，终端会打印 **当前 VERSION / PORTABLE_BUILD**、**线上 main / 最新 Release**、**本地与线上更新脚本版本**
- **Bootstrap**：每次更新前先从 GitHub `main` 同步最新更新脚本（`bootstrap_portable_updaters.ps1`），再执行实际更新；极旧包会先 curl 引导脚本
- 整合包：`Next-Trainer/PORTABLE_BUILD` 第一行为构建时 git short SHA

## 与源码安装的区别

| | 整合包 | 源码 |
|--|--------|------|
| Python | `python_embeded` | 系统 / `venv` |
| 入口 | `run_gui.bat` → `launch_portable.bat` | `run_gui.bat` → `run_gui_source.bat` |
| 首次依赖 | `setup_environment.py` | `install-cn.ps1` |
| 默认打标模型 | 7z 内置 `tagger-models/wd14/wd14-convnextv2-v2/`，其它模型需联网从 Hugging Face 下载 | `install-cn.ps1` + 每次启动 `prefetch_default_tagger.py --if-missing` |
| Hub 下载策略 | `MIKAZUKI_HUB_BACKEND=auto`（不强制魔搭）；内置 tokenizer/默认打标优先本地 | 源码 `auto`，按网络自动选择 |
| 文件选择器 | 启动时把 `sd-models/`、`output/`、`logs/`、`train/` 联接进 `Next-Trainer/`（`link_portable_data_dirs.py`） | 数据目录本来就在项目根 |

启动后**终端窗口**会显示打标模型下载进度与错误提示；不要关闭该窗口。

## 打标模型目录

整合包根目录包含 `tagger-models/`，用于放置用户可见的本地打标模型。默认 WD 模型位置：

```text
<PortableRoot>/tagger-models/wd14/wd14-convnextv2-v2/
  model.onnx
  selected_tags.csv
```

WD14 / CL 系列放在 `tagger-models/wd14/<model-key>/`，主要用于 tag 打标。VLM / 自然语言描述模型预留 `tagger-models/vlm/<model-key>/`。旧的一层目录 `tagger-models/<model-key>/` 仍兼容；文件缺失时会继续使用 `huggingface/` 缓存或在线下载。
