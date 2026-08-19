# Next Trainer

<p align="center">
  <img src="assets/readme/next-trainer-cover.png" alt="Next Trainer" width="720" />
</p>

<p align="center">
  <strong>Local Windows training WebUI</strong><br />
  Anima · SD 1.5 · SDXL · Flux · Krea 2<br />
  <sub>GitHub repository: <code>lora-scripts-next</code></sub>
</p>

<p align="center">
  <a href="README-zh.md">中文</a>
  ·
  <a href="docs/credits.md">Credits</a>
  ·
  <a href="CHANGELOG.md">Changelog</a>
  ·
  <a href="https://github.com/wochenlong/lora-scripts-next/releases">Releases</a>
</p>

---

## `main` has changed (read this first)

**The default branch `main` is no longer the legacy multi-page UI (v2.9.1). It is now the Vue 3 workspace (`3.0.0`).**

| | |
|---|---|
| **What changed** | Cloning or tracking `main` now gives you the **Vue 3 four-pane workspace** (Training · Dataset · Tasks · Settings) at product version **`3.0.0`**. The old sidebar multi-HTML frontend is no longer what `main` ships. |
| **Why** | After soak and gate fixes on `dev`, Vue 3 needs to be the **default stable baseline**: one brand (Next Trainer), one IA, less “default branch is still the old UI” confusion, and one line for fixes plus formal portable builds. |
| **What did not change** | Portable layout folder `SD-Trainer/` and updater bat **names** stay as launcher contracts for existing installs. Engines (Kohya / Anima Fast / Musubi) remain optional by package and Settings install. |

> **Merging to `main` ≠ shipping a formal 3.0.0 portable the same day.** Source default is already `3.0.0`; user-facing 7z / “check for updates” still follow GitHub Releases after soak.

### Need the old `main` (v2.9.1 UI)?

The previous stable line is fully preserved:

