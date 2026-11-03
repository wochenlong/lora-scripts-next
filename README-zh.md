<p align="center">
  <img src="assets/readme/next-trainer-cover.png" alt="Next Trainer — 支持 MOSS 训练" width="720" />
</p>

<p align="center">
  <strong>多模型、多引擎的本地训练工作台</strong><br />
  从数据集整理到模型训练，在一个界面里完成。
</p>

<p align="center">
  <a href="https://github.com/wochenlong/lora-scripts-next/releases">下载</a> ·
  <a href="docs/getting-started.md">快速开始</a> ·
  <a href="docs/README.md">使用文档</a> ·
  <a href="README.md">English</a>
</p>


## MOSS-Image 训练效果展示

由 [KohakuBlueleaf](https://github.com/KohakuBlueleaf) 使用其训练器 [KohakuMossTrainer](https://github.com/KohakuBlueleaf/KohakuMossTrainer) 完成的 **100 步风格 LoRA 测试**。上排为基础模型，下排为加载 LoRA 后的效果。经作者同意引用，用于展示 MOSS-Image 的训练效果；本图结果由 KohakuMossTrainer 训练获得。

[![KohakuBlueleaf 的 MOSS-Image 基础模型与 100 步风格 LoRA 效果对比](assets/readme/kohaku-moss-style-lora.png)](assets/readme/kohaku-moss-style-lora.png)

## 3.3.0 更新了什么

- **多引擎工作台**：统一支持 Kohya、Anima Fast、Musubi、AI Toolkit、DiffSynth-Studio 和 MOSS（anima_lora），并补充模型与引擎对应表及训练教程入口。
- **Kohya 运行环境独立化**：Kohya 使用 `extensions/kohya/` 独立环境；训练器源码更新与引擎环境分离，Kohya 可按需安装、修复和审计。
- **更新不再丢失 Kohya**：源码更新和整合包更新都会保留用户拥有的训练运行时；整合包更新器排除 `Next-Trainer/extensions/`，不会因更新主程序卸载 Kohya。
- **MOSS-Image**：新增 MOSS-Image LoRA 训练，默认推荐 Kohya，`anima_lora` 作为次选路径。
- **AI Toolkit 与 Ideogram 4**：加入 AI Toolkit 训练引擎和 Ideogram 4 LoRA 入口，按需安装，不强制下载可选引擎环境。
- **插件市场调整**：当前没有可用插件内容，已从用户界面和默认构建中隐藏，也不会强制下载空的 marketplace 依赖。
- **3.3.1-dev 整合包**：提供小于 2 GB 的 lite 包，包含基础运行环境、前端、WD 打标模型和离线 tokenizer，不预装 Kohya。

[完整更新日志](CHANGELOG.md)

## 开始使用

**Windows 用户**：推荐直接下载当前整合包 [Next-Trainer-v3.3.1-dev-lite.7z](https://github.com/wochenlong/lora-scripts-next/releases/download/v3.3.1-dev/Next-Trainer-v3.3.1-dev-lite.7z)，解压后使用包内启动脚本。该包包含基础运行环境、前端、WD 打标模型和离线 tokenizer，不预装 Kohya，也不会下载空的插件市场依赖；首次训练时可在 **设置 → 训练引擎** 按需安装引擎。需要 NVIDIA 显卡，详细步骤和包型区别见[快速开始](docs/getting-started.md)。

**版本说明**：当前推荐整合包版本为 `3.3.1-dev`。预装 Kohya 的大体积包单独发布，不放在 GitHub Release；插件市场当前没有可用内容，已从用户界面和默认构建中隐藏。

想使用最新源码或在 Linux 上运行？请看[从源码运行](docs/getting-started.md#从源码运行)。

### 如何更新

**源码安装：**

1. 关闭 WebUI 和正在运行的训练任务。
2. 在项目目录执行 `git status`，确认自己的修改已提交或已备份。
3. 稳定版切换到 `main` 后执行 `git pull --ff-only`；只想跟进下一版本时使用 `git fetch origin` 后再切换到 `dev`。
4. 重新运行 `run_gui.bat`（Windows）或 `bash run_gui.sh`（Linux）。如果依赖发生变化，按启动器提示重新运行 `install-cn.ps1` / `setup_environment.py`，不要删除整个项目目录里的用户数据。

源码更新只更新仓库代码；已安装的 Kohya 环境位于 `extensions/kohya/`，不要手动删除该目录。升级后如果页面提示 Kohya 环境损坏，再进入 **设置 → 训练引擎 → Kohya → 修复/安装**，由程序按当前版本重新检查或修复。

**整合包安装：**

- 优先双击包根目录的 `Update-Next-Trainer-Release.bat`，它会下载最新 Release 并合并程序文件；无法访问 Release 时可使用 `Update-Next-Trainer.bat` 走 Git 更新。
- 更新前必须关闭 WebUI。更新器会保留 `Next-Trainer\extensions\`、模型、输出、日志、训练集和配置；其中 `Next-Trainer\extensions\kohya\` 就是 Kohya 独立环境，不会被更新包覆盖。
- 更新完成后重新双击 `run_gui.bat`。如果启动器提示依赖变化，再运行包内 `update\update_dependencies.bat`；不要先删除 `python_embeded` 或 `extensions\kohya`。

**没有更新脚本的旧整合包：**不要把新版 7z 直接解压到旧目录并选择覆盖。先关闭程序，将旧包中的 `Next-Trainer\extensions\kohya\` 整个目录复制到安全位置，再下载新版并解压到新目录，最后把该目录复制回新版的 `Next-Trainer\extensions\kohya\`；同时迁移 `sd-models`、`output`、`logs`、`train`、`config`、`huggingface` 和 `tagger-models`。复制完成后从新版根目录启动。这个步骤把“程序代码更新”和“Kohya 环境”分开，避免旧版覆盖方式再次丢失引擎。

lite 包本身不预装 Kohya；首次使用时请在 **设置 → 训练引擎** 安装。安装完成后，后续更新只要使用上面的更新器并保留 `Next-Trainer\extensions\kohya\`，就不会因为更新主程序而卸载 Kohya。详细的整合包更新契约见[整合包更新说明](docs/portable-packaging-git-update.md)。

## 支持的训练引擎

![一个前端，多种训练引擎（概念示意图）](assets/readme/next-trainer-multi-engine.png)

**Kohya · Anima Fast · Musubi · AI Toolkit · DiffSynth-Studio · MOSS (anima_lora)**

引擎可在 **设置 → 训练引擎** 中按需安装，再到训练页选择对应引擎。从 3.1.1 或更早版本升级后，首次使用 Kohya 训练前需先安装 Kohya 引擎。可用引擎以所用训练器版本为准；接入引擎不代表已经支持其上游的全部模型和功能。

训练 Qwen-Image-2.1 时，选择 **DiffSynth-Studio → LoRA**，再切换 **文生图 T2I** 或 **Edit 图像编辑**。Edit 当前要求 Batch 1，可通过梯度累积增加有效批量。

训练 MOSS-Image LoRA 时，推荐使用且默认选择 **Kohya**；**MOSS (anima_lora)** 作为次选引擎保留。

## 支持的模型

![支持的模型概念示意图（非各模型实际输出样张）](assets/readme/next-trainer-models.png)

**MOSS-Image · Qwen-Image-2.1 · Anima · SD 1.5 · SDXL · Flux · FLUX.2 Klein · Krea 2 · Ideogram 4**

不同模型支持的训练目标、硬件要求和引擎安装方式有所区别，详见下方训练教程。

### 模型与训练引擎对应表

✅ 表示已集成的 LoRA 训练入口；— 表示暂无对应入口。此表以当前分支的训练模块为准，不代表上游引擎的全部能力；具体模型版本和硬件要求仍以对应引擎教程为准。

| 模型 | Kohya | Anima Fast | Musubi | AI Toolkit | DiffSynth-Studio | MOSS (anima_lora) |
| --- | :---: | :---: | :---: | :---: | :---: | :---: |
| MOSS-Image | ✅ | — | — | — | — | ✅ |
| Qwen-Image-2.1 | — | — | — | ✅ | ✅ | — |
| Krea 2 | — | — | ✅ | ✅ | — | — |
| Anima | ✅ | ✅ | — | ✅ | — | — |
| FLUX.2 Klein | — | — | — | ✅ | — | — |
| Ideogram 4 | — | — | ✅ | ✅ | — | — |
| Flux | ✅ | — | — | ✅ | — | — |
| SDXL | ✅ | — | — | ✅ | — | — |
| SD 1.5 | ✅ | — | — | ✅ | — | — |

Kohya 还提供 Anima、SDXL、SD 1.5 的全量训练入口。MOSS-Image 默认使用 Kohya，`MOSS (anima_lora)` 为备选。Lumina 保留 Kohya LoRA 入口，可通过 `?model=lumina` 访问，但不在常规模型选择列表中展示。

上方配图均为概念示意，其中画面不代表各标注模型的实际生成效果或评测结果。

## 训练教程

- [MOSS-Image](docs/MOSS.md)
- [Qwen-Image-2.1](docs/diffsynth.md)
- [Anima](docs/anima-training.md)
- [Anima Fast](docs/anima-fast.md)
- [Krea 2 （Linux / 多卡）](docs/krea2-linux-multigpu.md)
- [Ideogram 4 (Musubi)](docs/ideogram4-musubi.md)
- [TOML / CLI](docs/cli-args.md)

[界面导览](docs/interface-tour.md) · [打标模型准备](docs/tagger-models.md) · [训练监控](docs/train-monitor.md) · [全部文档](docs/README.md)


---

[使用文档](docs/README.md) · [问题反馈](https://github.com/wochenlong/lora-scripts-next/issues) · [开源致谢](docs/credits.md) · [贡献者](CONTRIBUTORS.md)
