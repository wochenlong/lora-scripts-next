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

## `main` 已切换到 Vue 3

默认分支 **`main`** 现在是 **Vue 3 工作台 · v3.0.0**（训练 · 数据集 · 任务 · 设置），不再是旧版多页 UI。

Vue 3 已在 `dev` 完成内测与关键门禁；转正是为了统一品牌与信息架构，让稳定修复与后续正式包落在同一条默认线上。整合包目录名 `SD-Trainer/`、更新脚本文件名等启动契约暂时保留。

正式整合包仍以 [GitHub Releases](https://github.com/wochenlong/lora-scripts-next/releases) 为准，不会因源码合入 `main` 就立刻全量推送。

### 需要旧版 UI？

- 源码分支：[legacy/v2.9.1](https://github.com/wochenlong/lora-scripts-next/tree/legacy/v2.9.1)
- 转正前快照标签：[legacy-v2.9.1-pre-vue3](https://github.com/wochenlong/lora-scripts-next/releases/tag/legacy-v2.9.1-pre-vue3)
- 旧 UI 整合包：[v2.9.1](https://github.com/wochenlong/lora-scripts-next/releases/tag/v2.9.1)

```powershell
git fetch origin
git switch legacy/v2.9.1
```

---

## 这是什么

**Next Trainer** 是面向本地 Windows（NVIDIA）的 LoRA 与全量微调 WebUI。  
基于 [kohya-ss/sd-scripts](https://github.com/kohya-ss/sd-scripts)，也可选装 [musubi-tuner](https://github.com/kohya-ss/musubi-tuner)，整体延续秋叶系训练习惯。

产品品牌与发布归档统一为 **Next Trainer**，压缩包命名形如 `Next-Trainer-v*.7z`。

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
| **3.0.0 正式包** | 准备中，将提供 lite、Kohya、Musubi 等分轨 | 即将发布到 GitHub `v3.0.0` 与魔搭 |
| **RC 试用** | lite 约 0.39 GB；kohya-musubi 约 4.2 GB，可用于体验 Vue 3 | [v2.9.2-rc.1-0813](https://github.com/wochenlong/lora-scripts-next/releases/tag/v2.9.2-rc.1-0813) · [魔搭](https://modelscope.cn/datasets/windsing/next-trainer-portable) |
| **旧 UI 稳定包** | 旧版多页界面，对应 v2.9.1 | [v2.9.1](https://github.com/wochenlong/lora-scripts-next/releases/tag/v2.9.1) |

魔搭 RC 示例路径：

```text
releases/v2.9.2-rc.1-0813/Next-Trainer-v2.9.2-rc.1-0813-kohya-musubi.7z
```

运行环境：Windows 10 或 11，NVIDIA 显卡（建议 RTX 20 系列及以上）。解压路径请避免中文与空格。

更多说明见 [整合包说明](docs/portable-getting-started.md)、[打标模型](docs/tagger-models.md)、[构建与发包（协作）](docs/portable-build-guide.md)。

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

> `main`、`dev`、`legacy` 的前端架构不同，请不要把未提交的 `frontend/dist` 热修混提。整合包用户以整包版本为准即可。

---

## 功能一览

| 模块 | 能力 |
|------|------|
| **训练** | 选择基础模型、引擎与训练目标；右侧实时 TOML 预览；支持校验、导入导出与开始训练 |
| **数据集** | WD14 模型打标；以图片为主的标签编辑，筛选与批量操作在右侧面板 |
| **任务** | 查看任务列表、状态、日志、预览图与 Loss，适合日常盯盘 |
| **设置** | 主题与界面偏好、训练引擎管理、下载源镜像、关于与更新日志 |

支持 Anima LoRA、Anima Fast、Anima 全量微调，以及 SD 1.5、SDXL、Flux（Kohya 线）。也可选装 **Krea 2**（Musubi）。本地还提供打标、训练监控页 `/train-monitor` 与 TensorBoard。

- Anima Fast 说明：[docs/anima-fast.md](docs/anima-fast.md)
- Krea 2 多卡（Linux）：[docs/krea2-linux-multigpu.md](docs/krea2-linux-multigpu.md)

### 界面预览

截图来自 Vue 3（v3.0.0 线，中文界面）。

<details open>
<summary><strong>训练</strong></summary>

| 标准（Kohya 或 Anima） | Anima Fast | Krea 2（Musubi） |
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
| Anima LoRA | 支持 LoRA、LoKr、T-LoRA，大约 12GB 显存起 |
| Anima Fast | 可选独立运行时，建议 16GB 及以上，在设置页安装 |
| Anima 全量 | 完整 DiT，建议大约 24GB 显存 |
| SD 1.5 / SDXL | LoRA 与全量微调 |
| Flux | LoRA |
| Krea 2 | 经 Musubi 的 LoRA；在设置页安装引擎；Linux 可多卡 |

显存与参数说明见 [docs/anima-training.md](docs/anima-training.md)。

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

请尽量附上：

- 侧栏显示的完整版本号
- 训练类型：基础模型、引擎、训练目标
- 复现步骤
- 相关日志

到 [Issues](https://github.com/wochenlong/lora-scripts-next/issues) 提交。

**lite 和 kohya-musubi 怎么选？**

- 网络较弱，或只想先轻量启动：选 **lite**（首次运行会安装依赖）
- 希望开箱即可使用 Kohya，并训 Krea 2：选 **kohya-musubi**
- 两种包里，Anima Fast 都需要到设置页单独安装

**3.0.0 和旧稳定版能混用配置吗？**

多数 TOML 仍可导入。导航结构和本地存储的 key 有差异，请以当前页面的「导入配置」结果为准。

**更新后界面全变了？**

这是预期行为：现在的 `main` 已经是 Vue 3。  
若仍需要旧界面，请使用上方的 [legacy/v2.9.1](https://github.com/wochenlong/lora-scripts-next/tree/legacy/v2.9.1) 分支，或安装 [v2.9.1 整合包](https://github.com/wochenlong/lora-scripts-next/releases/tag/v2.9.1)。

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
