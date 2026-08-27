# Python 3.12 适配与训练引擎统一 · 项目计划

> 目标：将 lora-scripts-next 主程序（GUI + sd-scripts 底层）、anima-fast、musubi-tuner 三套训练栈统一到 **CPython 3.12**。

## 1. 现状调研结论

| 组件 | 当前 Python | 位置 | 关键约束 |
|---|---|---|---|
| 主程序（mikazuki GUI + vendor/sd-scripts） | 3.10（venv 实测 3.10.20） | `venv/`、`setup_environment.py` | torch 2.7.0+cu128、numpy 1.26.4、gradio 3.44.2 |
| anima-fast（extensions/anima_lora） | **3.13**（上游 `pyproject.toml` 写死 `==3.13.*`） | `mikazuki/anima_fast_backend/` | torch 2.11/2.12 nightly + CUDA 13、transformers>=5.3、numpy>=2 |
| musubi-tuner | 3.12（`MUSUBI_PYTHON_VERSION = "3.12"`） | `mikazuki/musubi_backend/` | 上游要求 `>=3.10,<3.13`，已是 3.12 |

硬编码 3.10 / 3.13 的位置（必须改）：

- `setup_environment.py:24` — `PYTHON_TAG = "cp310"`，torch wheel 名拼接
- `build-scripts/01-prepare-python.ps1:13` — 下载 `python-3.10.11-embed-amd64.zip`
- `mikazuki/anima_fast_backend/environment.py` — `uv python install 3.13`、`cpython-3.13.*` 探测 pattern（:407-409）、审计 `python_major_minor: "3.13"`（:88）
- `extensions/anima_lora/source/pyproject.toml:5` — `requires-python = "==3.13.*"`
- 已存在的 uv 管理解释器 `.python/cpython-3.13.12-*/`（需替换为 3.12）
- `Dockerfile` 基础镜像 `nvcr.io/nvidia/pytorch:24.07-py3`（内置 py3.10，需换 24.12+ 或改用官方 python:3.12 基底）
- `install.bash` / `install.ps1` — `python3 -m venv venv` 依赖系统 python，需要求/引导 3.12

正面结论：

- 全仓库（mikazuki、vendor/sd-scripts、scripts/dev）未发现 `distutils`、`imp`、`getargspec` 等 3.12 已移除 stdlib 的使用，代码层面迁移阻力小。
- torch 2.7.0+cu128、numpy 1.26.4、sentencepiece 0.2.0、tensorboard 2.14、bitsandbytes、transformers 4.51.3、diffusers 0.33.1 均有 cp312 wheel。

## 2. 关键决策：统一到一个 venv 还是统一到同一解释器版本

**建议：统一到「同一 CPython 3.12 解释器」，保留三个独立 venv（低风险方案 A）。**

完全合并成单一 venv（方案 B）短期不可行，依赖存在硬冲突：

| 依赖 | 主栈 (sd-scripts) | anima-fast | 冲突 |
|---|---|---|---|
| torch | 2.7.0+cu128 | 2.11/2.12 nightly +cu13x | ✗ ABI/驱动不同 |
| transformers | 4.51.3 | >=5.3.0 | ✗ 跨大版本 |
| numpy | 1.26.4 | >=2.0 | ✗ ABI |
| diffusers | 0.33.1 | >=0.37.0 | ✗ |
| accelerate | 0.33.0 | >=1.13.0 | ✗ |
| huggingface-hub | 0.36.2 | >=1.9.0 | ✗ |

方案 B 需等 sd-scripts 底层整体升级到新 torch/transformers 世代，作为独立长期项目另行立项。

## 3. 工作分解（WBS）

### 阶段 0 · 基线与验证环境（0.5 天）
- [ ] 锁定验证机：CUDA 驱动满足 cu128 与 cu13x；准备 py3.12 解释器
- [ ] 跑通现有 `tests/`（pytest）作为回归基线
- [ ] 记录当前三条训练链路（sd-scripts / anima-fast / musubi）各跑一次冒烟训练的配置与结果

### 阶段 1 · 主程序 3.10 → 3.12（约 2–3 天）
1. **安装器/打包**
   - `setup_environment.py`：`PYTHON_TAG` → `cp312`，校验阿里云/SJTUG 镜像是否有 `torch-2.7.0+cu128-cp312` wheel；同步 `run_gui*.sh/.bat/.ps1` 的 python 探测
   - `build-scripts/01-prepare-python.ps1`：embedded python 3.10.11 → 3.12.x（同步 `.pth`、get-pip 流程）
   - `Dockerfile` / `Dockerfile-for-Mainland-China`：基底镜像升级到 py3.12（NGC 24.12+ 或自建 python:3.12 + CUDA）
