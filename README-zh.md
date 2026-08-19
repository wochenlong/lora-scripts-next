# Next Trainer

<p align="center">
  <img src="assets/readme/next-trainer-cover.png" alt="Next Trainer" width="720" />
</p>

<p align="center">
  <strong>本地 Windows 训练 WebUI</strong><br />
  Anima · SD 1.5 · SDXL · Flux · Krea 2<br />
  <sub>GitHub 仓库名：<code>lora-scripts-next</code></sub>
</p>

<p align="center">
  <a href="README.md">English</a>
  ·
  <a href="docs/credits.md">开源引用</a>
  ·
  <a href="CHANGELOG.md">更新日志</a>
  ·
  <a href="https://github.com/wochenlong/lora-scripts-next/releases">Releases</a>
</p>

---

## `main` 已切换（请先读）

**默认分支 `main` 已从旧版多页 UI（v2.9.1）切换为 Vue 3 工作台（`3.0.0`）。**

| | |
|---|---|
| **改了什么** | 默认检出 / 跟踪 `main` 时，得到的是 **Vue 3 四栏工作台**（训练 · 数据集 · 任务 · 设置），产品正式号为 **`3.0.0`**。旧版侧栏多 HTML 前端不再是 `main` 的默认内容。 |
| **为什么改** | Vue 3 线在 `dev` 上完成内测与关键门禁后，需要成为**默认稳定基线**：统一品牌（Next Trainer）、统一 IA、降低「默认分支还是旧 UI」的混淆，并让后续修复与正式整合包都落在同一条线上。 |
| **没改什么** | 整合包内目录名 `SD-Trainer/`、更新脚本文件名等**启动契约**暂时保留，兼容已有安装。训练引擎（Kohya / Anima Fast / Musubi）仍为可选项，按包体与设置页安装。 |

> **合 `main` ≠ 立刻推正式 3.0.0 整合包。** 源码默认线已是 3.0.0；正式 7z / 「点更新」仍以 GitHub Release 为准，建议先浸泡再全量推送。

### 需要旧版 `main`（v2.9.1 UI）？

旧稳定线已完整备份，可随时回退对照：

