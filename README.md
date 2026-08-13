# Next Trainer

**Next Trainer** is a local Windows training WebUI (GitHub repo: `lora-scripts-next`).  
LoRA and full finetune for Anima / SD 1.5 / SDXL / Flux / Krea 2, built on [kohya-ss/sd-scripts](https://github.com/kohya-ss/sd-scripts) (and optional [musubi-tuner](https://github.com/kohya-ss/musubi-tuner)) with an Akegarasu-style workflow.

> Product brand and release archives use **Next Trainer** / `Next-Trainer-v*.7z`. The portable layout folder `SD-Trainer/` (and updater bat names) stay as launcher contracts for existing installs.

[中文](README-zh.md) · [Credits](docs/credits.md) · [NOTICE](NOTICE.md) · [CHANGELOG](CHANGELOG.md)

---

## Branches and versions

| Branch | Role | UI | Version |
|--------|------|----|---------|
| **`main`** | Stable releases | Legacy prebuilt frontend | Stable **v2.9.1** |
| **`dev`** | **Vue 3 RC** (this README) | Vue 3 four-pane workspace | **`2.9.x-rc.*`** (e.g. `2.9.2-rc.1`) |

**Versioning:** pre-releases stay on **`2.9.x`** (`beta` → **`rc`**); **`3.0.0` is reserved for the formal release**. Include the full version from the sidebar when filing issues.

---

## Portable packages (Next Trainer)

| Package | Contents | Download |
|---------|----------|----------|
| **lite** | No Anima Fast / Musubi runtime; bundled WD tagger; ~**0.39 GB** | [GitHub Release v2.9.2-rc.1-0813](https://github.com/wochenlong/lora-scripts-next/releases/tag/v2.9.2-rc.1-0813) |
| **kohya-musubi** | Kohya main env (cu128) + Musubi preinstalled; same tagger; ~**4.2 GB** | [ModelScope dataset windsing/next-trainer-portable](https://modelscope.cn/datasets/windsing/next-trainer-portable) |

ModelScope path:

```text
releases/v2.9.2-rc.1-0813/Next-Trainer-v2.9.2-rc.1-0813-kohya-musubi.7z
```

Stable (legacy UI) packages: [Releases](https://github.com/wochenlong/lora-scripts-next/releases) → **v2.9.1** and earlier.

---

## How to use

### A. Portable (recommended for RC testers)

1. Download **lite** (GitHub) or **kohya-musubi** (ModelScope), extract with 7-Zip to a path **without spaces or non-ASCII characters**
2. **lite:** double-click **`run_gui.bat`** (first run installs main deps online). **kohya-musubi:** double-click **`启动.bat`**
3. Open **http://127.0.0.1:28000**
4. Confirm the sidebar shows **`v2.9.2-rc.1 · rc`** (archive build stamp: **0813**)

Requirements: Windows 10/11, NVIDIA GPU (RTX 20+ recommended).

More: [Portable getting started](docs/portable-getting-started.md) · [Tagger models](docs/tagger-models.md)

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

```sh
git branch --show-current   # should be dev
cat VERSION                 # e.g. 2.9.2-rc.1
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

## Vue 3 RC features (`dev`)

Compared with the legacy multi-page dist UI, **`dev` is a Vue 3 SPA workspace**:

| Area | Capabilities |
|------|----------------|
| **Training** | Base model × engine × target; live TOML preview; validate / import-export / start |
| **Dataset** | WD14 tagging; **image-first tag editor** (toolbar source/load, filter & batch edit in a right panel) |
| **Tasks** | Task list, status, logs, previews / Loss; primary place to watch runs |
| **Settings** | UI prefs (incl. light/dark theme), **engine management** (Kohya / Anima Fast / Musubi), **download sources** (pip / PyTorch / HF / GitHub mirrors), About, changelog |
| **Branding** | Product name **Next Trainer**; **rc** badge on prerelease versions |
| **Credits** | Settings → About; also [docs/credits.md](docs/credits.md) |

Training backends:

- Anima LoRA / Fast / finetune, SD/SDXL, Flux (Kohya line)
- **Krea 2 LoRA** via optional **Musubi-Tuner** engine (install from Settings)
- Local tagger, train monitor (`/train-monitor`), TensorBoard

Anima Fast: [docs/anima-fast.md](docs/anima-fast.md) · Krea 2 multi-GPU (Linux): [docs/krea2-linux-multigpu.md](docs/krea2-linux-multigpu.md)

### Screenshots

Captured from the `dev` Vue 3 UI (`v2.9.2-rc.1`, Chinese locale).

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
| Tagger models | [docs/tagger-models.md](docs/tagger-models.md) |
| Anima Fast | [docs/anima-fast.md](docs/anima-fast.md) |
| **Krea 2 multi-GPU (Linux host + WebUI / `dev`)** | [docs/krea2-linux-multigpu.md](docs/krea2-linux-multigpu.md) |
| Train monitor | [docs/train-monitor.md](docs/train-monitor.md) |
| Repo layout | [docs/repo-layout.md](docs/repo-layout.md) |

---

## FAQ (short)

**What to include in a bug report?**  
Full version (including `rc`), train type (model/engine/target), steps to reproduce, logs. → [Issues](https://github.com/wochenlong/lora-scripts-next/issues)

**lite vs kohya-musubi?**  
Quick / weak network → lite (install deps on first run). Want Kohya + Musubi (Krea 2) ready → **kohya-musubi** (ModelScope). Anima Fast is install-from-Settings on both.

---

<p align="center"><sub>Maintainer: <a href="https://github.com/wochenlong">@wochenlong</a> · <a href="docs/credits.md">Credits</a> · <a href="CONTRIBUTORS.md">Contributors</a></sub></p>