2. **requirements.txt 逐项核对 cp312 兼容性**
   - 重点风险项：
     - `opencv-python==4.8.1.78` — 若无 cp312 wheel 则升到 4.10+
     - `pytorch-lightning==1.9.0` — 老版本，3.12 下需实测 import；不行则升 2.x 或裁剪（sd-scripts 仅少量模块用到）
     - `gradio==3.44.2` + `fastapi==0.95.1` — 依赖 pydantic 1.10.x，需 ≥1.10.13 才有 3.12 支持；gradio 3.x 在 3.12 需实测
     - `triton-windows<3.4`、`onnxruntime-gpu`、flash-attn 预编译 wheel（`install_flash_attn.*`、`scripts/portable`）— 全部需要 cp312 构建
   - `numpy==1.26.4`：3.12 官方支持，但需确认 `lycoris-lora==3.3.0`、`dadaptation` 等下层包不拉 numpy2
3. **代码兼容性扫描与修复**
   - 全量 grep：`distutils`、`imp`、`pkg_resources`（3.12 需 setuptools）、`asyncio.coroutine`、`datetime.utcnow`、`re` 非法转义告警
   - `mikazuki/musubi_backend/settings.py` 中 `import tomllib / fallback toml` 分支在 3.12 下恒走 tomllib，可简化
4. **回归**：GUI 启动、WD14 打标（onnxruntime）、sd-scripts SDXL/Flux LoRA 冒烟训练

### 阶段 2 · anima-fast 3.13 → 3.12（约 2–3 天，风险最高）
1. **上游依赖可行性验证（先做，阻塞项）**
   - 确认 `torch 2.11 stable / 2.12 nightly` 是否仍发布 **cp312** wheel（PyTorch 正逐步放弃旧小版本；若 2.12 只出 cp313，则此阶段方案需改为「anima-fast 保持 3.13」或「降级其 torch」并重新评估）
   - 确认对应 torch ABI 的 flash-attn 2 预编译 wheel 是否有 cp312 版本（否则按 `docs/optimizations/cuda132.md` 自编译）
2. **打补丁**
   - `extensions/anima_lora/source/pyproject.toml`：`requires-python` → `==3.12.*`，重新 `uv lock`
   - `mikazuki/anima_fast_backend/environment.py`：uv 安装 3.13 → 3.12（:474-487）、探测 pattern `cpython-3.13.*` → `cpython-3.12.*`（:407-409）、`base_python` 路径（:206-209）
   - 审计期望 `python_major_minor: "3.13"` → `"3.12"`（:88）
   - 清理/重建 `.python/cpython-3.13.12-*` 与 anima-fast `.venv`
3. **回归**：anima-fast 完整链路（preprocess → cache → train），对比 Loss 曲线无异常

### 阶段 3 · musubi-tuner 对齐（约 0.5 天）
- 上游本就要求 `>=3.10,<3.13`，当前已用 3.12，主要工作：
  - 确认 musubi 安装流程使用与全局一致的 3.12 来源（uv 或系统）
  - 环境自检文案/审计断言复核（`musubi_backend/environment.py:194`）
  - Krea 2 冒烟训练

### 阶段 4 · 收尾（约 1 天）
- 文档：`README*.md`、`docs/`、安装向导中所有 python 版本说明
- 安装预检 `install_preflight.ps1` 的版本检查逻辑
- `CHANGELOG.md` 记录 breaking change：旧 3.10 venv 不可复用，需重建
- 全平台验证矩阵：Linux x86_64 / Windows portable / Docker

## 4. 风险清单

| 风险 | 等级 | 应对 |
|---|---|---|
| torch 2.12 nightly 无 cp312 wheel → anima-fast 无法降到 3.12 | 高 | 阶段 2 第 1 步先验证；不行则 anima-fast 维持 3.13，项目目标改为「主栈+musubi 上 3.12」 |
| flash-attn 无对应 cp312+新 torch 的预编译 wheel | 中 | 预留自编译构建脚本（CUDA toolkit + MSVC） |
| gradio 3.44 / pytorch-lightning 1.9 在 3.12 下隐性故障 | 中 | 阶段 1 冒烟覆盖；必要时小版本升级 |
| 镜像站（阿里云/SJTUG）缺 cp312 torch wheel | 中 | 回退 PyTorch 官方源，或更换 torch 版本 |
| 三 venv 并存磁盘/显存开销不变，用户预期"合成一个" | 低 | 文档明确说明方案 A 的理由与方案 B 的长期规划 |

## 5. 里程碑与工期估算

| 里程碑 | 内容 | 工期 |
|---|---|---|
| M1 | 阶段 0+1：主程序 3.12 跑通，GUI/打标/sd-scripts 训练回归通过 | ~3.5 天 |
| M2 | 阶段 2：anima-fast 降到 3.12 并回归（含可行性验证 gate） | ~2.5 天 |
| M3 | 阶段 3+4：musubi 对齐、文档、全平台验证、发版 | ~1.5 天 |

合计约 **7–8 个工作日**（不含方案 B 的依赖大统一）。