| 资源 | 链接 |
|------|------|
| **分支 `legacy/v2.9.1`** | [github.com/…/tree/legacy/v2.9.1](https://github.com/wochenlong/lora-scripts-next/tree/legacy/v2.9.1) |
| **标签 `legacy-v2.9.1-pre-vue3`** | [github.com/…/releases/tag/legacy-v2.9.1-pre-vue3](https://github.com/wochenlong/lora-scripts-next/releases/tag/legacy-v2.9.1-pre-vue3)（与转正前 `main` tip 同一提交） |
| **旧 UI 整合包** | [Releases → v2.9.1](https://github.com/wochenlong/lora-scripts-next/releases/tag/v2.9.1) |

源码检出旧线：

```powershell
git fetch origin
git switch legacy/v2.9.1
# 或固定到标签：
# git switch --detach legacy-v2.9.1-pre-vue3
```

---

## 这是什么

**Next Trainer** 面向本地 Windows（NVIDIA）的 LoRA / 全量微调 WebUI。  
基于 [kohya-ss/sd-scripts](https://github.com/kohya-ss/sd-scripts)，可选 [musubi-tuner](https://github.com/kohya-ss/musubi-tuner)；延续秋叶系训练习惯，产品名与发布归档统一为 **Next Trainer** / `Next-Trainer-v*.7z`。

---

## 分支怎么选

| 分支 | 角色 | 界面 | 版本 |
|------|------|------|------|
| **`main`** | **当前默认稳定线** | Vue 3 工作台 | **`3.0.0`** |
| **`dev`** | 继续试验、预发布功能 | 同为 Vue 3（可能超前 `main`） | 跟随试验 |
| **`legacy/v2.9.1`** | 旧 UI 备份，不默认开发 | 旧版预编译前端 | **v2.9.1** |

反馈 Issue 时请附上侧栏完整版本号与分支（或整合包 Release 名）。

---

## 下载整合包

| 包 | 说明 | 获取 |
|----|------|------|
| **3.0.0 正式包** | 准备中（lite / Kohya / Musubi 分轨） | 即将发布到 GitHub `v3.0.0` 与魔搭 |
| **RC 试用** | lite ~0.39 GB；kohya-musubi ~4.2 GB（Vue 3 预览可用） | [v2.9.2-rc.1-0813](https://github.com/wochenlong/lora-scripts-next/releases/tag/v2.9.2-rc.1-0813) · [魔搭](https://modelscope.cn/datasets/windsing/next-trainer-portable) |
| **旧 UI 稳定包** | 多页 dist / v2.9.1 | [v2.9.1](https://github.com/wochenlong/lora-scripts-next/releases/tag/v2.9.1) |

魔搭 RC 示例路径：

```text
releases/v2.9.2-rc.1-0813/Next-Trainer-v2.9.2-rc.1-0813-kohya-musubi.7z
```

要求：Windows 10/11，NVIDIA GPU（建议 RTX 20+）；解压路径避免中文与空格。

补充：[整合包说明](docs/portable-getting-started.md) · [打标模型](docs/tagger-models.md) · [构建与发包（协作）](docs/portable-build-guide.md)

---

## 快速开始

### 整合包

1. 解压后运行 `run_gui.bat`（或包内写明的启动脚本）  
2. 浏览器打开 **http://127.0.0.1:28000**  
3. 正式 3.0.0 包侧栏应显示 **`v3.0.0`**（RC 包可能仍带 rc 徽标）

### 从源码跑当前 `main`（Vue 3）

```powershell
git clone https://github.com/wochenlong/lora-scripts-next.git
cd lora-scripts-next
git checkout main
git pull

.\run_gui.bat
# 或：python gui.py --dev
```

```powershell
git branch --show-current   # main
Get-Content VERSION         # 3.0.0
```

前端工程在 `frontend/`（Vue 3 + Vite）：

```powershell
cd frontend
npm install
npm run dev      # 热更新（需后端已启动）
npm run build    # 写入 frontend/dist
```

### 跟着试验线 `dev`

```powershell
git fetch origin
git switch dev
git pull
```

> `main` / `dev` / `legacy` 前端架构不同，不要混提未提交的 `frontend/dist` 热修。整合包用户以整包版本为准。

---

## 功能一览

| 模块 | 能力 |
|------|------|
| **训练** | 基础模型 × 引擎 × 目标；右侧 TOML 预览；校验 / 导入导出 / 开训 |
| **数据集** | WD14 打标；以图为主的标签编辑（筛选与批量在右侧） |
| **任务** | 列表、状态、日志、预览 / Loss；日常盯盘入口 |
| **设置** | 主题与 UI、引擎管理（Kohya / Anima Fast / Musubi）、下载源镜像、关于与更新日志 |

训练后端：Anima LoRA / Fast / 全量、SD·SDXL、Flux（Kohya）；可选 **Krea 2**（Musubi）。另有本地打标、`/train-monitor`、TensorBoard。

- Anima Fast → [docs/anima-fast.md](docs/anima-fast.md)  
- Krea 2 多卡（Linux）→ [docs/krea2-linux-multigpu.md](docs/krea2-linux-multigpu.md)

### 界面预览

截图来自 Vue 3（`3.0.0` 线，中文界面）。

<details open>
<summary><strong>训练</strong></summary>

| 标准（Kohya / Anima） | Anima Fast | Krea 2（Musubi） |
|---|---|---|
| ![训练 · 标准](assets/readme/vue3/01-training-standard.png) | ![训练 · Fast](assets/readme/vue3/02-training-fast.png) | ![训练 · Krea 2](assets/readme/vue3/08-training-krea2.png) |

</details>

<details>
<summary><strong>数据集</strong></summary>

| 模型打标 | 标签编辑 |
|---|---|
| ![打标](assets/readme/vue3/03-dataset-tagger.png) | ![标签编辑](assets/readme/vue3/04-dataset-editor.png) |

</details>

<details>
<summary><strong>任务</strong></summary>

![任务](assets/readme/vue3/05-tasks.png)

</details>

<details>
<summary><strong>设置</strong></summary>

| 界面偏好 | 训练引擎 |
|---|---|
| ![设置 · 界面](assets/readme/vue3/07-settings-ui.png) | ![设置 · 引擎](assets/readme/vue3/06-settings-engines.png) |

</details>

---

## 支持的模式

| 模式 | 说明 |
|------|------|
| Anima LoRA | LoRA · LoKr · T-LoRA · 约 12GB 显存起 |
| Anima Fast | 可选独立运行时 · 建议 16GB+ · 设置页安装 |
| Anima 全量 | 完整 DiT · 建议约 24GB |
| SD 1.5 / SDXL | LoRA / 全量微调 |
| Flux | LoRA |
| Krea 2 | LoRA（Musubi）· 设置页装引擎 · Linux 可多卡 |

显存与参数：[docs/anima-training.md](docs/anima-training.md)

---

## 文档

| 主题 | 链接 |
|------|------|
| 开源引用 | [docs/credits.md](docs/credits.md) |
| NOTICE | [NOTICE.md](NOTICE.md) |
| 整合包补充 | [docs/portable-getting-started.md](docs/portable-getting-started.md) |
| 构建与发包 | [docs/portable-build-guide.md](docs/portable-build-guide.md) |
| 打标模型 | [docs/tagger-models.md](docs/tagger-models.md) |
| 训练监控 | [docs/train-monitor.md](docs/train-monitor.md) |
| 仓库布局契约 | [docs/repo-layout.md](docs/repo-layout.md) |

---

## 常见问题

**Bug 反馈要带什么？**  
侧栏完整版本、训练类型（模型/引擎/目标）、复现步骤、相关日志。→ [Issues](https://github.com/wochenlong/lora-scripts-next/issues)

**lite 和 kohya-musubi 怎么选？**  
弱网 / 轻量 → lite（首次装依赖）。要开箱 Kohya + Musubi（可训 Krea 2）→ **kohya-musubi**。Anima Fast 均需在设置页安装。

**3.0.0 和旧稳定版能混用配置吗？**  
多数 TOML 可导入；导航与本地存储 key 有差异，以当前页「导入配置」为准。

**更新后界面全变了？**  
这是预期行为：`main` 已是 Vue 3。若必须使用旧 UI，请切到 [`legacy/v2.9.1`](https://github.com/wochenlong/lora-scripts-next/tree/legacy/v2.9.1) 或安装 [v2.9.1 整合包](https://github.com/wochenlong/lora-scripts-next/releases/tag/v2.9.1)。

---

<p align="center">
  <sub>
    维护 <a href="https://github.com/wochenlong">@wochenlong</a>
    ·
    <a href="docs/credits.md">开源引用</a>
    ·
    <a href="CONTRIBUTORS.md">贡献者</a>
  </sub>
</p>
