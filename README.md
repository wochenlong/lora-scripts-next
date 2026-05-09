<p align="center">
  <img src="assets/readme/logo.svg" alt="lora-scripts-next" width="140" height="140" />
</p>

<h1 align="center">lora-scripts-next</h1>

<p align="center">
  <strong>SD-Trainer</strong> — LoRA · Dreambooth · one-click training shell around <a href="https://github.com/kohya-ss/sd-scripts">kohya-ss/sd-scripts</a><br/>
  <sub><em>A personal fork: ship faster experiments, keep the familiar GUI.</em></sub>
</p>

<p align="center">
  <a href="https://github.com/wochenlong/lora-scripts-next"><img src="https://img.shields.io/github/stars/wochenlong/lora-scripts-next?style=flat-square&label=stars&logo=github&color=8b5cf6" alt="stars"/></a>
  <a href="https://github.com/wochenlong/lora-scripts-next"><img src="https://img.shields.io/github/forks/wochenlong/lora-scripts-next?style=flat-square&label=forks&color=06b6d4" alt="forks"/></a>
  <a href="https://github.com/wochenlong/lora-scripts-next/blob/main/LICENSE"><img src="https://img.shields.io/github/license/wochenlong/lora-scripts-next?style=flat-square&color=ec4899" alt="license"/></a>
  <a href="https://github.com/wochenlong/lora-scripts-next/releases"><img src="https://img.shields.io/github/v/release/wochenlong/lora-scripts-next?include_prereleases&style=flat-square&color=a78bfa" alt="release"/></a>
</p>

<p align="center">
  <a href="https://github.com/wochenlong/lora-scripts-next/releases"><b>Releases</b></a>
  &nbsp;·&nbsp;
  <a href="https://github.com/wochenlong/lora-scripts-next/blob/main/README-zh.md"><b>中文 README</b></a>
  &nbsp;·&nbsp;
  <a href="https://github.com/wochenlong/lora-scripts-next/blob/main/NOTICE.md"><b>NOTICE</b></a>
</p>

---

<p align="center">
  <sub>Maintainer: <b>@wochenlong</b> — this repo is where I wire <b>Anima</b>, <b>Rectified Flow</b>, and my own training habits into the classic “秋叶式” stack.</sub>
</p>

<br/>

## Changelog

See **[CHANGELOG.md](CHANGELOG.md)** for image-oriented release notes (e.g. **v2.1**: AutoDL hashed safetensors, xformers/SDPA boot patch, and the **port 6008** training monitor refresh in `train_status_server.py`).

## At a glance

