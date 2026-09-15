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

![Next Trainer 训练工作台：Anima 2.9B 与 Anima Fast 环境已就绪](assets/readme/vue3/02-training-anima-fast-29b-ready.png)

Anima 2.9B 模型与 Anima Fast 训练环境已经就绪，左侧配置训练，右侧查看 TOML。[查看完整界面导览](docs/interface-tour.md)。

## 3.1.0 更新了什么

- **Anima Fast**：支持 Anima 2.9B 与 T-LoRA，使用独立训练环境。
- **多引擎统一管理**：在同一工作台中管理和使用 Kohya、Anima Fast、Musubi 与 AI Toolkit。
- **训练流程更顺畅**：改进任务管理、配置导入和训练步数 / epoch 处理。

[完整更新日志](CHANGELOG.md) · [Anima Fast 使用指南](docs/anima-fast.md)

## 支持的模型

**Anima · SD 1.5 · SDXL · Flux · FLUX.2 Klein · Krea 2**

不同模型支持的训练目标、硬件要求和引擎安装方式有所区别，详见[模型与训练指南](docs/README.md#training--训练)。

## 开始使用

**Windows 用户**：推荐[下载整合包](https://github.com/wochenlong/lora-scripts-next/releases)，解压后使用包内启动脚本。需要 NVIDIA 显卡，详细步骤和包型区别见[快速开始](docs/getting-started.md)。

**版本说明**：3.1.0 源码已进入 `main`；当前已发布的整合包仍为 **v3.0.0**，下载该包不包含 3.1.0 更新。新整合包以 Releases 发布为准。

想使用 3.1.0 源码版本，或在 Linux 上运行？请看[从源码运行](docs/getting-started.md#从源码运行)。

---

[使用文档](docs/README.md) · [问题反馈](https://github.com/wochenlong/lora-scripts-next/issues) · [开源致谢](docs/credits.md) · [贡献者](CONTRIBUTORS.md)
