# Next Trainer

**Next Trainer** is a local Windows training WebUI (GitHub repo: `lora-scripts-next`).  
LoRA and full finetune for Anima / SD 1.5 / SDXL / Flux / **FLUX.2 Klein** / Krea 2, built on [kohya-ss/sd-scripts](https://github.com/kohya-ss/sd-scripts) with optional [musubi-tuner](https://github.com/kohya-ss/musubi-tuner) and [AI Toolkit](https://github.com/ostris/ai-toolkit), following an Akegarasu-style workflow.

> Product brand and release archives use **Next Trainer** / `Next-Trainer-v*.7z`. The portable layout folder `SD-Trainer/` (and updater bat names) stay as launcher contracts for existing installs.

[中文](README-zh.md) · [Credits](docs/credits.md) · [NOTICE](NOTICE.md) · [CHANGELOG](CHANGELOG.md)

---

## Branches and versions

| Branch | Role | UI | Version |
|--------|------|----|---------|
| **`main`** | Stable release | Vue 3 workspace | **`3.1.0`** |
| **`dev`** | Next-version integration and acceptance | Vue 3 workspace | Follows development |

Include the full version shown in the sidebar or `VERSION` when filing issues. The old UI baseline remains available on `legacy/v2.9.1` for rollback and comparison.

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

More: [Portable getting started](docs/portable-getting-started.md) · [Tagger models](docs/tagger-models.md) · [Build & release (collaborators)](docs/portable-build-guide.md)

### B. Run from source

```sh
git clone https://github.com/wochenlong/lora-scripts-next.git
cd lora-scripts-next

# Windows
./run_gui.bat
# or: python gui.py --dev
```

Direct TOML training wrappers are also available from the repository root:
`train_anima_by_toml.sh` for the standard Anima backend and
`train_anima_fast_by_toml.sh` for the optional Anima Fast runtime.

```sh
git branch --show-current
cat VERSION                 # formal release branch should be 3.1.0
```

Frontend lives in `frontend/` (Vue 3 + Vite):

```sh
cd frontend
npm install
npm run dev      # hot reload (backend gui must be running)
npm run build    # writes frontend/dist for static hosting
```

### C. Work on `dev`

```sh
git fetch origin
git switch dev
git pull
```

Return to the stable release:

```sh
git switch main
git pull
```

> **Note:** `dev` may contain changes that have not reached a stable release. Portable users should stay on formal Releases.

---

## Vue 3 features (3.1.0)

Next Trainer uses a Vue 3 SPA workspace:

| Area | Capabilities |
|------|----------------|
| **Training** | Base model × engine × target; live TOML preview; validate / import-export / start |
| **Dataset** | WD14 tagging; **image-first tag editor** (toolbar source/load, filter & batch edit in a right panel) |
| **Tasks** | Task list, status, logs, previews / Loss; primary place to watch runs |
| **Settings** | UI prefs (incl. light/dark theme), **engine management** (Kohya / Anima Fast / Musubi / AI Toolkit), plugin marketplace, **download sources** (pip / PyTorch / HF / GitHub mirrors), About, changelog |
| **Branding** | Product name **Next Trainer**; current formal version **`3.1.0`** |
| **Credits** | Settings → About; also [docs/credits.md](docs/credits.md) |

Training backends:

- Anima LoRA / Fast / finetune, SD/SDXL, Flux (Kohya line)
- **FLUX.2 Klein LoRA** via optional **AI Toolkit** (install from Settings)
- **Krea 2 LoRA** via optional **Musubi-Tuner** engine (install from Settings)
- Local tagger, train monitor (`/train-monitor`), TensorBoard

Anima Fast: [docs/anima-fast.md](docs/anima-fast.md) · Krea 2 multi-GPU (Linux): [docs/krea2-linux-multigpu.md](docs/krea2-linux-multigpu.md)

### Screenshots

Captured from the Vue 3 workspace (Chinese locale).

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

## Supported modes

| Mode | Notes |
|------|-------|
| Anima LoRA | LoRA · LoKr · T-LoRA · from ~12 GB VRAM |
| Anima Fast | Optional runtime · 16 GB+ recommended · install in Settings |
| Anima finetune | Full DiT · ~24 GB recommended |
| SD 1.5 / SDXL | LoRA / full finetune |
| Flux | LoRA |
| Krea 2 | LoRA via Musubi · install engine in Settings · multi-GPU on Linux |

See [docs/anima-training.md](docs/anima-training.md) for VRAM tips.

---

## Docs

| Topic | Link |
|------|------|
| **Credits (subpage)** | [docs/credits.md](docs/credits.md) |
| Full legal NOTICE | [NOTICE.md](NOTICE.md) |
| Portable notes | [docs/portable-getting-started.md](docs/portable-getting-started.md) |
| **Portable build & release (collaborators)** | [docs/portable-build-guide.md](docs/portable-build-guide.md) |
| Tagger models | [docs/tagger-models.md](docs/tagger-models.md) |
| Anima Fast | [docs/anima-fast.md](docs/anima-fast.md) |
| **Krea 2 multi-GPU (Linux host + WebUI / `dev`)** | [docs/krea2-linux-multigpu.md](docs/krea2-linux-multigpu.md) |
| Train monitor | [docs/train-monitor.md](docs/train-monitor.md) |
| Repo layout | [docs/repo-layout.md](docs/repo-layout.md) |
| CLI entry points (`train_anima_by_toml.sh` / `train_anima_fast_by_toml.sh`) | [docs/cli-args.md](docs/cli-args.md) |

---

## FAQ (short)

**What to include in a bug report?**  
Full version from the sidebar, train type (model/engine/target), steps to reproduce, logs. → [Issues](https://github.com/wochenlong/lora-scripts-next/issues)

**lite vs kohya-musubi?**  
Quick / weak network → lite (install deps on first run). Want Kohya + Musubi (Krea 2) ready → **kohya-musubi** (ModelScope). Anima Fast is install-from-Settings on both.

---

<p align="center"><sub>Maintainer: <a href="https://github.com/wochenlong">@wochenlong</a> · <a href="docs/credits.md">Credits</a> · <a href="CONTRIBUTORS.md">Contributors</a></sub></p>
