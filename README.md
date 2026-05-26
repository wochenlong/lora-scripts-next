<p align="center">
  <img src="assets/readme/next-trainer-cover.png" alt="Next Trainer" width="880" />
</p>

<h1 align="center">Next Trainer</h1>

<p align="center">
  <b>One-click LoRA training GUI for Windows</b> — supports <b>Anima</b> / SD 1.5 / SDXL / Flux<br/>
  Extract and run. No environment setup needed. 12 GB VRAM is enough for Anima LoRA.<br/>
  <sub>Powered by <a href="https://github.com/kohya-ss/sd-scripts">kohya-ss/sd-scripts</a>, Akegarasu-style GUI.</sub>
</p>

<p align="center">
  <a href="https://github.com/wochenlong/lora-scripts-next/releases"><img src="https://img.shields.io/github/v/release/wochenlong/lora-scripts-next?include_prereleases&style=for-the-badge&color=a78bfa&label=Download" alt="Download"/></a>
</p>

<p align="center">
  <a href="https://github.com/wochenlong/lora-scripts-next"><img src="https://img.shields.io/github/stars/wochenlong/lora-scripts-next?style=flat-square&label=stars&logo=github&color=8b5cf6" alt="stars"/></a>
  <a href="https://github.com/wochenlong/lora-scripts-next/blob/main/LICENSE"><img src="https://img.shields.io/github/license/wochenlong/lora-scripts-next?style=flat-square&color=ec4899" alt="license"/></a>
</p>
<p align="center">
  <a href="https://github.com/wochenlong/lora-scripts-next/blob/main/README-zh.md"><b>中文</b></a>
</p>
<p align="center">
  <a href="https://github.com/wochenlong/lora-scripts-next/blob/main/NOTICE.md"><b>Credits</b></a>
</p>

---

<p align="center">
  <img src="assets/readme/screenshot-webui.png" alt="Next Trainer GUI" width="920" />
</p>

<p align="center"><sub>New UI — sidebar navigation, model & parameter form in the center, real-time config preview on the right</sub></p>

---

## Get Started in 3 Steps

```
1. Download  →  SD-Trainer-v2.5.2.7z (~380 MB) from Releases, extract
2. Launch    →  Double-click run_gui.bat (auto-installs deps on first run, ~3 GB)
3. Train     →  Open http://127.0.0.1:28000, pick a model, set params, start training
```

> **Requirements:** Windows 10/11, NVIDIA GPU (RTX 20+), ~7 GB disk.

<details>
<summary><b>Install from source (Linux / advanced users)</b></summary>

```sh
git clone https://github.com/wochenlong/lora-scripts-next.git
cd lora-scripts-next

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

## What's Supported

| Model | Network Types | Attention Backend |
|-------|---------------|-------------------|
| **Anima** | LoRA · LoKr · **T-LoRA** | Flash Attention 2 / xformers / SDPA |
| SD 1.5 / SDXL | LoRA · LoHa · LoKr | xformers / SDPA |
| Flux | LoRA | xformers / SDPA |

---

## Anima Image Editing (Experimental)

The `anima-edit` branch adds Anima conditioning / image-editing training. Enable **Image Editing (Experimental)** on the Anima page to configure paired datasets:

- **Target directory**: final images and their `.txt` / `.json` captions.
- **Reference / Conditioning directory**: input reference images with the same filenames and dimensions.
- **Image editing preview**: uses a dedicated edit prompt plus a fixed or randomly sampled Control Image, while reusing the normal preview width, CFG, steps, sampler, and schedule.

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

> WebUI training now writes the conditioning dataset TOML and `--cn <control image>` sample prompt automatically. See [docs/anima-training.md](docs/anima-training.md) for details.
> The backend conditioning work references [Mirumo0u0/sd-scripts](https://github.com/Mirumo0u0/sd-scripts), an Apache-2.0 fork of kohya-ss/sd-scripts; this project preserves its license notices and source attribution.

---

## Train Monitor

Automatically opens a monitor page (port 6008) when training starts — GPU stats, training parameters, Loss curves, preview samples, and logs all in one dashboard.

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
| Anima LoRA Training Guide | [docs/anima-training.md](docs/anima-training.md) |
| Flash Attention 2 | [docs/flash-attention.md](docs/flash-attention.md) |
| Train Monitor & SSE API | [docs/train-monitor.md](docs/train-monitor.md) |
| Docker Deployment | [docs/docker.md](docs/docker.md) |
| CLI Arguments | [docs/cli-args.md](docs/cli-args.md) |

</details>

<details>
<summary><b>Changelog</b></summary>

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
