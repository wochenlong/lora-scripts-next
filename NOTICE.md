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

Experimental Anima conditioning / image-editing backend planning references:

- `Mirumo0u0/sd-scripts`: https://github.com/Mirumo0u0/sd-scripts

`Mirumo0u0/sd-scripts` is a fork of `kohya-ss/sd-scripts` and is licensed under the **Apache License 2.0**. Any local integration of its conditioning changes should preserve the upstream license text, source attribution, and prominent notices for modified files.

Example images used in the Anima image-editing documentation were provided by **古柯C17H21NO4**. We thank him for contributing the images used to illustrate the experimental workflow.

Earlier Anima integration work also referenced:

- `WhitecrowAurora/lora-rescripts` (**SD-reScripts** — historical fork / continuation of the LoRA-scripts line): https://github.com/WhitecrowAurora/lora-rescripts

The historical reference repository is licensed under AGPL-3.0. Current Anima training should be synchronized from `kohya-ss/sd-scripts`; local code is limited to the WebUI compatibility wrapper, config adapter, defaults, and launch orchestration.

### Anima LoRA Compile Optimizations (Turbo Mode)

The optional "Turbo" training mode integrates torch.compile acceleration, constant-token bucketing, and compile-friendly code patterns adapted from:

- `sorryhyun/anima_lora`: https://github.com/sorryhyun/anima_lora

Licensed under the **MIT License** (Copyright (c) 2026 Seunghyun Ji).

The referenced repository is an optimized Anima LoRA training engine featuring per-block torch.compile with CUDAGraph capture, static-shape token bucketing for zero recompilation, and compile-friendly forward paths (einops removal, autocast elimination, hoisted dict loops). These techniques achieve ~5x training speedup on consumer GPUs at the cost of higher VRAM usage.

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
