## Open Source Notices

### Upstream GUI / community packaging

This repository is maintained as **[wochenlong/lora-scripts-next](https://github.com/wochenlong/lora-scripts-next)** and traces its UX and packaging to **Akegarasu SD-Trainer** / **秋叶一键训练包**: **[Akegarasu/lora-scripts](https://github.com/Akegarasu/lora-scripts)** (training backend integration: **[kohya-ss/sd-scripts](https://github.com/kohya-ss/sd-scripts)**).

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

SD Trainer ships this engine as an **optional plugin** (`extensions/anima_lora/`). On install, the plugin snapshot includes upstream `LICENSE` / `NOTICE` / `README.md` (see `mikazuki/anima_fast_backend/installer.py`). User-facing docs: [`docs/anima-fast.md`](docs/anima-fast.md).

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
