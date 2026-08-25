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
  <a href="#roadmap">Roadmap</a>
  ·
  <a href="docs/credits.md">Credits</a>
  ·
  <a href="CHANGELOG.md">Changelog</a>
  ·
  <a href="https://github.com/wochenlong/lora-scripts-next/releases">Releases</a>
</p>

---

## What it is

**Next Trainer** is a **local trainer for the future — and for agents**:  
the UI stays familiar and ready in one unpack, while the product itself is built like a professional workbench — **one trainer for most common models**, kept current as new models and engines arrive.

For people, it is a local trainer: tagging, starting runs, watching tasks, and switching engines live in one professional UI. It runs on Windows and Linux.  
For platforms and agents, the goal is a modular surface: use the full package today, and **later** plug training into automated workflows as one step.

You still train LoRA or full finetune on a local NVIDIA GPU.  
The stack stays grounded in proven backends: the main path is built on [kohya-ss/sd-scripts](https://github.com/kohya-ss/sd-scripts); for Krea 2 you can optionally plug in [musubi-tuner](https://github.com/kohya-ss/musubi-tuner).  
The public brand is **Next Trainer**, and release archives usually look like `Next-Trainer-v*.7z`. The default UI is the Vue 3 workspace at **3.0.0**, with Training, Dataset, Tasks, and Settings.

---

## What you can do

In short: tagging, caption editing, choosing a model, starting training, watching progress, and reading logs can stay in one local trainer.

Common training routes covered:

1. Anima LoRA  
2. Anima Fast  
3. Anima full finetune  
4. SD 1.5, SDXL, and Flux  
5. Optional Krea 2  

Local tagging, a train monitor page, and TensorBoard are included too.

### Why try this over other trainers

If other tools force a choice between “familiar” and “ahead,” Next Trainer wants both.

1. **UI: familiar, ready in one go**  
   The flow deliberately keeps habits familiar to Akegarasu-style users (with thanks to Akegarasu; see [Credits](docs/credits.md)). Unpack the portable package and start. Pick a model, fill parameters, import TOML, train, watch previews — no relearning just to get a new shell.

2. **Capability: professional, one trainer for common models**  
   Anima, SD 1.5, SDXL, Flux, and optional Krea 2 live in one workbench. Kohya is the baseline; engines such as Anima Fast and Musubi install and switch on demand.

3. **Pace: kept up to date**  
   New models and common training paths keep landing here, instead of freezing around one script wrapper. Individuals can follow portable releases; developers and platforms can follow `main` / `dev`.

4. **Code: modular, with agent hooks planned**  
   The design goal is not “UI only.” Modules can be composed, configs import and export, and tasks plus logs are machine-readable. People can use the full UI today; agent and platform hooks for plugging in just the training step are on the roadmap.

5. **Process: runs stay visible**  
   Status, logs, previews, and Loss live on the Tasks page. After training starts, you do not need a pile of external windows just to watch the run.

This is not a cloud one-click platform, and it does not pretend to replace every specialized tool.  
What it aims to be: a local trainer for the future — and for agents — broad enough for common models, and current enough to keep moving.

---

## Features

### Training

1. Pick a base model  
2. Pick an engine  
3. Pick a training target  
4. Preview TOML on the right  
5. Validate, import or export, then start training

### Dataset

1. Run WD14 tagging  
2. Edit tags in an image-first editor  
3. Use filters and batch actions in the right panel

### Tasks

Watch the task list, status, logs, preview images, and Loss. This is the main page for following a run.

### Settings

1. Theme and UI prefs  
2. Engine management  
3. Download mirrors  
4. About and changelog

### Rough VRAM guidance

1. **Anima LoRA**  
   Supports LoRA, LoKr, and T-LoRA. Starts around 12 GB.

2. **Anima Fast**  
   Optional separate runtime. 16 GB or more is recommended. Install it in Settings.

3. **Anima full finetune**  
   Full DiT. About 24 GB is recommended.

4. **SD 1.5 and SDXL**  
   LoRA and full finetune.

5. **Flux**  
   LoRA.

6. **Krea 2**  
   LoRA through Musubi. Prefer the **musubi** portable pack, or install Musubi from Settings on a kohya/lite pack. Multi-GPU works on Linux.

More detail: [Anima training docs](docs/anima-training.md).

Related docs:

1. [Anima Fast](docs/anima-fast.md)  
2. [Krea 2 multi-GPU](docs/krea2-linux-multigpu.md)

### Screenshots

These shots are from the Vue 3 UI with the Chinese locale.

<details open>
<summary><strong>Training</strong></summary>

| Kohya or Anima standard | Anima Fast | Krea 2 |
|---|---|---|
| ![Training standard](assets/readme/vue3/01-training-standard.png) | ![Training Fast](assets/readme/vue3/02-training-fast.png) | ![Training Krea 2](assets/readme/vue3/08-training-krea2.png) |

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
| ![Settings UI](assets/readme/vue3/07-settings-ui.png) | ![Settings engines](assets/readme/vue3/06-settings-engines.png) |

</details>

---

## Roadmap

Public TODO list — **no hard dates**. Track progress on [Issues](https://github.com/wochenlong/lora-scripts-next/issues). Feedback and use-cases welcome.

### Engines & capabilities

- [ ] Plug in [AI Toolkit](https://github.com/ostris/ai-toolkit) (more training paths for newer models)
- [ ] Plug in [DiffSynth-Studio](https://github.com/modelscope/DiffSynth-Studio) (e.g. text-to-image LoRA)
- [ ] **Image-editing** model training
- [ ] **Video** model training

### Models & data

- [ ] **Model manager**: per base-model-family defaults, local-first, remote ID → engine-native layout
- [ ] **API tagging** (external / multimodal caption APIs)
- [ ] **Natural-language tagging** (describe in plain language → captions)

### Automation

- [ ] **Agent / API hooks**: make training and task status callable from other tools (part of the modular goal)

---

## Downloads, setup, and other notes

### Downloads

**Formal [v3.0.0](https://github.com/wochenlong/lora-scripts-next/releases/tag/v3.0.0)** is out (Vue 3 workbench). Prefer ModelScope if you are in China.

| Pack | Preinstalled | Best for | Size (approx.) | Download |
|------|--------------|----------|----------------|----------|
| **kohya** (default) | Kohya (cu128) | Anima / SD / SDXL / Flux | ~2.5 GB (two volumes) | [GitHub](https://github.com/wochenlong/lora-scripts-next/releases/tag/v3.0.0) · [ModelScope](https://www.modelscope.cn/datasets/Next-Lab/next-trainer-releases) |
| **musubi** | Musubi | **Krea 2** LoRA | ~2.2 GB | **[ModelScope](https://www.modelscope.cn/datasets/Next-Lab/next-trainer-releases)** (`releases/v3.0.0/Next-Trainer-v3.0.0-musubi.7z`) |
| **lite** | Almost no training env | Bring-your-own deps | ~0.4 GB | GitHub · ModelScope |

- Kohya split: `Next-Trainer-v3.0.0-kohya.7z.001` + `.002` — keep both in one folder and extract with 7-Zip.  
- ModelScope dataset: [`Next-Lab/next-trainer-releases`](https://www.modelscope.cn/datasets/Next-Lab/next-trainer-releases), path `releases/v3.0.0/`.  
- Base checkpoints and Anima Fast are **not** preinstalled (install Fast from Settings). Krea 2 steps: [portable Krea 2 guide](docs/portable-1.5-krea2-guide.md).  
- Old UI: [v2.9.1](https://github.com/wochenlong/lora-scripts-next/releases/tag/v2.9.1).

Runtime needs:

1. Windows 10 / 11, or Linux  
2. NVIDIA GPU, RTX 20-series or newer recommended  
3. For portable packages, extract to a path without Chinese characters and without spaces (portable builds are mainly for Windows; on Linux, prefer running from source)

More reading:

1. [Portable getting started](docs/portable-getting-started.md)  
2. [Tagger models](docs/tagger-models.md)  
3. [Build and release](docs/portable-build-guide.md)

### Start from a portable package

1. Extract the archive  
2. Run **`启动.bat`** at the root (or `run_gui.bat`; follow the pack notes)  
3. Open http://127.0.0.1:28000  
4. The sidebar should show **`v3.0.0`**

### Run `main` from source

```sh
git clone https://github.com/wochenlong/lora-scripts-next.git
cd lora-scripts-next
git checkout main
git pull

./run_gui.bat
```

Or:

```sh
python gui.py --dev
```

Check the version:

```sh
git branch --show-current
cat VERSION
```

Frontend source lives in `frontend/`. It uses Vue 3 and Vite.

```sh
cd frontend
npm install
npm run dev
npm run build
```

`npm run dev` needs the backend already running.  
`npm run build` writes into `frontend/dist`.

### Which branch to use

1. **`main`**  
   Current default stable line. Vue 3 workspace. Version **3.0.0**.

2. **`dev`**  
   Where new work lands first. Also Vue 3, and it may move ahead of `main`.

3. **`legacy/v2.9.1`**  
   Backup of the old UI. Use this only when you need the old frontend.

Follow the experiment line:

```sh
git fetch origin
git switch dev
git pull
```

Note: `main`, `dev`, and `legacy` use different frontend layouts.  
Do not mix uncommitted `frontend/dist` hotfixes across them.  
Portable users can stay on the package version and skip branch switching.

### Why `main` moved from the old UI to Vue 3

Vue 3 already soaked on `dev`, and the important gate bugs were fixed.  
Promoting it keeps one brand and one page structure, and puts stable fixes and later formal portables on the same default line.

A few launcher contracts stay for now. The portable folder is still named `SD-Trainer/`, and updater bat filenames stay as they are so older installs keep working.

Merging source into `main` does not ship a new 7z for every change. Formal portables are on [GitHub Releases](https://github.com/wochenlong/lora-scripts-next/releases/tag/v3.0.0) and [ModelScope](https://www.modelscope.cn/datasets/Next-Lab/next-trainer-releases); **v3.0.0** lite / kohya / musubi are available.

If you want the old UI:

1. Source branch: [legacy/v2.9.1](https://github.com/wochenlong/lora-scripts-next/tree/legacy/v2.9.1)  
2. Pre-cutover snapshot: [legacy-v2.9.1-pre-vue3](https://github.com/wochenlong/lora-scripts-next/releases/tag/legacy-v2.9.1-pre-vue3)  
3. Legacy portable: [v2.9.1](https://github.com/wochenlong/lora-scripts-next/releases/tag/v2.9.1)

```sh
git fetch origin
git switch legacy/v2.9.1
```

### Doc index

1. [Credits and Akegarasu acknowledgement](docs/credits.md)  
2. [NOTICE](NOTICE.md)  
3. [Portable getting started](docs/portable-getting-started.md)  
4. [Build and release](docs/portable-build-guide.md)  
5. [Tagger models](docs/tagger-models.md)  
6. [Train monitor](docs/train-monitor.md)  
7. [Repo layout](docs/repo-layout.md)

### Acknowledgements to Akegarasu

Next Trainer thanks **Akegarasu** and [Akegarasu/lora-scripts](https://github.com/Akegarasu/lora-scripts) (SD-Trainer) for years of open local-training WebUI and portable packaging work. This project continues from that lineage. Full credits: [Credits](docs/credits.md) and [NOTICE.md](NOTICE.md).

### FAQ

**What should a bug report include**

Please include:

1. The full version from the sidebar  
2. The base model, engine, and training target you used  
3. Steps to reproduce  
4. Relevant logs  

Then open an [Issue](https://github.com/wochenlong/lora-scripts-next/issues).

**How do I choose lite vs kohya vs musubi**

1. If your network is weak, or you want a lighter first launch, pick **lite**. Dependencies install on first run.  
2. For day-to-day Anima / SD / SDXL / Flux, pick **kohya** (default).  
3. For **Krea 2**, pick **musubi** (on ModelScope; or install Musubi from Settings).  
4. On every pack, Anima Fast still needs a separate install in Settings.

**Can I reuse configs between 3.0.0 and the old stable line**

Most TOML files still import.  
Navigation and local storage keys differ, so trust what the current import page shows after loading.

**Why did the UI change completely after update**

That is expected. Current `main` is Vue 3.

If you want the old UI:

1. Switch to [legacy/v2.9.1](https://github.com/wochenlong/lora-scripts-next/tree/legacy/v2.9.1)  
2. Or install the [v2.9.1 portable](https://github.com/wochenlong/lora-scripts-next/releases/tag/v2.9.1)

---

## Changelog

Full history: [CHANGELOG.md](CHANGELOG.md).  
Release notes: [Releases](https://github.com/wochenlong/lora-scripts-next/releases).

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
