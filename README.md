# Next Trainer

<p align="center">
  <img src="assets/readme/next-trainer-cover.png" alt="Next Trainer" width="720" />
</p>

<p align="center">
  <strong>A local trainer for the future — and for agents</strong><br />
  Familiar UI · One trainer for common models · Kept up to date<br />
  <sub>For creators and platforms · Agent hooks planned · Repo <code>lora-scripts-next</code></sub>
</p>

<p align="center">
  <a href="README-zh.md">中文</a>
  ·
  <a href="#whats-new-in-310">What's new</a>
  ·
  <a href="docs/credits.md">Credits</a>
  ·
  <a href="CHANGELOG.md">Changelog</a>
  ·
  <a href="https://github.com/wochenlong/lora-scripts-next/releases">Releases</a>
</p>

<p align="center"><sub>Product: <strong>Next Trainer</strong> · Portable compatibility keeps the existing <code>SD-Trainer/</code> folder and updater names.</sub></p>

---

## What it is

**Next Trainer** is a local trainer for the future — and for agents: the UI stays familiar, while the product is built as a professional workbench for common models and multiple training engines.

Train Anima, SD 1.5, SDXL, Flux, FLUX.2 Klein, and Krea 2 LoRA or finetunes locally on an NVIDIA GPU. Tag datasets, edit captions, import TOML, start runs, and follow logs, previews, and Loss from one workspace.

The main path uses [kohya-ss/sd-scripts](https://github.com/kohya-ss/sd-scripts), with optional [musubi-tuner](https://github.com/kohya-ss/musubi-tuner) and [AI Toolkit](https://github.com/ostris/ai-toolkit) engines.

---

## Branches and versions

| Branch | Role | UI | Version |
|--------|------|----|---------|
| **`main`** | Stable release | Vue 3 workspace | **`3.1.0`** |
| **`dev`** | Next-version integration and acceptance | Vue 3 workspace | Follows development |

Issue reports should include the sidebar version or `VERSION`. The old UI baseline remains on `legacy/v2.9.1`.

---

## Portable packages (Next Trainer)

| Package | Contents | Download |
|---------|----------|----------|
| **3.0.0 GA** | lite / Kohya flavors | [GitHub Release v3.0.0](https://github.com/wochenlong/lora-scripts-next/releases/tag/v3.0.0) |
| **3.1.0** | Source release candidate; portable packages follow acceptance | [Releases](https://github.com/wochenlong/lora-scripts-next/releases) |

---

## How to use

### A. Portable

1. Download a formal package and extract it to a path **without spaces or non-ASCII**
2. **lite** → `run_gui.bat`; full/split packs → follow the in-archive launcher
3. Open **http://127.0.0.1:28000**
4. The sidebar version should match the downloaded Release

Requirements: Windows 10/11, NVIDIA GPU (RTX 20+ recommended).

More: [Portable](docs/portable-getting-started.md) · [Tagger](docs/tagger-models.md) · [Build](docs/portable-build-guide.md)

### B. Run from source

```sh
git clone https://github.com/wochenlong/lora-scripts-next.git
cd lora-scripts-next

# Windows
./run_gui.bat
# or: python gui.py --dev
```

Developers: see [CLI and TOML](docs/cli-args.md), [repo layout](docs/repo-layout.md), and [build & release](docs/portable-build-guide.md).

---

## What's new in 3.1.0

The 3.1.0 source release is now on `main`. Highlights:

- **Anima Fast** now covers Anima 2.9B and T-LoRA with a separate runtime, clearer preflight checks, improved installation progress, and safer defaults. Anima Fast was verified on an RTX 4090 for 100 steps with `AdamW`.
- **Unified engines**: Kohya, Anima Fast, Musubi, and AI Toolkit now share one engine model.
- **New paths**: AI Toolkit / Klein, plugin marketplace, and Pi Agent foundations.
- **Better operations**: task queue, persistence, cleanup, retry, config export, logs, previews, and Loss isolation.
- **Stability**: safer parameter mapping, TOML step/epoch handling, multi-GPU launch fixes, and improved Windows installation behavior.

Details: [full changelog](CHANGELOG.md) · [Anima Fast](docs/anima-fast.md) · [task workbench](docs/issues/286-task-workbench.md).

Portable and AIO archives still require their final build, acceptance, and publication steps.

---

## Screenshots

The Vue 3 workspace covers training, datasets, tasks, and engine settings. More detailed workflows live in the linked docs.

Captured from the Chinese locale:

#### Training

| Standard (Kohya / Anima LoRA) | Anima Fast | Krea 2 (Musubi) |
|---|---|---|
| ![Training · standard](assets/readme/vue3/01-training-standard.png) | ![Training · Fast](assets/readme/vue3/02-training-fast.png) | ![Training · Krea 2](assets/readme/vue3/08-training-krea2.png) |

#### Dataset

| Tagger | Tag editor |
|---|---|
| ![Dataset · tagger](assets/readme/vue3/03-dataset-tagger.png) | ![Dataset · editor](assets/readme/vue3/04-dataset-editor.png) |

#### Tasks

![Tasks](assets/readme/vue3/05-tasks.png)

#### Settings

| UI prefs | Engines |
|---|---|
| ![Settings · UI](assets/readme/vue3/07-settings-ui.png) | ![Settings · engines](assets/readme/vue3/06-settings-engines.png) |

---

## Supported models

Anima · SD 1.5 · SDXL · Flux · FLUX.2 Klein · Krea 2.
Training targets and VRAM guidance: [Anima training](docs/anima-training.md) · [Anima Fast](docs/anima-fast.md) · [Krea 2 multi-GPU](docs/krea2-linux-multigpu.md).

---

## Further reading

[Portable setup](docs/portable-getting-started.md) · [Anima Fast](docs/anima-fast.md) · [Krea 2](docs/krea2-linux-multigpu.md) · [TOML / CLI](docs/cli-args.md) · [Build & release](docs/portable-build-guide.md) · [Credits](docs/credits.md)

---

## FAQ (short)

**What to include in a bug report?**  
Full version from the sidebar, train type (model/engine/target), steps to reproduce, logs. → [Issues](https://github.com/wochenlong/lora-scripts-next/issues)

**lite vs kohya-musubi?**  
Quick / weak network → lite (install deps on first run). Want Kohya + Musubi (Krea 2) ready → **kohya-musubi** (ModelScope). Anima Fast is install-from-Settings on both.

---

<p align="center"><sub>Maintainer: <a href="https://github.com/wochenlong">@wochenlong</a> · <a href="docs/credits.md">Credits</a> · <a href="CONTRIBUTORS.md">Contributors</a></sub></p>
