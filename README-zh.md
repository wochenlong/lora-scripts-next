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

由 [KohakuBlueleaf](https://github.com/KohakuBlueleaf) 使用其训练器 [KohakuMossTrainer](https://github.com/KohakuBlueleaf/KohakuMossTrainer) 完成的 **100 步风格 LoRA 测试**。上排为基础模型，下排为加载 LoRA 后的效果。经作者同意引用，用于展示 MOSS-Image 的训练效果；本图结果由 KohakuMossTrainer 训练获得（现已作为可选训练引擎接入 Next Trainer）。

[![KohakuBlueleaf 的 MOSS-Image 基础模型与 100 步风格 LoRA 效果对比](assets/readme/kohaku-moss-style-lora.png)](assets/readme/kohaku-moss-style-lora.png)

## 3.2.0 更新了什么

- **标签编辑重做**：图片墙优先，选中后才展开编辑面板；提供「标签编辑 / 自由编辑」两种模式、批量操作与历史记录。
- **离线中文释义**：内置 Danbooru 中文词典（约 33 万条），翻译来源精简为 **词库 / 本地模型 / API**，词库来源完全离线。
- **设置区重构**：顺序调整为 **UI 设置 → 训练引擎 → API → 插件市场 → 高级设置 → 关于**；新增 **API** 页统一管理接口与本地模型，网络与下载源归入高级设置。
- **训练任务队列**：训练任务自动排队、服务重启后不丢失，失败 / 已终止任务可按原配置重新排队。
- **MOSS-Image LoRA**：新增 MOSS-Image 训练，推荐并默认使用 Kohya；同时接入 [KohakuMossTrainer](https://github.com/KohakuBlueleaf/KohakuMossTrainer)（实验性高性能 / LyCORIS 引擎）与 `anima_lora` 备选运行时。
- **Musubi 新增 Ideogram 4 LoRA**：FP8 量化权重、非商用许可，整合包不预置（上游仍标记 experimental）。
- **修复**：Anima 页面的 LoKr / LoHa / T-LoRA 参数在刷新或导入配置时被重置为默认值；数据集配置预检拒绝会被静默跳过的子集。

[完整更新日志](CHANGELOG.md)

## 支持的训练引擎

![一个前端，多种训练引擎（概念示意图）](assets/readme/next-trainer-multi-engine.png)

**Kohya · Anima Fast · Musubi · AI Toolkit · DiffSynth-Studio · KohakuMossTrainer · MOSS (anima_lora)**

引擎可在 **设置 → 训练引擎** 中按需安装，再到训练页选择对应引擎。从 3.1.1 或更早版本升级后，首次使用 Kohya 训练前需先安装 Kohya 引擎。可用引擎以所用训练器版本为准；接入引擎不代表已经支持其上游的全部模型和功能。

训练 Qwen-Image-2.1 时，选择 **DiffSynth-Studio → LoRA**，再切换 **文生图 T2I** 或 **Edit 图像编辑**。Edit 当前要求 Batch 1，可通过梯度累积增加有效批量。

训练 MOSS-Image LoRA 时，推荐使用且默认选择 **Kohya**；也可按需安装并切换 **KohakuMossTrainer**（Kohaku / 龙娘开发的高性能 LyCORIS 训练引擎）或 **MOSS (anima_lora)**。

## 支持的模型

![支持的模型概念示意图（非各模型实际输出样张）](assets/readme/next-trainer-models.png)

**MOSS-Image · Qwen-Image-2.1 · Anima · SD 1.5 · SDXL · Flux · FLUX.2 Klein · Krea 2 · Ideogram 4**

不同模型支持的训练目标、硬件要求和引擎安装方式有所区别，详见下方训练教程。

### 模型与训练引擎对应表

✅ 表示已集成的 LoRA 训练入口；— 表示暂无对应入口。此表以当前分支的训练模块为准，不代表上游引擎的全部能力；具体模型版本和硬件要求仍以对应引擎教程为准。

| 模型 | Kohya | Anima Fast | Musubi | AI Toolkit | DiffSynth-Studio | KohakuMossTrainer | MOSS (anima_lora) |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| MOSS-Image | ✅ | — | — | — | — | ✅ | ✅ |
| Qwen-Image-2.1 | — | — | — | ✅ | ✅ | — | — |
| Krea 2 | — | — | ✅ | ✅ | — | — | — |
| Anima | ✅ | ✅ | — | ✅ | — | — | — |
| FLUX.2 Klein | — | — | — | ✅ | — | — | — |
| Ideogram 4 | — | — | ✅ | ✅ | — | — | — |
| Flux | ✅ | — | — | ✅ | — | — | — |
| SDXL | ✅ | — | — | ✅ | — | — | — |
| SD 1.5 | ✅ | — | — | ✅ | — | — | — |

Kohya 还提供 Anima、SDXL、SD 1.5 的全量训练入口。MOSS-Image 默认使用 Kohya，并提供 `KohakuMossTrainer` 与 `MOSS (anima_lora)` 可选引擎。Lumina 保留 Kohya LoRA 入口，可通过 `?model=lumina` 访问，但不在常规模型选择列表中展示。

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

## 开始使用

**Windows 用户**：推荐[下载整合包](https://github.com/wochenlong/lora-scripts-next/releases)，解压后使用包内启动脚本。需要 NVIDIA 显卡，详细步骤和包型区别见[快速开始](docs/getting-started.md)。

**版本说明**：3.2.0 源码已进入 `main`。整合包有单独的发布进度，请以 Releases 中的版本号和更新说明为准；旧整合包不一定包含 DiffSynth 与 Qwen-Image-2.1 支持。

想使用 3.2.0 源码版本，或在 Linux 上运行？请看[从源码运行](docs/getting-started.md#从源码运行)。


---

[使用文档](docs/README.md) · [问题反馈](https://github.com/wochenlong/lora-scripts-next/issues) · [开源致谢](docs/credits.md) · [贡献者](CONTRIBUTORS.md)
