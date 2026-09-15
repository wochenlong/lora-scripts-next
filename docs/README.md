# Next Trainer Documentation / 使用文档

[Home](../README.md) · [中文首页](../README-zh.md)

## Start Here / 从这里开始

- [快速开始](getting-started.md) / [Quick start](getting-started.en.md): downloads, package selection, source setup, and branches.
- [Interface tour / 界面导览](interface-tour.md): training, datasets, tasks, and settings.
- [Changelog / 更新日志](../CHANGELOG.md): release details, fixes, and new capabilities.

## Training / 训练

- [Anima training / Anima 训练](anima-training.md): training targets and VRAM guidance.
- [Anima Fast](anima-fast.md): optional runtime, configuration, and training.
- [Krea 2 multi-GPU / Krea 2 多卡](krea2-linux-multigpu.md): Linux deployment and multi-GPU usage.
- [TOML and CLI / TOML 与命令行](cli-args.md): command-line training entry points.
- [Tagger models / 打标模型](tagger-models.md): model files and installation paths.
- [Training monitor / 训练监控](train-monitor.md).

Available training targets depend on the model and engine. Use the training page's model, engine, and target selectors to check available combinations.

训练目标取决于模型和引擎，请以训练页的模型、引擎和训练目标选项为准。

## Development / 开发与发行

- [Repository layout / 仓库布局](repo-layout.md).
- [Frontend development / 前端开发](../frontend/README.md).
- [Build and release / 整合包构建与发包](portable-build-guide.md).
- [Portable notes / 整合包补充说明](portable-getting-started.md): includes historical release instructions; check the version before following them.
- [Task workbench design / 任务工作台设计](issues/286-task-workbench.md).
- [Team / 协作说明](team/README.md).

## Help and Credits / 反馈与致谢

When [reporting an issue](https://github.com/wochenlong/lora-scripts-next/issues), include the sidebar version, model/engine/target, reproduction steps, and relevant logs. Remove tokens and other private information before posting.

[反馈问题](https://github.com/wochenlong/lora-scripts-next/issues)时请提供侧栏版本号、模型 / 引擎 / 训练目标、复现步骤和相关日志。发布前请移除凭证和其他隐私信息。

[Credits / 开源引用](credits.md) · [Legal notice](../NOTICE.md) · [Contributors / 贡献者](../CONTRIBUTORS.md)
