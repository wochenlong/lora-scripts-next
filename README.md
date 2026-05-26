<p align="center">
  <img src="assets/readme/next-trainer-cover.png" alt="Next Trainer" width="880" />
</p>

<h1 align="center">Next Trainer: Anima Edit Branch</h1>

<p align="center">
  <b>Experimental Anima image-editing / conditioning training branch</b><br/>
  Train paired Target / Reference datasets from the WebUI and preview edits with Control Images.<br/>
  <sub>Based on Next Trainer, kohya-ss/sd-scripts, and conditioning work from <a href="https://github.com/Mirumo0u0/sd-scripts">Mirumo0u0/sd-scripts</a>.</sub>
</p>

<p align="center">
  <a href="https://github.com/wochenlong/lora-scripts-next/tree/anima-edit"><img src="https://img.shields.io/badge/branch-anima--edit-a78bfa?style=for-the-badge" alt="anima-edit branch"/></a>
</p>

<p align="center">
  <a href="https://github.com/wochenlong/lora-scripts-next"><img src="https://img.shields.io/github/stars/wochenlong/lora-scripts-next?style=flat-square&label=stars&logo=github&color=8b5cf6" alt="stars"/></a>
  <a href="https://github.com/wochenlong/lora-scripts-next/blob/main/LICENSE"><img src="https://img.shields.io/github/license/wochenlong/lora-scripts-next?style=flat-square&color=ec4899" alt="license"/></a>
</p>
<p align="center">
  <a href="https://github.com/wochenlong/lora-scripts-next/blob/anima-edit/README-zh.md"><b>中文</b></a>
</p>
<p align="center">
  <a href="https://github.com/wochenlong/lora-scripts-next/blob/anima-edit/NOTICE.md"><b>Credits</b></a>
</p>

---

<p align="center">
  <img src="assets/readme/screenshot-webui.png" alt="Next Trainer GUI" width="920" />
</p>

<p align="center"><sub>New UI — sidebar navigation, model & parameter form in the center, real-time config preview on the right</sub></p>

---

## Anima Image Editing (Experimental)

The `anima-edit` branch adds Anima conditioning / image-editing training. Enable **Image Editing (Experimental)** on the Anima page to configure paired datasets:

- **Target directory**: final images and their `.txt` / `.json` captions.
- **Reference / Conditioning directory**: input reference images with the same filenames and dimensions.
- **Image editing preview**: uses a dedicated edit prompt plus a fixed or randomly sampled Control Image, while reusing the normal preview width, CFG, steps, sampler, and schedule.

Quick links:

