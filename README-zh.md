<p align="center">
  <img src="assets/readme/next-trainer-cover.png" alt="Next Trainer" width="720" />
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

![Next Trainer 训练工作台：使用 DiffSynth 引擎训练 Qwen-Image-2.1 LoRA](assets/readme/vue3/02-training-qwen-image-21-diffsynth.png)

使用 DiffSynth 引擎训练 Qwen-Image-2.1 LoRA，左侧配置训练，右侧查看 TOML。[从零开始训练 Qwen-Image-2.1](docs/diffsynth.md) · [查看完整界面导览](docs/interface-tour.md)。

## 3.2.0 更新了什么

- **标签编辑重做**：图片墙优先，选中后才展开编辑面板；提供「标签编辑 / 自由编辑」两种模式、批量操作与历史记录。
- **离线中文释义**：内置 Danbooru 中文词典（约 33 万条），翻译来源精简为 **词库 / 本地模型 / API**，词库来源完全离线。
- **设置区重构**：顺序调整为 **UI 设置 → 训练引擎 → API → 插件市场 → 高级设置 → 关于**；新增 **API** 页统一管理接口与本地模型，网络与下载源归入高级设置。
- **训练任务队列**：训练任务自动排队、服务重启后不丢失，失败 / 已终止任务可按原配置重新排队。
- **MOSS-Image LoRA**：新增 MOSS-Image 训练，推荐并默认使用 Kohya；`anima_lora` 运行时保留为次选路径。详见 [MOSS-Image 训练指南](docs/MOSS.md)。
- **Musubi 新增 Ideogram 4 LoRA**：FP8 量化权重、非商用许可，整合包不预置（上游仍标记 experimental）。
- **修复**：Anima 页面的 LoKr / LoHa / T-LoRA 参数在刷新或导入配置时被重置为默认值；数据集配置预检拒绝会被静默跳过的子集。

[完整更新日志](CHANGELOG.md) · [Qwen-Image-2.1 入门教程](docs/diffsynth.md) · [Anima Fast 使用指南](docs/anima-fast.md)

## 支持的训练引擎

**Kohya · Anima Fast · Musubi · AI Toolkit · DiffSynth-Studio · MOSS (anima_lora)**

引擎可在 **设置 → 训练引擎** 中按需安装，再到训练页选择对应引擎。从 3.1.1 或更早版本升级后，首次使用 Kohya 训练前需先安装 Kohya 引擎。可用引擎以所用训练器版本为准；接入引擎不代表已经支持其上游的全部模型和功能。

训练 Qwen-Image-2.1 时，选择 **DiffSynth-Studio → LoRA**，再切换 **文生图 T2I** 或 **Edit 图像编辑**。Edit 当前要求 Batch 1，可通过梯度累积增加有效批量。

训练 MOSS-Image LoRA 时，推荐使用且默认选择 **Kohya**；**MOSS (anima_lora)** 作为次选引擎保留。安装、模型目录与参数说明见 [MOSS-Image 训练指南](docs/MOSS.md)。

## 支持的模型

**MOSS-Image · Qwen-Image-2.1 · Anima · SD 1.5 · SDXL · Flux · FLUX.2 Klein · Krea 2 · Ideogram 4**

不同模型支持的训练目标、硬件要求和引擎安装方式有所区别，详见[模型与训练指南](docs/README.md#training--训练)。

## 开始使用

**Windows 用户**：推荐[下载整合包](https://github.com/wochenlong/lora-scripts-next/releases)，解压后使用包内启动脚本。需要 NVIDIA 显卡，详细步骤和包型区别见[快速开始](docs/getting-started.md)。

**版本说明**：3.2.0 源码已进入 `main`。整合包有单独的发布进度，请以 Releases 中的版本号和更新说明为准；旧整合包不一定包含 DiffSynth 与 Qwen-Image-2.1 支持。

想使用 3.2.0 源码版本，或在 Linux 上运行？请看[从源码运行](docs/getting-started.md#从源码运行)。

命令行训练可用 `scripts/cli/train_anima_by_toml.sh`、`scripts/cli/train_anima_fast_by_toml.sh` 提交 Anima / Anima Fast 配置，参数见 [CLI 说明](docs/cli-args.md)。

---

[使用文档](docs/README.md) · [问题反馈](https://github.com/wochenlong/lora-scripts-next/issues) · [开源致谢](docs/credits.md) · [贡献者](CONTRIBUTORS.md)
