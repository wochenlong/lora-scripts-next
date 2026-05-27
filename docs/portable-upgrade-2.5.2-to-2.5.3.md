# 整合包升级指南：v2.5.2 → v2.5.3

v2.5.3 修复便携整合包在「`torch` 已存在但其它依赖不完整」时跳过环境安装，导致 **能打开网页却无法开始训练** 的问题（[Issue #54](https://github.com/wochenlong/lora-scripts-next/issues/54)）。

**请 v2.5.2 用户升级到 v2.5.3**，仅用手动进 `SD-Trainer` 跑 `gui.py` 属于临时规避，不能替代正式升级。

## 推荐方式：下载新整合包（最稳）

1. 在 [GitHub Releases](https://github.com/wochenlong/lora-scripts-next/releases) 下载 **SD-Trainer-v2.5.3** 整合包（7z）。
2. 解压到新目录（或先备份旧目录再覆盖代码部分）。
3. **保留并复制回** 以下用户数据（不要删）：
   - `sd-models/`
   - `output/`
   - `logs/`
   - `huggingface/`
   - `train/`
   - `config/`（含 `autosave/`）
4. 用新包根目录 **`run_gui.bat`** 启动。
5. 侧栏「Next Trainer」旁应显示 **`v2.5.3`**；若仍显示 `v2.5.2` 或没有版本 chip，说明仍在用旧文件。

## 可选方式：包内 Git 更新（仅当整合包带 `.git`）

若你的 v2.5.2 整合包是通过官方渠道获得、且 `SD-Trainer/` 内存在 `.git`：

1. 关闭正在运行的 SD-Trainer 窗口。
2. 双击 **`Update-SD-Trainer.bat`**，等待拉取完成。
3. 确认更新到包含 v2.5.3 的 tag 或 `main` 上对应提交后，再运行 **`run_gui.bat`**。

若更新后问题仍在，请改用「下载新整合包」方式，并检查是否误用了旧目录下的 `python_embeded`。

## 临时规避（未升级前）

在无法立即下载新包时，可：

1. 用整合包自带 Python：`<PortableRoot>\python_embeded\python.exe`
2. 进入 `SD-Trainer` 目录，执行：`gui.py`（**不要**加 `--skip-prepare-environment`）
3. 等待依赖补全完成后，以后仍建议升级到 v2.5.3 正式包。

## 如何确认已修复

- 启动日志 `sd-trainer-log.txt` 中可见 `[setup] Verifying embedded dependencies`；若曾缺依赖，会出现 `[Repair] Incomplete dependencies detected` 并跑 setup。
- 训练页点击「开始训练」不再出现「无法连接训练端」（在模型与数据路径正确的前提下）。

## 反馈

仍失败请附带整合包根目录 **`sd-trainer-log.txt`**，并在 [Issue #54](https://github.com/wochenlong/lora-scripts-next/issues/54) 或新 Issue 中说明是否已从 v2.5.2 升级、侧栏显示的版本号。
