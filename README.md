# Next Trainer

**Next Trainer** is a local Windows training WebUI (GitHub repo: `lora-scripts-next`).  
LoRA and full finetune for Anima / SD 1.5 / SDXL / Flux / Krea 2, plus Qwen-Image-2.1 LoRA through DiffSynth. It is built on [kohya-ss/sd-scripts](https://github.com/kohya-ss/sd-scripts) with optional [musubi-tuner](https://github.com/kohya-ss/musubi-tuner) and isolated engine runtimes, using an Akegarasu-style workflow.

> Product brand and release archives use **Next Trainer** / `Next-Trainer-v*.7z`. The portable layout folder `SD-Trainer/` (and updater bat names) stay as launcher contracts for existing installs.

[中文](README-zh.md) · [Credits](docs/credits.md) · [NOTICE](NOTICE.md) · [CHANGELOG](CHANGELOG.md)

---

## Branches and versions

| Branch | Role | UI | Version |
|--------|------|----|---------|
| **`main`** | Stable (legacy UI until cutover) | Legacy prebuilt frontend | **v2.9.1** (moving to `legacy`) |
| **`dev`** | **Vue 3 development line** (this README) | Vue 3 workspace | **`3.0.0`** |

**Versioning:** pre-releases used **`2.9.x`** (`beta` → `rc`); **formal Vue 3 release is `3.0.0`**. After default-branch cutover and portable GA, trust the sidebar version and Release archive names. Include the full version when filing issues.

---

## Portable packages (Next Trainer)

| Package | Contents | Download |
|---------|----------|----------|
| **3.0.0 GA** | Preparing (lite / Kohya / Musubi flavors) | Coming to GitHub Release `v3.0.0` and ModelScope |
| **RC (still usable)** | lite ~0.39 GB; kohya-musubi ~4.2 GB | [GitHub v2.9.2-rc.1-0813](https://github.com/wochenlong/lora-scripts-next/releases/tag/v2.9.2-rc.1-0813) · [ModelScope windsing/next-trainer-portable](https://modelscope.cn/datasets/windsing/next-trainer-portable) |

RC ModelScope example path:

```text
releases/v2.9.2-rc.1-0813/Next-Trainer-v2.9.2-rc.1-0813-kohya-musubi.7z
```

Legacy UI packages: [Releases](https://github.com/wochenlong/lora-scripts-next/releases) → **v2.9.1**.

---

## How to use

### A. Portable

1. **Until 3.0.0 packs ship:** keep using the RC packages above for Vue 3 (sidebar may still say rc; source `dev` is already `3.0.0`)
2. Extract to a path **without spaces or non-ASCII**; **lite** → `run_gui.bat`; full/split packs → follow in-archive launcher
3. Open **http://127.0.0.1:28000**
4. GA builds should show **`v3.0.0`** in the sidebar

Requirements: Windows 10/11, NVIDIA GPU (RTX 20+ recommended).

More: [Portable getting started](docs/portable-getting-started.md) · [Tagger models](docs/tagger-models.md) · [Build & release (collaborators)](docs/portable-build-guide.md)

### B. Run `dev` from source (Vue 3)

```sh
git clone https://github.com/wochenlong/lora-scripts-next.git
cd lora-scripts-next

git fetch origin
git checkout dev
git pull origin dev

# Windows
./run_gui.bat
# or: python gui.py --dev
```

Direct TOML training wrappers are also available from the repository root:
`train_anima_by_toml.sh` for the standard Anima backend and
`train_anima_fast_by_toml.sh` for the optional Anima Fast runtime.

```sh
git branch --show-current   # should be dev
cat VERSION                 # should be 3.0.0
```

Frontend lives in `frontend/` (Vue 3 + Vite):

```sh
cd frontend
npm install
npm run dev      # hot reload (backend gui must be running)
npm run build    # writes frontend/dist for static hosting
```

### C. Switch an existing clone from `main` to `dev`

```sh
git fetch origin
git switch dev
git pull
```

Back to stable:

```sh
git switch main
git pull
```

> **Note:** `main` and `dev` use different frontend architectures. Do not mix uncommitted `frontend/dist` hotfixes across branches. Portable users should use the package version as-is.

---

## Vue 3 features (`dev` / 3.0.0)

Compared with the legacy multi-page dist UI, **`dev` is a Vue 3 SPA workspace**:

| Area | Capabilities |
|------|----------------|
| **Training** | Base model × engine × target; live TOML preview; validate / import-export / start |
| **Dataset** | Managed dataset root; create/discover datasets; reliable image + TXT upload; overview stats; ZIP export; recoverable deletion; WD14 tagging; **image-first tag editor** |
| **Tasks** | Task list, status, logs, previews / Loss; primary place to watch runs |
| **Settings** | UI prefs (incl. light/dark theme), **engine management** (Kohya / Anima Fast / Musubi / DiffSynth), **plugin marketplace**, **download sources** (pip / PyTorch / HF / GitHub mirrors), About, changelog |
| **Branding** | Product name **Next Trainer**; formal **`3.0.0`** (prerelease versions still show an **rc** badge) |
| **Credits** | Settings → About; also [docs/credits.md](docs/credits.md) |

Training backends:

- Anima LoRA / Fast / finetune, SD/SDXL, Flux (Kohya line)
- **Krea 2 LoRA** via optional **Musubi-Tuner** engine (install from Settings)
- **Qwen-Image-2.1 BF16 text-to-image LoRA** via optional **DiffSynth** engine (install from Settings; `dev` integration)
- Local tagger, train monitor (`/train-monitor`), TensorBoard

Anima Fast: [docs/anima-fast.md](docs/anima-fast.md) · Krea 2 multi-GPU (Linux): [docs/krea2-linux-multigpu.md](docs/krea2-linux-multigpu.md)

### Recent `dev` updates

- **Dataset manager:** `/dataset` now opens a managed workspace with a configurable root directory. First-level folders are discovered automatically, and each dataset shows image count, caption coverage, size and last update time.
- **Reliable import and export:** upload files or nested folders while preserving relative paths; conflicts are checked before upload with explicit skip-all or overwrite-all choices. Uploads enforce per-file and batch limits, validate images/TXT files, report progress and support retrying failures. A complete dataset can be streamed as a ZIP.
- **Recoverable deletion:** deleting selected images also includes matching TXT captions; deleting files or a whole dataset moves them to a global trash area. Restore never silently overwrites newer files, while permanent deletion requires confirmation. Dataset operations are serialized to avoid upload/delete/restore races.
- **Tool handoff:** managed datasets can be opened directly in the tagger or tag editor. The editor can download individual managed files and move selected images to trash.
- **Qwen onboarding:** the home page links to the updated Qwen-Image-2.1 beginner guide and shows the Qwen tutorial poster first.
- **Runtime hardening:** engine installation no longer reports success for an empty virtual environment; dataset-config-owned training paths are left untouched; Anima Fast exposes explicit duration and validation-split controls.

### Dataset manager

Open **Dataset → Dataset manager**. The default managed root is `./datasets`, resolved from the application directory rather than the process working directory. Changing the root does not move existing data.

Supported now:

- Create and auto-discover first-level dataset folders.
- Upload PNG, JPG/JPEG, WebP, BMP and UTF-8 TXT files, including nested folder drops.
- Preview conflicts, monitor upload progress, retry failed files, and view asynchronous dataset statistics.
- Download one file from the editor or stream a complete dataset ZIP while excluding trash and temporary files.
- Soft-delete and restore files or whole datasets through the global trash view.
- Open the same dataset path in WD14 tagging or the tag editor.

Not included in this first dataset-workspace slice: ZIP import/extraction, rename, video/audio management, natural-language captioning, training-form dataset picker/validation, or write locking against an active training run.

### DiffSynth / Qwen-Image-2.1 (`dev`)

Install, check, repair or uninstall DiffSynth from **Settings → Training engines**. It uses an isolated Python 3.12 / PyTorch 2.8 CUDA 12.8 environment.

- Select a complete model directory or separate supported BF16 DiT, text encoder and VAE files, including Comfy-Org components. Processor resources are managed automatically.
- Use images with matching TXT captions (including Kohya-style repeat folders), or CSV / JSON / JSONL metadata.
- Supports TE/VAE encoding caches, CPU offload, bucketing, batch training and per-Sample previews at step or epoch intervals. CPU offload with previews requires encoding caches; cached previews reuse the training DiT.
- Initial scope: single-GPU BF16 text-to-image LoRA only. Image editing, quantized training, full finetuning and full optimizer-state resume are not supported.

This is a `dev` integration, not a claim that existing portable packages include it. The contributor reports previews followed by continued training with CPU offload both enabled and disabled. Independent ComfyUI reload/inference of the exported LoRA remains a **pre-`main` acceptance item**.

Configuration and limitations: [DiffSynth guide](docs/diffsynth.md).

### Screenshots

Captured from the `dev` Vue 3 UI (`3.0.0` line, Chinese locale).

#### Training

| Standard (Kohya / Anima LoRA) | Anima Fast | Krea 2 (Musubi) |
|---|---|---|
| ![Training · standard](assets/readme/vue3/01-training-standard.png) | ![Training · Fast](assets/readme/vue3/02-training-fast.png) | ![Training · Krea 2](assets/readme/vue3/08-training-krea2.png) |

#### Dataset

The screenshots below predate the new dataset-manager landing view; the tagger and editor remain available as tabs in the same workspace.

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
| Qwen-Image-2.1 | DiffSynth · single-GPU BF16 text-to-image LoRA · `dev` integration |

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
| DiffSynth / Qwen-Image-2.1 | [docs/diffsynth.md](docs/diffsynth.md) |
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
