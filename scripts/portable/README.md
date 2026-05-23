# 整合包（Portable）启动脚本

## 稳定目录契约（发布 7z 后勿改）

整合包根目录（用户双击处）：

```
<PortableRoot>/
  run_gui.bat              ← 用户主入口（薄转发，可随更新刷新）
  run_gui_portable.bat     ← 旧版兼容 shim（可选）
  python_embeded/          ← 嵌入式 Python（注意拼写 embeded）
  SD-Trainer/              ← 本项目副本（gui.py、setup_environment.py 在此）
```

**禁止**在发布物中改名：`python_embeded`、`SD-Trainer`、根目录 `run_gui.bat`。

## 启动链（推荐）

1. 用户双击 `<PortableRoot>/run_gui.bat`
2. 转发到 `SD-Trainer/scripts/portable/launch_portable.bat`（**随 git pull / 新 7z 更新**）
3. 首次运行调用 `SD-Trainer/setup_environment.py`，再 `python_embeded` 执行 `gui.py`

旧包若无 `scripts/portable/`，`run_gui.bat` 会回退到根目录 `run_gui_portable.bat`。

## 用户更新代码后

| 方式 | 操作 |
|------|------|
| **SD-Trainer 为 git 仓库** | 运行根目录 `Update-SD-Trainer.bat`，然后可选运行 `SD-Trainer\scripts\portable\sync_portable_root_launchers.bat` 刷新根目录 `run_gui.bat` |
| **仅解压 7z、无 git** | `Update-SD-Trainer.bat` 不能工作；下载新版 7z，保留 `sd-models`/`output`/`logs`，替换 `SD-Trainer` 与根目录 bat（或整包覆盖后拷回数据） |

## 与源码安装的区别

| | 整合包 | 源码 |
|--|--------|------|
| Python | `python_embeded` | 系统 / `venv` |
| 入口 | `run_gui.bat` → `launch_portable.bat` | `run_gui.bat` → `run_gui_source.bat` |
| 首次依赖 | `setup_environment.py` | `install-cn.ps1` |
| 默认打标模型 | 7z 内置 `huggingface/hub/`（wd14-convnextv2-v2） | `install-cn.ps1` + 每次启动 `prefetch_default_tagger.py --if-missing` |
