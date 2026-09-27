# Next Trainer

**Next Trainer** 是 Windows 本地训练 WebUI（GitHub 仓库名：`lora-scripts-next`）。  
支持 Anima / SD 1.5 / SDXL / Flux / **Krea 2** 的 LoRA 与全量微调，并可通过 DiffSynth 训练 Qwen-Image-2.1 LoRA；基于 [kohya-ss/sd-scripts](https://github.com/kohya-ss/sd-scripts)，可选 [musubi-tuner](https://github.com/kohya-ss/musubi-tuner) 与独立引擎运行环境，延续秋叶系训练体验。

> 产品品牌与发布归档一律为 **Next Trainer** / `Next-Trainer-v*.7z`。整合包内目录名 `SD-Trainer/`（及 `Update-SD-Trainer*.bat`）仍为兼容旧安装的启动契约，暂不改名。

[English](README.md) · [开源引用](docs/credits.md) · [NOTICE](NOTICE.md) · [CHANGELOG](CHANGELOG.md)

---

## 分支与版本（请先读）

| 分支 | 用途 | 界面 | 版本号 |
|------|------|------|--------|
| **`main`** | 稳定发布（切换前仍为旧 UI） | 旧版前端（预编译 dist） | **v2.9.1**（即将迁入 `legacy`） |
| **`dev`** | **Vue3 开发线（本 README）** | Vue 3 工作台 | **`3.0.0`** |

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

仓库根目录还提供直接使用 TOML 的训练入口：标准 Anima 后端使用
`train_anima_by_toml.sh`，可选 Anima Fast 运行时使用
`train_anima_fast_by_toml.sh`。

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
| **数据集** | 托管数据集根目录；创建/自动发现；可靠上传图片与 TXT；概览统计；ZIP 导出；可恢复删除；WD14 打标；**以图为主的标签编辑** |
| **任务** | 任务列表、状态、日志、预览 / Loss；日常盯盘以任务页为主 |
| **设置** | UI 偏好（含浅色/深色主题）、**训练引擎管理**（Kohya / Anima Fast / Musubi / DiffSynth）、**插件市场**、**下载源**（pip / PyTorch / HF / GitHub 镜像）、关于、更新日志 |
| **品牌与版本** | 产品名统一为 **Next Trainer**；正式号 **`3.0.0`**（预发布号仍会显示 RC 徽标） |
| **开源致谢** | 设置 → 关于；仓库另有 [开源引用](docs/credits.md) 子页 |

训练能力包括：

- Anima LoRA / LoKr / T-LoRA、Anima Fast（插件）、Anima 全量微调  
- SD 1.5 / SDXL LoRA 与全量微调、Flux LoRA  
- **Krea 2 LoRA**（可选 **Musubi-Tuner** 引擎，设置页安装）  
- **Qwen-Image-2.1 BF16 文生图 LoRA**（可选 **DiffSynth** 引擎，设置页安装；`dev` 集成阶段）
- 本地打标、训练监控（`/train-monitor`）、TensorBoard  

Anima Fast：[docs/anima-fast.md](docs/anima-fast.md) · Krea 2 多卡（Linux）：[docs/krea2-linux-multigpu.md](docs/krea2-linux-multigpu.md)

### 近期 `dev` 更新

- **数据集管理器：** `/dataset` 现在默认进入托管工作区，可配置数据集根目录，自动发现一级文件夹，并显示图片数、标注覆盖率、大小与更新时间。
- **可靠导入与导出：** 支持上传文件或拖入多层文件夹并保留相对路径；上传前集中预检冲突，明确选择全部跳过或全部覆盖。上传具备单文件/整批限制、图片与 TXT 可读性校验、进度展示和仅重试失败项；完整数据集可流式导出 ZIP。
- **可恢复删除：** 删除图片时会联动同名 TXT；文件或整个数据集删除后进入全局回收站。恢复时不会静默覆盖新文件，永久清空必须二次确认；数据集操作已串行化，避免上传、删除与恢复互相竞争。
- **工具互通：** 托管数据集可直接打开模型打标或标签编辑；编辑器内可下载单个托管文件，并把选中图片移入回收站。
- **Qwen 新手入口：** 首页优先展示 Qwen-Image-2.1 教程海报，并链接到更新后的入门教程。
- **运行时加固：** 引擎安装不再对空虚拟环境误报成功；使用 dataset config 时不再自动整理其训练目录；Anima Fast 增加明确的训练时长模式与验证集拆分设置。

### 数据集管理器

打开 **数据集 → 数据集管理**。默认托管根目录是 `./datasets`，相对路径按应用目录解析，不随进程启动目录变化；修改根目录不会自动搬迁旧数据。

当前支持：

- 创建数据集，并自动发现根目录下的一级数据集文件夹。
- 上传 PNG、JPG/JPEG、WebP、BMP 与 UTF-8 TXT，支持拖入多层文件夹。
- 上传前预检冲突、显示上传进度、仅重试失败文件，并异步查看数据集统计。
- 在编辑器下载单个文件，或流式导出整个数据集 ZIP；回收站与临时文件不会进入压缩包。
- 通过全局回收站软删除、恢复文件或整个数据集。
- 把同一数据集路径直接交给 WD14 打标或标签编辑器。

当前首期暂不包含：ZIP 上传/解压、重命名、视频/音频管理、自然语言打标、训练表单数据集选择器/校验，以及训练运行期间的数据写锁。

### DiffSynth / Qwen-Image-2.1（`dev`）

在 **设置 → 训练引擎** 中安装、检查、修复或卸载 DiffSynth，使用独立的 Python 3.12 / PyTorch 2.8 CUDA 12.8 环境。

- 模型可选择完整目录，或分别指定受支持的 BF16 DiT、文本编码器和 VAE 文件，支持 Comfy-Org 对应组件；Processor 资源自动管理。
- 数据集支持图片 + 同名 TXT（含 Kohya 风格子目录重复次数），也可使用 CSV / JSON / JSONL 元数据。
- 支持 TE/VAE 编码缓存、CPU 卸载、分桶、批量训练，以及按步数或 epoch 生成独立 Sample 预览。CPU 卸载与预览同时使用时需要开启编码缓存；缓存预览复用训练 DiT。
- 首版仅支持单卡 BF16 文生图 LoRA，暂不支持图像编辑、量化训练、全量微调或恢复完整优化器状态。

目前属于 `dev` 集成，不代表已有整合包已包含此引擎。合作者已反馈 CPU 卸载开启、关闭时都能生成预览并继续训练；导出 LoRA 在独立 ComfyUI 环境回载出图，仍是**进入 `main` 前的验收项**。

参数与限制见 [DiffSynth 使用说明](docs/diffsynth.md)。

### 界面预览

截图来自 `dev` / Vue3（`3.0.0` 线；界面语言为中文）。

#### 训练

| 标准（Kohya / Anima LoRA） | Anima Fast | Krea 2（Musubi） |
|---|---|---|
| ![训练 · 标准](assets/readme/vue3/01-training-standard.png) | ![训练 · Fast](assets/readme/vue3/02-training-fast.png) | ![训练 · Krea 2](assets/readme/vue3/08-training-krea2.png) |

#### 数据集

以下截图早于新的数据集管理首页；模型打标与标签编辑仍作为同一工作区中的标签页保留。

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
| Qwen-Image-2.1 | DiffSynth · 单卡 BF16 文生图 LoRA · `dev` 集成阶段 |

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
| DiffSynth / Qwen-Image-2.1 | [docs/diffsynth.md](docs/diffsynth.md) |
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