- Branch: switch to `anima-edit`; `main` and the current portable Release package do not include this backend yet.
- Training guide: [Anima image editing / conditioning training](docs/anima-training.md#图像编辑--条件训练实验).
- Inference: LoRA models trained here can be used in ComfyUI with [Mirumo0u0/ComfyUI-Cosmos-Reference](https://github.com/Mirumo0u0/ComfyUI-Cosmos-Reference), which adds reference-image input for Anima / Cosmos-family models.
- Key constraints: paired Target / Reference images must have identical filenames and dimensions; image-editing mode automatically enables latent / text encoder caching and disables step 0 preview.

<p align="center">
  <img src="assets/readme/anima-edit-ui.jpg" alt="Anima image editing controls" width="920" />
</p>

<p align="center"><sub>Anima image-editing controls: Target / Reference dataset paths and Control Image preview inputs.</sub></p>

<p align="center">
  <img src="assets/readme/anima-edit-sample.jpg" alt="Anima image editing sample" width="760" />
</p>

<p align="center"><sub>Example reference-driven preview workflow for Anima image editing.</sub></p>

<p align="center">
  <img src="assets/readme/anima-edit-sample-1.jpg" alt="Anima image editing sample variant" width="760" />
</p>

<p align="center"><sub>Sample images courtesy of <b>古柯C17H21NO4</b>. Thank you for providing the reference images used here.</sub></p>

### Experimental quality note

Anima Edit in this branch is **conditioning LoRA training on top of an Anima text-to-image base model**, not a dedicated image-editing foundation model. Compared with specialized editors such as Qwen Image Edit, it can be less precise around local boundaries and may learn fixed artifacts from small paired datasets, especially at later epochs.

If previews start showing repeated dark stains, color blocks, or structure drift, treat that as an overfitting signal rather than a WebUI display issue. Prefer an earlier checkpoint, lower `unet_lr`, fewer epochs, or a cleaner / more diverse paired dataset.

<p align="center">
  <img src="assets/readme/anima-edit-limitations.png" alt="Anima Edit overfitting artifact example" width="920" />
</p>

<p align="center"><sub>Example of a small edit dataset overfitting over epochs: local color artifacts become more stable after the useful learning phase.</sub></p>

> WebUI training now writes the conditioning dataset TOML and `--cn <control image>` sample prompt automatically. See [docs/anima-training.md](docs/anima-training.md) for details.
> The backend conditioning work references [Mirumo0u0/sd-scripts](https://github.com/Mirumo0u0/sd-scripts), an Apache-2.0 fork of kohya-ss/sd-scripts; this project preserves its license notices and source attribution.

---

## Run This Branch

```
1. Clone     →  git clone https://github.com/wochenlong/lora-scripts-next.git
2. Switch    →  cd lora-scripts-next && git checkout anima-edit
3. Launch    →  run_gui.bat on Windows, or bash install.bash && bash run_gui.sh on Linux
4. Train     →  Open http://127.0.0.1:28000, enter Anima LoRA, enable Image Editing
```

> The current portable Release package does **not** include Anima Edit yet. Use the `anima-edit` source branch for now; the one-click bundle is only for released mainline features.

> **Requirements:** Windows 10/11, NVIDIA GPU (RTX 20+), ~7 GB disk.

<details>
<summary><b>Full source commands</b></summary>

```sh
git clone https://github.com/wochenlong/lora-scripts-next.git
cd lora-scripts-next
git checkout anima-edit

# Windows
run_gui.bat

# Linux
bash install.bash && bash run_gui.sh

# Optional: install Flash Attention 2 for faster Anima training
# Windows
install_flash_attn.bat
# Linux
bash install_flash_attn.sh
```

Python **3.10** recommended. See [Flash Attention 2 docs](docs/flash-attention.md) for details.

</details>

---

## Branch Scope

| Area | Status |
|------|--------|
| **Anima image editing** | Primary focus of this branch: paired Target / Reference training and Control Image previews |
| **Anima LoRA / LoKr / T-LoRA** | Inherited from Next Trainer and available on the same page |
| SD 1.5 / SDXL / Flux | Inherited mainline training pages; not the focus of this experimental branch |
| Portable Release package | Not ready for Anima Edit yet; use source checkout |

---

## Training Monitor for Edit Runs

When an Anima Edit run starts, the monitor page helps judge whether the conditioning path is learning: GPU stats, training parameters, Loss curves, preview samples, and logs in one dashboard.

<p align="center">
  <img src="assets/readme/screenshot-train-monitor.png" alt="Train Monitor Dashboard" width="920" />
</p>

<p align="center"><sub>GPU load & VRAM, total steps, training params at a glance</sub></p>

<p align="center">
  <img src="assets/readme/train-monitor-samples.png" alt="Preview Samples & Loss Curves" width="920" />
</p>

<p align="center"><sub>Preview samples and TensorBoard-backed Loss / LR curves</sub></p>

<p align="center">
  <img src="assets/readme/train-monitor-logs.png" alt="Training Logs" width="920" />
</p>

<p align="center"><sub>Real-time training logs with auto-scroll</sub></p>

---

<details>
<summary><b>VRAM Reference (Anima LoRA, 1024 resolution, RTX 4090 benchmarked)</b></summary>

| VRAM | Configuration | Notes |
|------|---------------|-------|
| ≥ 24 GB | Default settings | Easiest |
| ≥ 16 GB | `gradient_checkpointing` | Recommended |
| ≥ 12 GB | Gradient checkpointing | Stable |
| ≥ 10 GB | Gradient checkpointing + `blocks_to_swap=16` | Slightly slower |
| ≥ 8 GB | Gradient checkpointing + swap 24 + cache TE + LoKr | Tight |

</details>

<details>
<summary><b>Documentation</b></summary>

| Topic | Link |
|-------|------|
| **Anima Image Editing / Conditioning Guide** | [docs/anima-training.md#图像编辑--条件训练实验](docs/anima-training.md#图像编辑--条件训练实验) |
| Anima LoRA Training Guide | [docs/anima-training.md](docs/anima-training.md) |
| Flash Attention 2 | [docs/flash-attention.md](docs/flash-attention.md) |
| Train Monitor & SSE API | [docs/train-monitor.md](docs/train-monitor.md) |
| Docker Deployment | [docs/docker.md](docs/docker.md) |
| CLI Arguments | [docs/cli-args.md](docs/cli-args.md) |

</details>

<details>
<summary><b>Mainline Changelog</b></summary>

| Date | Version |
|------|---------|
| 2026-05-21 | **v2.5.0** — UI refresh: new sidebar navigation, home portal page, training monitor dashboard with GPU metrics; CSS cleanup |
| 2026-05-21 | **v2.4.0** — Training stability: env isolation, NaN filter, sample guard, attn_mode fallback, path normalization; Portable tkinter fix |
| 2026-05-20 | **v2.3.0** — Train Monitor: TensorBoard-backed curves, parameter checks, log sync |
| 2026-05-19 | **v2.2.0** — Portable flash-attn fix, crash logging, cross-drive monitor |
| 2026-05-19 | **v2.1.0** — Flash Attention 2 prebuilt wheels, save-by-steps |
| 2026-05-18 | **v2.0.0** — First portable release, AMD detection, bf16 fix |

Full details in [CHANGELOG.md](CHANGELOG.md).

</details>

<details>
<summary><b>Credits</b></summary>

[Akegarasu/lora-scripts](https://github.com/Akegarasu/lora-scripts) · [kohya-ss/sd-scripts](https://github.com/kohya-ss/sd-scripts) · [LyCORIS](https://github.com/KohakuBlueleaf/LyCORIS) · [T-LoRA](https://github.com/ControlGenAI/T-LoRA) — Full attribution in [NOTICE.md](NOTICE.md)

</details>

---

<p align="center"><sub>Maintainer: <b><a href="https://github.com/wochenlong">@wochenlong</a></b> · <a href="CONTRIBUTORS.md">Contributors</a></sub></p>