| | |
|:---|:---|
| **Train WebUI** | Single dashboard: presets, tensorboard hook, tagger, tag editor — open **`http://127.0.0.1:28000`** after `run_gui.ps1` / `run_gui.sh`. |
| **What this fork adds** | **Anima LoRA** training entry in the sidebar (Anima DiT + Qwen3 + T5), live training log over SSE at **`/train-log`**, and a `MIKAZUKI_FRONTEND_DIST` env var for swapping the static UI without touching the submodule. |
| **Back end** | [kohya-ss/sd-scripts](https://github.com/kohya-ss/sd-scripts); SDXL RF ideas from [bluvoll/Akegarasu-lora-scripts-RF](https://github.com/bluvoll/Akegarasu-lora-scripts-RF); Anima path from [WhitecrowAurora/lora-rescripts](https://github.com/WhitecrowAurora/lora-rescripts) (**SD-reScripts**). |
| **Docs** | Full attribution & licenses in [`NOTICE.md`](NOTICE.md). |

---

## Credits & upstream

This repo is built on top of the following open-source projects. Thank you to all the authors.

| Project | Role in this fork |
|:--------|:------------------|
| [Akegarasu/lora-scripts](https://github.com/Akegarasu/lora-scripts) | GUI framework & one-click training UX ("秋叶式" stack) |
| [kohya-ss/sd-scripts](https://github.com/kohya-ss/sd-scripts) | Core training scripts backend |
| [bluvoll/Akegarasu-lora-scripts-RF](https://github.com/bluvoll/Akegarasu-lora-scripts-RF) | SDXL Rectified Flow training implementation reference |
| [WhitecrowAurora/lora-rescripts](https://github.com/WhitecrowAurora/lora-rescripts) | Anima LoRA training integration reference (SD-reScripts) |

Full license attribution in [`NOTICE.md`](NOTICE.md). If anything is missing or incorrectly attributed, please open an issue — we will fix it promptly.

---

## Interface preview

<p align="center">
  <img src="assets/readme/screenshot-webui.png" alt="SD-Trainer WebUI screenshot" width="920" />
</p>

<p align="center"><sub>TensorBoard, WD 1.4 Tagger, and Tag Editor open inside the same WebUI.</sub></p>

---

# Usage

### Dependencies

Python **3.10** and **Git**.

### Clone (with submodules)

```sh
git clone --recurse-submodules https://github.com/wochenlong/lora-scripts-next.git
cd lora-scripts-next
```

## SD-Trainer GUI

### Windows

**Install:** run `install.ps1` (mainland China: `install-cn.ps1`).  
**Train:** run `run_gui.ps1` → opens **[http://127.0.0.1:28000](http://127.0.0.1:28000)**.

### Linux

**Install:** `install.bash`  
**Train:** `bash run_gui.sh` → same URL as above.

### Anima LoRA training

After launching the WebUI, open the **Anima LoRA** entry in the left sidebar (it lives where SD3 used to be — the `model_train_type` is wired to `anima-lora`, and the backend dispatches to [`scripts/dev/anima_train_network.py`](scripts/dev/anima_train_network.py)). Fill in the four model paths the schema asks for:

| Field | What it expects |
|---|---|
| `pretrained_model_name_or_path` | Anima DiT weights, e.g. `./sd-models/anima-preview.safetensors` |
| `vae` | Qwen Image VAE checkpoint (required) |
| `qwen3` | Qwen3 text model (`.safetensors` / `.pt` or a local model directory) |
| `t5` | T5 text encoder weights |

Toggling **`enable_preview`** in the form switches sample generation to Anima-friendly defaults (1024×1024, CFG 4.5, 40 steps, seed 42, with the Anima sample prompts pre-filled). Windows users can also run [`run_gui_anima.bat`](run_gui_anima.bat) which boots the WebUI with the Anima-oriented defaults.

> Heads-up: the page is still served at the `/lora/sd3.html` URL (the SPA route is reused). The visible label, parameter set, and trainer script are all Anima — only the URL slug is legacy.

### Live training log (SSE)

Whenever the WebUI fires off a run, the backend captures stdout and republishes it line-by-line over Server-Sent Events. Two ways to consume it:

- **Standalone full-screen viewer** — open `http://127.0.0.1:28000/train-log?task_id=<task_id>` in a new tab, or embed it as `<iframe src="/train-log?task_id=…" />`. Backed by [`mikazuki/static/train_log.html`](mikazuki/static/train_log.html).
- **Raw stream** — `GET /api/train/log/stream/{task_id}` returns `text/event-stream`; useful for agents, dashboards, or remote monitoring on AutoDL / cloud GPUs.

The `task_id` is what `POST /api/run` returns when a training job is started, and is also persisted in the browser's `localStorage` so the viewer auto-resumes.

### Frontend static files

The training GUI backend serves `frontend/dist` by default. The directory is a prebuilt static-file submodule (`hanamizuki-ai/lora-gui-dist`), not the frontend source tree — there is no `package.json` or build step inside this repo. The "Anima LoRA" page you see does **not** live in `dist`; it is rendered from `mikazuki/schema/sd3-lora.ts`, which this fork rewrites into an Anima schema. The backend ships that schema to the original UI and the form re-renders accordingly.

If you want to plug in a different UI build, set `MIKAZUKI_FRONTEND_DIST` to any directory and the backend will serve from there:

```bash
MIKAZUKI_FRONTEND_DIST=/path/to/your/dist python gui.py --listen
```

Or point the `frontend` submodule URL at your own dist repository. The backend does not build frontend source automatically.

## Legacy: script-only training

### Windows

Install with `install.ps1`, then edit and run `train.ps1`.

### Linux

Activate venv first (`source venv/bin/activate`), edit `train.sh`, run it.

### TensorBoard

`tensorboard.ps1` → [http://localhost:6006/](http://localhost:6006/)

### Anima single-subject LoRA: step-count rule of thumb

In checkpoint sweeps, **~1k–3k optimizer steps** (same “step” as `total optimization steps` in the log header) is often enough for a usable character; beyond that is mostly polish. Depends on data, repeats, buckets, rank, LR, and taste—trust your samples.

**`num batches per epoch` × epoch** ≈ cumulative steps at epoch end (e.g. 510 batches/epoch → ~1020 steps after epoch 2).

## Program arguments

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `--host` | str | `127.0.0.1` | Server host |
| `--port` | int | `28000` | Server port |
| `--listen` | bool | `false` | Listen on all interfaces |
| `--skip-prepare-environment` | bool | `false` | Skip env prep |
| `--disable-tensorboard` | bool | `false` | Disable TensorBoard |
| `--disable-tageditor` | bool | `false` | Disable tag editor |
| `--tensorboard-host` | str | `127.0.0.1` | TensorBoard host |
| `--tensorboard-port` | int | `6006` | TensorBoard port |
| `--localization` | str | | UI locale |
| `--dev` | bool | `false` | Developer mode |
