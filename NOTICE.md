## Open Source Notices

### Acknowledgement to Akegarasu（必读）

**Next Trainer**（仓库 [wochenlong/lora-scripts-next](https://github.com/wochenlong/lora-scripts-next)）向 **Akegarasu** 及其开源项目 **[Akegarasu/lora-scripts](https://github.com/Akegarasu/lora-scripts)**（社区常称 **SD-Trainer** / **秋叶一键训练包**）致以明确、持续的感谢。

本项目在历史演进上，受益于 Akegarasu 项目在以下方面打下的基础与社区实践：

1. 本地 LoRA / 微调训练 WebUI 的整体使用路径  
2. 面向普通用户的整合包与启动约定  
3. 与 [kohya-ss/sd-scripts](https://github.com/kohya-ss/sd-scripts) 等训练后端的对接方式  
4. 长期公开维护所形成的用户习惯与文档氛围  

**关系说明：**

1. 本仓库由 [wochenlong/lora-scripts-next](https://github.com/wochenlong/lora-scripts-next) 维护，产品品牌为 **Next Trainer**。  
2. 上游 Akegarasu 项目仍按其自身节奏独立发展：https://github.com/Akegarasu/lora-scripts  
3. 本仓库在 AGPL-3.0 等适用许可下维护；这 **不减轻** 对上游与其它第三方的致谢与许可义务。  
4. 再分发源码或整合包时，须一并保留本 NOTICE、本仓库 LICENSE，以及各上游要求的声明。

若致谢表述有疏漏，欢迎通过本仓库 Issues 指出，我们会优先修正。

### Upstream GUI / community packaging

This repository is maintained as **[wochenlong/lora-scripts-next](https://github.com/wochenlong/lora-scripts-next)** and **publicly acknowledges** that its UX lineage and packaging culture trace to **Akegarasu SD-Trainer** / **秋叶一键训练包**: **[Akegarasu/lora-scripts](https://github.com/Akegarasu/lora-scripts)**.

Training backend integration continues to rely primarily on **[kohya-ss/sd-scripts](https://github.com/kohya-ss/sd-scripts)** and other engines documented below. Product branding for this repository is **Next Trainer**.

### Rectified Flow (SDXL LoRA)

This project includes Rectified Flow training support for SDXL LoRA inspired by and adapted from:

- `bluvoll/Akegarasu-lora-scripts-RF`: https://github.com/bluvoll/Akegarasu-lora-scripts-RF

The referenced repository is licensed under AGPL-3.0. Its RF training ideas include the Rectified Flow objective, sigma timestep sampling, optional cosine optimal transport pairing, and SDXL resolution-dependent timestep shift controls.

### Anima LoRA

Active Anima backend maintenance is based on:

- `kohya-ss/sd-scripts`: https://github.com/kohya-ss/sd-scripts

Earlier Anima integration work also referenced:

- `WhitecrowAurora/lora-rescripts` (**SD-reScripts** — historical fork / continuation of the LoRA-scripts line): https://github.com/WhitecrowAurora/lora-rescripts

The historical reference repository is licensed under AGPL-3.0. Current Anima training should be synchronized from `kohya-ss/sd-scripts`; local code is limited to the WebUI compatibility wrapper, config adapter, defaults, and launch orchestration.

### Anima LoRA Fast Mode（进阶插件）

The optional **Fast mode** (`model_train_type: anima-lora-fast`) integrates the optimized Anima LoRA training engine adapted from:

- `sorryhyun/anima_lora`: https://github.com/sorryhyun/anima_lora

Licensed under the **MIT License** (Copyright (c) 2026 Seunghyun Ji).

Next Trainer ships this engine as an **optional plugin** (`extensions/anima_lora/`). On install, the plugin snapshot includes upstream `LICENSE` / `NOTICE` / `README.md` (see `mikazuki/anima_fast_backend/installer.py`). User-facing docs: [`docs/anima-fast.md`](docs/anima-fast.md).

The referenced repository features per-block or full-model `torch.compile`, static-shape token bucketing, and compile-friendly forward paths. On consumer GPUs this yields substantially faster step times than the default Kohya/sd-scripts path at the cost of higher VRAM and a separate Python/CUDA runtime. See **Performance** in `docs/anima-fast.md` for measured comparisons in this repo.

### LyCORIS

LoKr, LoHa, and other advanced LoRA variants are powered by:

- `KohakuBlueleaf/LyCORIS`: https://github.com/KohakuBlueleaf/LyCORIS

LyCORIS (Lora beYond Conventional methods, Other Rank adaptation Implementations for Stable diffusion) is licensed under the **Apache License 2.0**. It provides the network modules for LoKr (Low-Rank Kronecker Product), LoHa (Low-Rank Hadamard Product), and other parameter-efficient fine-tuning methods used in this project.

**Paper**: Yeh et al. *Navigating Text-To-Image Customization: From LyCORIS Fine-Tuning to Model Evaluation*. ICLR 2024.

### T-LoRA (Timestep-Dependent LoRA)

T-LoRA support is adapted from:

- `ControlGenAI/T-LoRA`: https://github.com/ControlGenAI/T-LoRA

The referenced repository is licensed under the **MIT License** (Copyright (c) 2025 AIRI, https://airi.net).

T-LoRA introduces dynamic rank adjustment based on diffusion timesteps and orthogonal initialization. Local files `networks/tlora.py` and `networks/tlora_anima.py` are adapted from the original implementation with modifications for Anima model integration within the sd-scripts training pipeline.

**Paper**: Nikita Balagansky, Daniil Gavrilov. *T-LoRA: Timestep-Dependent Low-Rank Adaptation for Diffusion Models*. 2025.

### EmoSens Optimizer

The EmoSens optimizer is adapted from:

- `muooon/EmoSens`: https://github.com/muooon/EmoSens

Licensed under the **Apache License 2.0** (Copyright (c) muooon).

EmoSens is an emotion-driven optimizer that generates autonomous learning rates via the emoPulse mechanism, analyzing loss fluctuations through multi-scale EMA. The implementation is in `vendor/sd-scripts/library/optimizers/emosens.py`.

**Citation**: muooon. "emo series Optimizers: An emotion-driven optimizer that feels loss and navigates accordingly." DOI: 10.57967/hf/7738. https://github.com/muooon/EmoSens

### WD14 Tagger (default portable model)

Default offline image tagging uses weights and tag lists derived from:

- `SmilingWolf/wd-v1-4-convnextv2-tagger-v2`: https://huggingface.co/SmilingWolf/wd-v1-4-convnextv2-tagger-v2

Bundled under `tagger-models/wd14/wd14-convnextv2-v2/` in portable packages. Redistribute the model files only under the terms published by the model author / host.

### Schemastery

Dynamic training forms are driven by:

- `shigma/schemastery`: https://github.com/shigma/schemastery

Please see the upstream repository for its license terms.
