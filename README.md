<p align="center">
  <img src="assets/readme/next-trainer-cover.png" alt="Next Trainer" width="880" />
</p>

<h1 align="center">Anima Edit — Image Editing LoRA Training</h1>

<p align="center">
  <b><code>anima-edit</code> experimental branch</b>: train paired <strong>Target + Reference</strong> datasets in the Next Trainer WebUI with <strong>single-reference</strong> or <strong>dual-reference</strong> layouts.<br/>
  <sub>Built on kohya-ss/sd-scripts Anima and conditioning work from <a href="https://github.com/Mirumo0u0/sd-scripts">Mirumo0u0/sd-scripts</a>.</sub>
</p>

<p align="center">
  <a href="https://github.com/wochenlong/lora-scripts-next/tree/anima-edit"><img src="https://img.shields.io/badge/branch-anima--edit-a78bfa?style=for-the-badge" alt="anima-edit branch"/></a>
  <a href="https://github.com/wochenlong/lora-scripts-next/blob/anima-edit/README-zh.md"><b>中文</b></a>
  <a href="https://github.com/wochenlong/lora-scripts-next/blob/anima-edit/NOTICE.md"><b>Credits</b></a>
</p>

---

## Quick start

```text
git clone https://github.com/wochenlong/lora-scripts-next.git
cd lora-scripts-next
git checkout anima-edit
run_gui.bat          # Windows; see Install below for Linux
```

| Mode | Entry |
|------|--------|
| **WebUI** | **http://127.0.0.1:28000/lora/anima-edit.html** (sidebar Anima Image Edit) |
| **CLI** | `accelerate launch` + `scripts/dev/anima_train_network.py --config_file …` → **[CLI guide](docs/anima-edit-cli.md)** |

> The portable Release and **`main`** branch do **not** ship this feature yet.

---

## Command-line training (advanced)

See **[docs/anima-edit-cli.md](docs/anima-edit-cli.md)** for single- and dual-reference layouts, dataset TOML fields, and example configs.

**Dual-reference (multi-image edit) quick start:**

```powershell
accelerate launch --num_cpu_threads_per_process 1 `
  scripts/dev/anima_train_network.py `
  --config_file docs/examples/anima-edit-dual-ref-smoke.toml

accelerate launch --num_cpu_threads_per_process 1 `
  scripts/dev/anima_train_network.py `
  --config_file docs/examples/anima-edit-dual-ref-10epoch.toml
```

Dataset template: [anima-edit-dual-ref-dataset.toml](docs/examples/anima-edit-dual-ref-dataset.toml) (`conditioning_multi_reference = true`, `conditioning_reference_count = 2`). Fetch a small public set: `python script/ops/fetch_multiref_anima_edit_subset.py --count 48 --seed 42`.

---

## Train image editing in the WebUI

### Entry (use the correct page)

| Goal | Sidebar / URL |
|------|----------------|
| **Image-editing LoRA (this branch)** | **Anima Image Edit** → `/lora/anima-edit.html` |
| Anima text-to-image LoRA | **Anima** → `/lora/sd3.html` (not Edit) |

Train type: **`anima-edit-lora`**. Fill Anima base model, VAE, Qwen3, and T5, then configure Target / Reference under **image-editing dataset & preview**.

### Single reference (one ref image per sample)

Set **reference layout** to **「单张参考图」** (single reference).

```text
my_dataset/
├── target/
│   ├── foo.png
│   └── foo.txt
└── reference/
    └── foo.png          # same stem as target; same dimensions
```

Example config: [anima-edit-single-ref-12epoch.toml](docs/examples/anima-edit-single-ref-12epoch.toml)

### Dual reference (two ref images — “multi-image” edit training)

Set **reference layout** to **「双张参考图」** (dual reference). P0 fixes **2** references per sample (latent time-axis concat).

```text
my_dataset/
├── target/
│   ├── foo.png
│   └── foo.txt
└── reference/
    └── foo/             # folder name = target stem
        ├── 1.png        # first two files by sorted name
        └── 2.png
```