| Resource | Link |
|----------|------|
| **Branch `legacy/v2.9.1`** | [github.com/…/tree/legacy/v2.9.1](https://github.com/wochenlong/lora-scripts-next/tree/legacy/v2.9.1) |
| **Tag `legacy-v2.9.1-pre-vue3`** | [github.com/…/releases/tag/legacy-v2.9.1-pre-vue3](https://github.com/wochenlong/lora-scripts-next/releases/tag/legacy-v2.9.1-pre-vue3) (same tip as pre-cutover `main`) |
| **Legacy UI portable** | [Releases → v2.9.1](https://github.com/wochenlong/lora-scripts-next/releases/tag/v2.9.1) |

Check out the old line:

```sh
git fetch origin
git switch legacy/v2.9.1
# or pin the tag:
# git switch --detach legacy-v2.9.1-pre-vue3
```

---

## What it is

**Next Trainer** is a local Windows (NVIDIA) WebUI for LoRA and full finetune.  
Built on [kohya-ss/sd-scripts](https://github.com/kohya-ss/sd-scripts), with optional [musubi-tuner](https://github.com/kohya-ss/musubi-tuner), in an Akegarasu-style workflow. Product brand and release archives use **Next Trainer** / `Next-Trainer-v*.7z`.

---

## Branches

| Branch | Role | UI | Version |
|--------|------|----|---------|
| **`main`** | **Current default stable** | Vue 3 workspace | **`3.0.0`** |
| **`dev`** | Ongoing experiments / previews | Vue 3 (may lead `main`) | experimental |
| **`legacy/v2.9.1`** | Old UI backup (not default) | Legacy prebuilt frontend | **v2.9.1** |

When filing issues, include the full sidebar version and branch (or Release archive name).

---

## Portable downloads

| Package | Notes | Get it |
|---------|-------|--------|
| **3.0.0 GA** | Preparing (lite / Kohya / Musubi flavors) | Coming to GitHub `v3.0.0` and ModelScope |
| **RC preview** | lite ~0.39 GB; kohya-musubi ~4.2 GB (Vue 3 usable) | [v2.9.2-rc.1-0813](https://github.com/wochenlong/lora-scripts-next/releases/tag/v2.9.2-rc.1-0813) · [ModelScope](https://modelscope.cn/datasets/windsing/next-trainer-portable) |
| **Legacy UI stable** | Multi-page dist / v2.9.1 | [v2.9.1](https://github.com/wochenlong/lora-scripts-next/releases/tag/v2.9.1) |

ModelScope RC example path:

```text
releases/v2.9.2-rc.1-0813/Next-Trainer-v2.9.2-rc.1-0813-kohya-musubi.7z
```

Needs Windows 10/11, NVIDIA GPU (RTX 20+ recommended); extract to a path without spaces or non-ASCII.

More: [Portable getting started](docs/portable-getting-started.md) · [Tagger models](docs/tagger-models.md) · [Build & release (collaborators)](docs/portable-build-guide.md)

---

## Quick start

### Portable

1. Run `run_gui.bat` (or the launcher named in the archive)  
2. Open **http://127.0.0.1:28000**  
3. GA builds should show **`v3.0.0`** in the sidebar (RC may still show an rc badge)

### Run current `main` from source (Vue 3)

```sh
git clone https://github.com/wochenlong/lora-scripts-next.git
cd lora-scripts-next
git checkout main
git pull

./run_gui.bat
# or: python gui.py --dev
```

```sh
git branch --show-current   # main
cat VERSION                 # 3.0.0
```

Frontend lives in `frontend/` (Vue 3 + Vite):

```sh
cd frontend
npm install
npm run dev      # hot reload (backend must be running)
npm run build    # writes frontend/dist
```

### Follow the experiment line `dev`

```sh
git fetch origin
git switch dev
git pull
```

> Do not mix uncommitted `frontend/dist` hotfixes across `main` / `dev` / `legacy`. Portable users should stay on the package version.

---

## Features

| Area | Capabilities |
|------|----------------|
| **Training** | Base model × engine × target; live TOML preview; validate / import-export / start |
| **Dataset** | WD14 tagging; image-first tag editor (filter & batch on the right) |
| **Tasks** | List, status, logs, previews / Loss — primary place to watch runs |
| **Settings** | Theme & UI, engine management (Kohya / Anima Fast / Musubi), download mirrors, About, changelog |

Backends: Anima LoRA / Fast / finetune, SD·SDXL, Flux (Kohya); optional **Krea 2** (Musubi). Plus local tagger, `/train-monitor`, TensorBoard.

- Anima Fast → [docs/anima-fast.md](docs/anima-fast.md)  
- Krea 2 multi-GPU (Linux) → [docs/krea2-linux-multigpu.md](docs/krea2-linux-multigpu.md)

### Screenshots

From the Vue 3 UI (`3.0.0` line, Chinese locale).

<details open>
<summary><strong>Training</strong></summary>

| Standard (Kohya / Anima) | Anima Fast | Krea 2 (Musubi) |
|---|---|---|
| ![Training · standard](assets/readme/vue3/01-training-standard.png) | ![Training · Fast](assets/readme/vue3/02-training-fast.png) | ![Training · Krea 2](assets/readme/vue3/08-training-krea2.png) |

</details>

<details>
<summary><strong>Dataset</strong></summary>

| Tagger | Tag editor |
|---|---|
| ![Tagger](assets/readme/vue3/03-dataset-tagger.png) | ![Editor](assets/readme/vue3/04-dataset-editor.png) |

</details>

<details>
<summary><strong>Tasks</strong></summary>

![Tasks](assets/readme/vue3/05-tasks.png)

</details>

<details>
<summary><strong>Settings</strong></summary>

| UI prefs | Engines |
|---|---|
| ![Settings · UI](assets/readme/vue3/07-settings-ui.png) | ![Settings · engines](assets/readme/vue3/06-settings-engines.png) |

</details>

---

## Supported modes

| Mode | Notes |
|------|-------|
| Anima LoRA | LoRA · LoKr · T-LoRA · from ~12 GB VRAM |
| Anima Fast | Optional runtime · 16 GB+ recommended · install in Settings |
| Anima finetune | Full DiT · ~24 GB recommended |
| SD 1.5 / SDXL | LoRA / full finetune |
| Flux | LoRA |
| Krea 2 | LoRA via Musubi · install in Settings · multi-GPU on Linux |

VRAM tips: [docs/anima-training.md](docs/anima-training.md)

---

## Docs

| Topic | Link |
|------|------|
| Credits | [docs/credits.md](docs/credits.md) |
| NOTICE | [NOTICE.md](NOTICE.md) |
| Portable notes | [docs/portable-getting-started.md](docs/portable-getting-started.md) |
| Build & release | [docs/portable-build-guide.md](docs/portable-build-guide.md) |
| Tagger models | [docs/tagger-models.md](docs/tagger-models.md) |
| Train monitor | [docs/train-monitor.md](docs/train-monitor.md) |
| Repo layout | [docs/repo-layout.md](docs/repo-layout.md) |

---

## FAQ

**What to include in a bug report?**  
Full sidebar version, train type (model/engine/target), repro steps, logs. → [Issues](https://github.com/wochenlong/lora-scripts-next/issues)

**lite vs kohya-musubi?**  
Quick / weak network → lite (deps on first run). Want Kohya + Musubi (Krea 2) ready → **kohya-musubi**. Anima Fast installs from Settings on both.

**UI completely changed after update?**  
Expected: `main` is Vue 3 now. If you need the old UI, use [`legacy/v2.9.1`](https://github.com/wochenlong/lora-scripts-next/tree/legacy/v2.9.1) or the [v2.9.1 portable](https://github.com/wochenlong/lora-scripts-next/releases/tag/v2.9.1).

---

<p align="center">
  <sub>
    Maintainer <a href="https://github.com/wochenlong">@wochenlong</a>
    ·
    <a href="docs/credits.md">Credits</a>
    ·
    <a href="CONTRIBUTORS.md">Contributors</a>
  </sub>
</p>
