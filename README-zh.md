# Next Trainer

**Next Trainer** 是 Windows 本地训练 WebUI（GitHub 仓库名：`lora-scripts-next`）。  
支持 Anima / SD 1.5 / SDXL / Flux / **Krea 2** 的 LoRA 与全量微调；基于 [kohya-ss/sd-scripts](https://github.com/kohya-ss/sd-scripts)，可选 [musubi-tuner](https://github.com/kohya-ss/musubi-tuner)，延续秋叶系训练体验。

> 产品品牌与发布归档一律为 **Next Trainer** / `Next-Trainer-v*.7z`。整合包内目录名 `SD-Trainer/`（及 `Update-SD-Trainer*.bat`）仍为兼容旧安装的启动契约，暂不改名。

[English](README.md) · [开源引用](docs/credits.md) · [NOTICE](NOTICE.md) · [CHANGELOG](CHANGELOG.md)

---

## 分支与版本（请先读）

| 分支 | 用途 | 界面 | 版本号 |
|------|------|------|--------|
| **`main`** | 稳定发布（切换前仍为旧 UI） | 旧版前端（预编译 dist） | **v2.9.1**（即将迁入 `legacy`） |
| **`dev`** | **Vue3 正式线（本 README）** | Vue 3 四栏工作台 | **`3.0.0`** |

**版本约定：** 预发布曾使用 **`2.9.x`**（`beta` → `rc`）；**本线正式号为 `3.0.0`**。默认分支切换与正式整合包发布后，请以侧栏版本与 Release 归档名为准。反馈 Issue 时请附上完整版本号。

---

## 下载 Next Trainer 整合包

| 包 | 内容 | 下载 |
|----|------|------|
| **3.0.0 正式包** | 准备中（lite / Kohya / Musubi 分轨） | 即将发布到 GitHub Release `v3.0.0` 与魔搭 |
| **RC 试用（仍可用）** | lite ~0.39 GB；kohya-musubi ~4.2 GB | [GitHub v2.9.2-rc.1-0813](https://github.com/wochenlong/lora-scripts-next/releases/tag/v2.9.2-rc.1-0813) · [魔搭 windsing/next-trainer-portable](https://modelscope.cn/datasets/windsing/next-trainer-portable) |

RC 魔搭示例路径：

```text
releases/v2.9.2-rc.1-0813/Next-Trainer-v2.9.2-rc.1-0813-kohya-musubi.7z
```

旧 UI 稳定包仍见 [Releases](https://github.com/wochenlong/lora-scripts-next/releases) 中 **v2.9.1**。

---

## 怎么用

### A. 整合包

1. **正式 3.0.0 包发布前**：可继续用上表 RC 包试用 Vue3（侧栏可能仍显示 rc；源码 `dev` 已为 `3.0.0`）  
2. 解压到**非中文、非空格**路径；**lite** 用 `run_gui.bat`，满配/分轨包按包内说明（如 `启动.bat`）  
3. 打开 **http://127.0.0.1:28000**  
4. 正式包侧栏应显示 **`v3.0.0`**

要求：Windows 10/11，NVIDIA GPU（建议 RTX 20+）。

补充说明：[整合包补充说明](docs/portable-getting-started.md) · [打标模型目录](docs/tagger-models.md) · [构建与发包（协作）](docs/portable-build-guide.md)

### B. 从源码运行 `dev`（Vue3）

```powershell
git clone https://github.com/wochenlong/lora-scripts-next.git
cd lora-scripts-next

# 切换到 Vue3 正式线（dev）
git fetch origin
git checkout dev
git pull origin dev

# Windows：准备环境后启动（需本机 Python 3.10）
.\run_gui.bat
# 或：python gui.py --dev
```

查看当前分支与版本：

```powershell
git branch --show-current   # 应为 dev
Get-Content VERSION         # 应为 3.0.0
```

前端源码在 `frontend/`（Vue 3 + Vite）。日常开发：

```powershell
cd frontend
npm install
npm run dev          # 热更新（需后端 gui 已启动）
npm run build        # 产物写入 frontend/dist，供 gui 静态托管
```

### C. 从 `main` 切到 `dev`（已有克隆）

```powershell
git fetch origin
git switch dev
# 若本地已有旧分支名，也可：git checkout -B dev origin/dev
git pull
```

回到稳定线：

```powershell
git switch main
git pull
```

> **注意：** `main` 与 `dev` 前端架构不同，不要混用未提交的 `frontend/dist` 热修。整合包用户以整包版本为准，不必手动切分支。

---

## Vue3 功能（`dev` / 3.0.0）

相对旧版侧栏多页 dist，**`dev` 为 Vue 3 单页工作台**：

| 模块 | 能力 |
|------|------|
| **训练** | 基础模型 × 训练引擎 × 训练目标；右侧 TOML 预览；校验 / 导入导出 / 开始训练 |
| **数据集** | 模型打标（内置 WD14）+ **以图为主的标签编辑**（顶栏数据源/加载；筛选与批量编辑在右侧面板） |
| **任务** | 任务列表、状态、日志、预览 / Loss；日常盯盘以任务页为主 |
| **设置** | UI 偏好（含浅色/深色主题）、**训练引擎管理**（Kohya / Anima Fast / Musubi）、**下载源**（pip / PyTorch / HF / GitHub 镜像）、关于、更新日志 |
| **品牌与版本** | 产品名统一为 **Next Trainer**；正式号 **`3.0.0`**（预发布号仍会显示 RC 徽标） |
| **开源致谢** | 设置 → 关于；仓库另有 [开源引用](docs/credits.md) 子页 |

训练能力包括：

- Anima LoRA / LoKr / T-LoRA、Anima Fast（插件）、Anima 全量微调  
- SD 1.5 / SDXL LoRA 与全量微调、Flux LoRA  
- **Krea 2 LoRA**（可选 **Musubi-Tuner** 引擎，设置页安装）  
- 本地打标、训练监控（`/train-monitor`）、TensorBoard  

Anima Fast：[docs/anima-fast.md](docs/anima-fast.md) · Krea 2 多卡（Linux）：[docs/krea2-linux-multigpu.md](docs/krea2-linux-multigpu.md)

### 界面预览

截图来自 `dev` / Vue3（`3.0.0` 线；界面语言为中文）。

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

**3.0.0 和旧稳定版能混用配置吗？**  
多数 TOML 可导入；导航与存储 key 有差异，以当前页「导入配置」为准。

---

<p align="center"><sub>维护：<a href="https://github.com/wochenlong">@wochenlong</a> · <a href="docs/credits.md">开源引用</a> · <a href="CONTRIBUTORS.md">贡献者</a></sub></p>