Example configs: [anima-edit-dual-ref-dataset.toml](docs/examples/anima-edit-dual-ref-dataset.toml), smoke [anima-edit-dual-ref-smoke.toml](docs/examples/anima-edit-dual-ref-smoke.toml)

Fetch a small benchmark subset:

```bash
python script/ops/fetch_multiref_anima_edit_subset.py --count 48 --seed 42
```

**Layout diagrams in the WebUI**: Edit page → **「查看数据集目录示意图 →」** → `/help/guide.html#anima-edit-dataset` (page ②).

### Suggested workflow

1. Prepare `target/` + `reference/` (single or dual layout).
2. Open **`/lora/anima-edit.html`**, set model paths and dataset dirs.
3. Pick single vs dual reference; enable preview; optional `prompt_file` ([multi-preview example](docs/examples/anima-edit-sample-prompts-multi.toml)).
4. Start training (dataset TOML, latent / TE cache, and step-0 preview behavior are handled automatically).
5. Watch **Train Monitor** at `/train-monitor` for loss and preview sanity.

### After training

Use the LoRA in ComfyUI with [ComfyUI-Cosmos-Reference](https://github.com/Mirumo0u0/ComfyUI-Cosmos-Reference). P0 focuses on **training + training previews**; multi-ref ComfyUI inference is follow-up work.

### More docs

| Topic | Link |
|-------|------|
| **CLI training (single/dual ref)** | **[docs/anima-edit-cli.md](docs/anima-edit-cli.md)** |
| WebUI guide & datasets | [docs/anima-training.md — image editing](docs/anima-training.md#图像编辑--条件训练实验) |
| Dual-reference design | [docs/design/anima-edit-multi-reference.md](docs/design/anima-edit-multi-reference.md) |
| VRAM & resolution | [docs/design/anima-edit-vram-resolution.md](docs/design/anima-edit-vram-resolution.md) |

---

## UI & samples

<p align="center">
  <img src="assets/readme/anima-edit-ui.jpg" alt="Anima Edit page: reference layout and dataset paths" width="920" />
</p>

<p align="center">
  <img src="assets/readme/anima-edit-sample.jpg" alt="Reference-driven preview sample" width="760" />
</p>

<p align="center"><sub>Sample images courtesy of <b>古柯C17H21NO4</b>.</sub></p>

### Quality expectations

This is **conditioning LoRA on an Anima T2I base**, not a dedicated image-editing foundation model. Small datasets may show fixed stains or color blocks at later epochs (overfitting).

<p align="center">
  <img src="assets/readme/anima-edit-limitations.png" alt="Overfitting artifact example" width="920" />
</p>

---

<details>
<summary><b>Install (Windows / Linux)</b></summary>

```sh
git checkout anima-edit
run_gui.bat          # Windows
bash install.bash && bash run_gui.sh   # Linux
```

Python **3.10** recommended. Optional Flash Attention 2: [docs/flash-attention.md](docs/flash-attention.md).

</details>

<details>
<summary><b>Train monitor</b></summary>

Open **http://127.0.0.1:28000/train-monitor** after starting a run.

<p align="center">
  <img src="assets/readme/screenshot-train-monitor.png" width="920" />
  <img src="assets/readme/train-monitor-samples.png" width="920" />
</p>

</details>

<details>
<summary><b>Branch scope</b></summary>

| Area | Notes |
|------|-------|
| **Anima Edit (single/dual ref)** | Primary focus |
| Anima T2I LoRA | **Anima** page, not Edit |
| Portable Release | No Anima Edit yet |

</details>

<details>
<summary><b>Mainline FAQ, changelog, repo layout</b></summary>

See [main branch README-zh](https://github.com/wochenlong/lora-scripts-next/blob/main/README-zh.md) for portable package issues, tagging, torch install, etc.

[CHANGELOG.md](CHANGELOG.md) · [docs/repo-layout.md](docs/repo-layout.md) · [NOTICE.md](NOTICE.md)

</details>

---

<p align="center"><sub>Maintainer: <b><a href="https://github.com/wochenlong">@wochenlong</a></b> · <a href="CONTRIBUTORS.md">Contributors</a></sub></p>
