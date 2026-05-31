# 仓库根目录说明

## 不能移动 / 不能改名的契约

### 所有用户

| 路径 | 原因 |
|------|------|
| `gui.py` | 服务主程序 |
| `setup_environment.py` | 整合包首次安装（`SD-Trainer/setup_environment.py`） |
| `run_gui.bat` | Windows 主入口（整合包根目录 + 源码） |
| `Download-Anima-Model.bat` | 一键下载 Anima 三件套到 `sd-models/anima/`（整合包根 / 源码根） |
| `requirements.txt` / `VERSION` | 依赖与版本 |

### 整合包（Portable 7z）

```
<PortableRoot>/
  run_gui.bat
  python_embeded/          # 拼写为 embeded
  SD-Trainer/                # 项目副本
```

启动逻辑：`SD-Trainer/scripts/portable/launch_portable.bat`（随更新变化）。

### 云镜像（AutoDL 等）

| 路径 | 原因 |
|------|------|
| `start_autodl.sh` | 镜像开机命令写死此路径 |

## 根目录转发器（可保留文件名，实现已迁走）

| 根目录 | 实际实现 |
|--------|----------|
| `start_lora_next.sh` 等 | `scripts/autodl/` |
| `train.ps1` / `train.sh` | `scripts/cli/` |
| `apply_lora_next_anima_defaults.py` | `scripts/autodl/`（shim） |
| `run_gui_cn.sh` | `USE_CN_MIRROR=1` + `run_gui.sh` |

## 本地 vs 公开命名（勿混用）

| 目录 | Git | 用途 |
|------|-----|------|
| `docs/` | 跟踪 | 对外文档（复数 `docs`） |
| `doc/` | **忽略** | 仅本地 Markdown / 交接 / Issue 调查（单数 `doc`） |
| `scripts/` | 跟踪 | 仓库正式脚本（复数 `scripts`） |
| `script/` | **忽略** | 个人或 Agent 一次性脚本（单数 `script`），建议 `script/ops/`、`script/scratch/` |

Agent 内部操作说明（Token、Release、本机路径等）：`doc/local/AGENT_INTERNAL.md`（随 `doc/` 不入库）。Cursor 总入口：`.cursor/rules/00-project-overview.mdc`。

## 推荐目录

| 目录 | 内容 |
|------|------|
| `scripts/portable/` | 整合包启动 |
| `scripts/autodl/` | 云 GPU 运维 |
| `scripts/cli/` | 旧式 CLI 训练 |
| `legacy/` | 打标 / notebook 等上游工具 |
| `doc/local/` | 本地交接与 Issue 草稿（不上传 GitHub）；`AGENT_INTERNAL.md` 放此处 |
| `docs/team/` | 协作约定、[backlog 总表](team/backlog-priorities.md)、优先级草案、风险备忘录（维护者，不上主页） |
| `mikazuki/` / `vendor/` / `train_monitor/` / `frontend/` | 主产品代码 |

## 日常开发记一句

- **Windows 本地 / 整合包**：双击 `run_gui.bat`
- **Linux 源码**：`bash run_gui.sh` 或 `USE_CN_MIRROR=1 bash run_gui.sh`
- **云镜像开机**：`start_autodl.sh`（勿动路径）
- **不要用**根目录秋叶 CLI 训 Anima，除非你知道自己在走 `scripts/cli` 旁路
