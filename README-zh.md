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

## 3.1.3 更新了什么

- **整合包引擎环境自愈**：Musubi / AI Toolkit 整合包若仍指向构建机 Python，解压或挪目录后会自动修复 venv（#406 / #411）。
- **Anima 2B / 2.9B 规格选择**：训练页可选模型规格，并按规格记住底模路径（#394）。
- **Kohya 独立引擎**：可在 **设置 → 训练引擎** 中安装、修复、卸载 Kohya，不再占用 GUI Python 环境。
- **默认训练引擎**：可设置启动时默认引擎，也可选择记住上次使用的引擎。

[完整更新日志](CHANGELOG.md) · [Qwen-Image-2.1 入门教程](docs/diffsynth.md) · [Anima Fast 使用指南](docs/anima-fast.md)

## 支持的训练引擎

**Kohya · Anima Fast · Musubi · AI Toolkit · DiffSynth-Studio**

引擎可在 **设置 → 训练引擎** 中按需安装，再到训练页选择对应引擎。从 3.1.1 或更早版本升级后，首次使用 Kohya 训练前需先安装 Kohya 引擎。可用引擎以所用训练器版本为准；接入引擎不代表已经支持其上游的全部模型和功能。

训练 Qwen-Image-2.1 时，选择 **DiffSynth-Studio → LoRA**，再切换 **文生图 T2I** 或 **Edit 图像编辑**。Edit 当前要求 Batch 1，可通过梯度累积增加有效批量。

## 支持的模型

**Qwen-Image-2.1 · Anima · SD 1.5 · SDXL · Flux · FLUX.2 Klein · Krea 2**

不同模型支持的训练目标、硬件要求和引擎安装方式有所区别，详见[模型与训练指南](docs/README.md#training--训练)。

## 开始使用

**Windows 用户**：推荐[下载整合包](https://github.com/wochenlong/lora-scripts-next/releases)，解压后使用包内启动脚本。需要 NVIDIA 显卡，详细步骤和包型区别见[快速开始](docs/getting-started.md)。

**版本说明**：3.1.3 源码已进入 `main`。整合包有单独的发布进度，请以 Releases 中的版本号和更新说明为准；旧整合包不一定包含 DiffSynth 与 Qwen-Image-2.1 支持。

想使用 3.1.3 源码版本，或在 Linux 上运行？请看[从源码运行](docs/getting-started.md#从源码运行)。

---

[使用文档](docs/README.md) · [问题反馈](https://github.com/wochenlong/lora-scripts-next/issues) · [开源致谢](docs/credits.md) · [贡献者](CONTRIBUTORS.md)
