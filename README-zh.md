# Next Trainer

**Next Trainer** 是 Windows 本地训练 WebUI（GitHub 仓库名：`lora-scripts-next`）。  
支持 Anima / SD 1.5 / SDXL / Flux / **FLUX.2 Klein** / **Krea 2** 的 LoRA 与全量微调；基于 [kohya-ss/sd-scripts](https://github.com/kohya-ss/sd-scripts)，可选 [musubi-tuner](https://github.com/kohya-ss/musubi-tuner) 与 [AI Toolkit](https://github.com/ostris/ai-toolkit)，延续秋叶系训练体验。

> 产品品牌与发布归档一律为 **Next Trainer** / `Next-Trainer-v*.7z`。整合包内目录名 `SD-Trainer/`（及 `Update-SD-Trainer*.bat`）仍为兼容旧安装的启动契约，暂不改名。

[English](README.md) · [开源引用](docs/credits.md) · [NOTICE](NOTICE.md) · [CHANGELOG](CHANGELOG.md)

---

## 分支与版本（请先读）

| 分支 | 用途 | 界面 | 版本号 |
|------|------|------|--------|
| **`main`** | 稳定发布 | Vue 3 工作台 | **`3.1.0`** |
| **`dev`** | 下一版本集成与验收 | Vue 3 工作台 | 跟随开发进度 |

反馈 Issue 时请附上侧栏或 `VERSION` 中显示的完整版本号。`legacy/v2.9.1` 保留旧 UI 基线，供回退与对照。

---

## 下载 Next Trainer 整合包

| 包 | 内容 | 下载 |
|----|------|------|
| **3.0.0 正式包** | lite / Kohya 分轨 | [GitHub Release v3.0.0](https://github.com/wochenlong/lora-scripts-next/releases/tag/v3.0.0) |
| **3.1.0** | 代码发布候选；整合包将在验收后发布 | [Releases](https://github.com/wochenlong/lora-scripts-next/releases) |

---

## 怎么用

### A. 整合包

1. 下载对应版本的正式包并解压到**非中文、非空格**路径
2. **lite** 用 `run_gui.bat`，满配/分轨包按包内说明（如 `启动.bat`）
3. 打开 **http://127.0.0.1:28000**  
4. 侧栏版本应与下载的 Release 一致

要求：Windows 10/11，NVIDIA GPU（建议 RTX 20+）。

补充说明：[整合包补充说明](docs/portable-getting-started.md) · [打标模型目录](docs/tagger-models.md) · [构建与发包（协作）](docs/portable-build-guide.md)

### B. 从源码运行

```powershell
git clone https://github.com/wochenlong/lora-scripts-next.git
cd lora-scripts-next

# Windows：准备环境后启动（需本机 Python 3.10）
.\run_gui.bat
# 或：python gui.py --dev
```

仓库根目录还提供直接使用 TOML 的训练入口：标准 Anima 后端使用
`train_anima_by_toml.sh`，可选 Anima Fast 运行时使用
`train_anima_fast_by_toml.sh`。

查看当前分支与版本：

```powershell
git branch --show-current
Get-Content VERSION         # 正式发布分支应为 3.1.0
```

前端源码在 `frontend/`（Vue 3 + Vite）。日常开发：

```powershell
cd frontend
npm install
npm run dev          # 热更新（需后端 gui 已启动）
npm run build        # 产物写入 frontend/dist，供 gui 静态托管
```

### C. 参与 `dev` 开发

```powershell
git fetch origin
git switch dev
# 若本地已有旧分支名，也可：git checkout -B dev origin/dev
git pull
```

回到稳定发布线：

```powershell
git switch main
git pull
```

> **注意：** `dev` 可能包含尚未进入稳定发布的改动。整合包用户以正式 Release 为准，不必手动切分支。

---

## Vue3 功能（3.1.0）

Next Trainer 使用 Vue 3 单页工作台：

| 模块 | 能力 |
|------|------|
| **训练** | 基础模型 × 训练引擎 × 训练目标；右侧 TOML 预览；校验 / 导入导出 / 开始训练 |
| **数据集** | 模型打标（内置 WD14）+ **以图为主的标签编辑**（顶栏数据源/加载；筛选与批量编辑在右侧面板） |
| **任务** | 任务列表、状态、日志、预览 / Loss；日常盯盘以任务页为主 |
| **设置** | UI 偏好（含浅色/深色主题）、**训练引擎管理**（Kohya / Anima Fast / Musubi / AI Toolkit）、插件市场、**下载源**（pip / PyTorch / HF / GitHub 镜像）、关于、更新日志 |
| **品牌与版本** | 产品名统一为 **Next Trainer**；当前正式号 **`3.1.0`** |
| **开源致谢** | 设置 → 关于；仓库另有 [开源引用](docs/credits.md) 子页 |

训练能力包括：

- Anima LoRA / LoKr / T-LoRA、Anima Fast（插件）、Anima 全量微调  
- SD 1.5 / SDXL LoRA 与全量微调、Flux LoRA  
- **FLUX.2 Klein LoRA**（可选 **AI Toolkit** 引擎，设置页安装）
- **Krea 2 LoRA**（可选 **Musubi-Tuner** 引擎，设置页安装）  
- 本地打标、训练监控（`/train-monitor`）、TensorBoard  

Anima Fast：[docs/anima-fast.md](docs/anima-fast.md) · Krea 2 多卡（Linux）：[docs/krea2-linux-multigpu.md](docs/krea2-linux-multigpu.md)

### 界面预览

截图来自 Vue 3 工作台（界面语言为中文）。

#### 训练

| 标准（Kohya / Anima LoRA） | Anima Fast | Krea 2（Musubi） |
|---|---|---|
| ![训练 · 标准](assets/readme/vue3/01-training-standard.png) | ![训练 · Fast](assets/readme/vue3/02-training-fast.png) | ![训练 · Krea 2](assets/readme/vue3/08-training-krea2.png) |

#### 数据集

| 模型打标 | 标签编辑 |
|---|---|
| ![数据集 · 打标](assets/readme/vue3/03-dataset-tagger.png) | ![数据集 · 标签编辑](assets/readme/vue3/04-dataset-editor.png) |

#### 任务

![任务](assets/readme/vue3/05-tasks.png)

#### 设置

| 界面偏好 | 训练引擎 |
|---|---|
| ![设置 · 界面](assets/readme/vue3/07-settings-ui.png) | ![设置 · 训练引擎](assets/readme/vue3/06-settings-engines.png) |

---

## 支持一览

| 模式 | 说明 |
|------|------|
| Anima LoRA | LoRA · LoKr · T-LoRA · 约 12GB 显存起 |
| Anima Fast | 可选独立运行时 · 建议 16GB+ · 设置页安装 |
| Anima 全量微调 | 完整 DiT · 建议约 24GB |
| SD 1.5 / SDXL | LoRA / 全量微调 |
| Flux | LoRA |
| Krea 2 | LoRA（Musubi）· 设置页安装引擎 · Linux 可多卡 |

显存与进阶参数见 [docs/anima-training.md](docs/anima-training.md)。

---

## 文档

| 主题 | 链接 |
|------|------|
| **开源引用（子页）** | [docs/credits.md](docs/credits.md) |
| 法律向完整 NOTICE | [NOTICE.md](NOTICE.md) |
| 整合包补充 | [docs/portable-getting-started.md](docs/portable-getting-started.md) |
| **整合包构建与发包（协作）** | [docs/portable-build-guide.md](docs/portable-build-guide.md) |
| 打标模型 | [docs/tagger-models.md](docs/tagger-models.md) |
| Anima Fast | [docs/anima-fast.md](docs/anima-fast.md) |
| **Krea 2 多卡（Linux 部署 + WebUI / `dev`）** | [docs/krea2-linux-multigpu.md](docs/krea2-linux-multigpu.md) |
| 训练监控 | [docs/train-monitor.md](docs/train-monitor.md) |
| 仓库布局契约 | [docs/repo-layout.md](docs/repo-layout.md) |
| 命令行入口（`train_anima_by_toml.sh` / `train_anima_fast_by_toml.sh`） | [docs/cli-args.md](docs/cli-args.md) |

---

## 常见问题（简）

**反馈 Bug 要带什么？**  
完整版本号（侧栏）、训练类型（模型/引擎/目标）、复现步骤、相关日志。→ [Issues](https://github.com/wochenlong/lora-scripts-next/issues)

**lite 和 kohya-musubi 怎么选？**  
弱网 / 轻量入口 → lite（首次启动装依赖）。要开箱 Kohya + Musubi（可训 Krea 2）→ **kohya-musubi**（魔搭）。Anima Fast 两包都需在设置页安装。

**3.x 和旧 UI 版本能混用配置吗？**
多数 TOML 可导入；导航与存储 key 有差异，以当前页「导入配置」为准。

---

<p align="center"><sub>维护：<a href="https://github.com/wochenlong">@wochenlong</a> · <a href="docs/credits.md">开源引用</a> · <a href="CONTRIBUTORS.md">贡献者</a></sub></p>
