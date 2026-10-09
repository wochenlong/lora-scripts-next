# Next Trainer

**A multi-engine workspace for training AI models.**

[中文](README-zh.md) · [Download](https://github.com/wochenlong/lora-scripts-next/releases) · [Get started](#get-started) · [Development updates](docs/dev-progress.md) · [Roadmap](docs/roadmap.md)

## What Is Next Trainer?

Next Trainer brings dataset management, tagging, caption editing, training configuration and task monitoring into one Web UI, for local use or browser access to a remote training server.

Building on the Akegarasu training workflow, it integrates engines such as Kohya, Anima Fast, Musubi, DiffSynth and AI Toolkit. The goal is a professional, extensible workspace rather than a separate application for every model.

> This is the **`dev` development branch**. Features here may not be included in published portable packages. For everyday use, prefer a [Release](https://github.com/wochenlong/lora-scripts-next/releases); development progress is not a release announcement.

![Qwen-Image training workspace](assets/readme/screenshot-qwen-ui.png)

*Example interface; available options depend on the version and engine.*

## What Can It Do?

| Workflow | Current capabilities |
| --- | --- |
| Datasets | Create and discover datasets; upload images, TXT files and nested folders; check conflicts, retry failures, export ZIPs and recover deleted data |
| Tagging and editing | Local WD-family tagging; the caption editor offers tag and free-text modes, double-click full-size preview, batch selection and undo/redo; a bundled offline Chinese dictionary translates tags in bulk; datasets flow between management, tagging and editing |
| Training | Model / engine / target selection, TOML preview and import/export, LoRA and full finetuning where supported |
| Monitoring | Training queues, task status, logs, Loss and previews; TensorBoard remains an option |
| Engine management | Manage training environments, search and filter engines, drag to reorder, five items per page; engine preferences and order saved on the server |

### Models and Engines

Settings are organised as **UI, Training Engines, API, Plugins, Advanced** and **About**: endpoint and local-model configuration lives under Settings → API, network and download sources under Advanced, and the project introduction, updates and changelog under About.

**An engine integration does not imply support for every upstream model or training mode.**

| Engine | Main training entry points | Notes |
| --- | --- | --- |
| Kohya | SD 1.5, SDXL, Flux, Anima | Capabilities vary by model; standalone environment management is integrated |
| Anima Fast | Anima 2B / 2.9B LoRA | Isolated runtime with explicit base-model path selection |
| Musubi | Krea 2 LoRA | Optional installation; see the Linux multi-GPU guide |
| DiffSynth | Qwen-Image-2.1 text-to-image / image-editing LoRA | Single-GPU BF16; Edit currently uses batch size 1 |
| AI Toolkit | SDXL, Flux.1 Dev, Klein 4B / 9B, Krea 2 RAW, Anima, Qwen-Image-2.1 LoRA | Optional installation with an isolated runtime; Klein supports base / distilled variants, and Klein and Qwen offer image-editing entry points |

Install AI Toolkit from **Settings → Training Engines**, then select the model and engine on the training page. Depending on the model, supply a local model directory, single file or component paths, along with the required text encoder, VAE, configuration and tokenizer files. Model components and datasets are checked before launch. Image editing uses target and reference-image folders; preview samples have individual prompts, dimensions, seeds and reference images.

Anima's default paths are guidance, **not downloaded model weights**. Prepare models, datasets, GPU resources and dependencies for your chosen engine.

AI Toolkit acceptance: Qwen-Image-2.1 text-to-image and image editing passed three-step GPU smoke tests with saved LoRAs and preview generation. This is not full-model or long-run validation. See the [acceptance report](docs/team/pr399-acceptance-2026-10-03.md).

Guides: [Anima](docs/anima-training.md) · [Anima Fast](docs/anima-fast.md) · [Krea 2](docs/krea2-linux-multigpu.md) · [DiffSynth / Qwen](docs/diffsynth.md)

## Get Started

**Portable package:** choose a package from [Releases](https://github.com/wochenlong/lora-scripts-next/releases), follow its startup instructions and open `http://127.0.0.1:28000`. Preinstalled runtimes vary by package; base-model weights generally need to be supplied separately.

**Development source:** follow the environment instructions and switch to `dev`. On Windows, use `run_gui.bat`; with a prepared Python environment, run `python gui.py`. Frontend development and builds are documented in [frontend/README.md](frontend/README.md).

| Need help with | Documentation |
| --- | --- |
| Installation and portable packages | [Getting started](docs/portable-getting-started.md) |
| Dataset paths, upload and deletion rules | [Development feature notes](docs/dev-progress.md#dataset-workspace) |
| Tagger models and storage | [Tagger models](docs/tagger-models.md) |
| Monitoring and command-line use | [Train monitor](docs/train-monitor.md) · [CLI](docs/cli-args.md) |
| Development and packaging | [Repository layout](docs/repo-layout.md) · [Build guide](docs/portable-build-guide.md) |

### User Data

Engine preferences and ordering are stored in project-root `user_data/`, so they
survive browser and port changes. This branch also adds user preset CRUD and
configuration archives for new training tasks. GUI, monitor and TensorBoard
startup settings share a configuration file with GUI port priority.

See [user data and migration boundaries](docs/user-data.md). Existing history is
not migrated; this is not a complete migration of every browser preference.

## What We Have Built

Recent work integrated into `dev`:

- **Dataset workspace:** managed roots, nested uploads, batch conflict decisions, export, rename and recoverable deletion.
- **Caption editing and Chinese glosses:** a reworked editor that leads with the image wall, tag and free-text modes, double-click previews, batch selection and undo/redo; a bundled offline Danbooru Chinese dictionary (~330k entries) with dictionary / local model / API sources.
- **Settings structure:** reordered to UI, Training Engines, API, Plugins, Advanced and About, with a new API page for shared endpoint and local-model configuration.
- **Image-editing training:** target/reference-image workflows for DiffSynth / Qwen-Image-2.1.
- **AI Toolkit model entries:** configure LoRA in the shared training page, with model-specific quantization, memory offloading and sampling options, using the existing task queue, logs and Loss monitoring.
- **Anima path guidance:** separate defaults and remembered paths for Anima 2B / 2.9B, preserving imported paths.
- **Engine environments and UI:** standalone Kohya management, compact searchable lists, persistent drag ordering and five-item pagination.
- **Reliability:** stronger environment installation checks, configuration boundaries and portable update handling.

See [development progress and limitations](docs/dev-progress.md). Historical version notes are in [CHANGELOG](CHANGELOG.md) and [Releases](https://github.com/wochenlong/lora-scripts-next/releases).

### What Comes Next?

| Milestone | Direction |
| --- | --- |
| **3.2.0** | Dataset preparation, tagging and caption editing; continued model integrations |
| **3.3.0** | Expand AI Toolkit model-format support and improve training workflows |
| **Later 3.x** | Update reliability, an EXE client, API captioning and model publishing; individual versions not assigned |
| **4.0.0** | Official Agent support across data preparation, training and testing |

These are goals, not completion claims or release-date commitments. See the [roadmap](docs/roadmap.md) for implemented portions and remaining work.

## Contribute

When opening an [issue](https://github.com/wochenlong/lora-scripts-next/issues), include the version or commit, model and engine, reproduction steps and relevant logs. Remove tokens and private data before sharing.

Thanks to the original project, engine authors and contributors. [Credits](docs/credits.md) · [NOTICE](NOTICE.md) · [Contributors](CONTRIBUTORS.md)
