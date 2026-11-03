<p align="center">
  <img src="assets/readme/next-trainer-cover.png" alt="Next Trainer — 支持 MOSS 训练" width="720" />
</p>

<p align="center">
  <strong>A local training workbench for multiple models and engines</strong><br />
  Prepare datasets, train models, and follow your runs in one place.
</p>

<p align="center">
  <a href="https://github.com/wochenlong/lora-scripts-next/releases">Download</a> ·
  <a href="docs/getting-started.en.md">Quick start</a> ·
  <a href="docs/README.md">Documentation</a> ·
  <a href="README-zh.md">中文</a>
</p>


## MOSS-Image training showcase

A **100-step style LoRA test** by [KohakuBlueleaf](https://github.com/KohakuBlueleaf), trained with their [KohakuMossTrainer](https://github.com/KohakuBlueleaf/KohakuMossTrainer). The top row shows the base model; the bottom row shows the LoRA results. Shared with the author's permission as a MOSS-Image training example; these results were produced with KohakuMossTrainer.

[![MOSS-Image base model and 100-step style LoRA comparison by KohakuBlueleaf](assets/readme/kohaku-moss-style-lora.png)](assets/readme/kohaku-moss-style-lora.png)

## What's new in 3.3.0

- **Multi-engine workbench:** Kohya, Anima Fast, Musubi, AI Toolkit, DiffSynth-Studio, and MOSS (`anima_lora`) are presented through one engine workflow, with an updated model/engine matrix and tutorial index.
- **Independent Kohya runtime:** Kohya uses its own environment under `extensions/kohya/`; trainer source updates are separated from engine installation, repair, and auditing.
- **Kohya survives updates:** source and portable-package updates preserve user-owned training runtimes; the portable updater excludes `Next-Trainer/extensions/` so updating the main program does not uninstall Kohya.
- **MOSS-Image:** MOSS-Image LoRA training is available with Kohya as the recommended/default engine and `anima_lora` as an optional secondary path.
- **AI Toolkit and Ideogram 4:** AI Toolkit training and an Ideogram 4 LoRA entry are available as optional engines and are not force-installed.
- **Plugin marketplace:** the currently empty marketplace is hidden from users and skipped by default, so its unused dependencies are not downloaded.
- **3.3.1-dev portable package:** a sub-2 GB lite package includes the base runtime, frontend, WD tagger model, and offline tokenizer assets without preinstalling Kohya.

[Full changelog](CHANGELOG.md)

## Get started

**Windows users:** download the current [Next-Trainer-v3.3.1-dev-lite.7z](https://github.com/wochenlong/lora-scripts-next/releases/download/v3.3.1-dev/Next-Trainer-v3.3.1-dev-lite.7z), extract it, and use the included launcher. It contains the base runtime, frontend, WD tagger model, and offline tokenizer assets. Kohya is not preinstalled, and the empty plugin marketplace is not downloaded; install a training engine from **Settings → Training engines** when needed. An NVIDIA GPU is required; see [setup and package selection](docs/getting-started.en.md).

**Release status:** the recommended portable package is `3.3.1-dev`. The larger preinstalled-Kohya package is distributed separately from GitHub Releases; the empty plugin marketplace is hidden from users and skipped by default during builds.

For the latest source version or Linux setup, follow [run from source](docs/getting-started.en.md#from-source).

### Updating

**Source installation:**

1. Close the WebUI and stop active training jobs.
2. Run `git status` in the project directory and commit or back up any local changes.
3. For the stable version, switch to `main` and run `git pull --ff-only`. To follow the next development version, run `git fetch origin` and then switch to `dev`.
4. Start again with `run_gui.bat` on Windows or `bash run_gui.sh` on Linux. If the launcher reports changed dependencies, rerun `install-cn.ps1` / `setup_environment.py` as instructed; do not delete the project directory's user data.

Source updates change repository code only. The installed Kohya environment lives under `extensions/kohya/`; do not delete it manually. If the UI reports a broken Kohya environment after an upgrade, use **Settings → Training engines → Kohya → Repair/Install** so the current version can audit or repair it.

**Portable package:**

- Prefer `Update-Next-Trainer-Release.bat` from the package root. It downloads the latest Release and merges the program files. If GitHub Release downloads are unavailable, use `Update-Next-Trainer.bat` for a Git update.
- Close the WebUI before updating. The updater preserves `Next-Trainer\extensions\`, models, outputs, logs, training data, and configuration. `Next-Trainer\extensions\kohya\` is the independent Kohya environment and is excluded from the update merge.
- Start again with `run_gui.bat`. If the launcher reports changed dependencies, run the included `update\update_dependencies.bat`; do not delete `python_embeded` or `extensions\kohya` first.

**Old portable packages without an updater:** do not extract a new 7z directly over the old directory. Close the application, copy the old `Next-Trainer\extensions\kohya\` directory to a safe location, extract the new package into a new directory, then restore that directory to `Next-Trainer\extensions\kohya\`. Also migrate `sd-models`, `output`, `logs`, `train`, `config`, `huggingface`, and `tagger-models`. Launch from the new package. This keeps the program update separate from the Kohya environment and avoids losing the engine through an old overwrite workflow.

The lite package does not include Kohya. Install it from **Settings → Training engines** when needed. After installation, use the updater above and keep `Next-Trainer\extensions\kohya\`; updating the main program will not uninstall Kohya. See the [portable update contract](docs/portable-packaging-git-update.md) for the detailed rules.

## Supported training engines

![One interface, multiple training engines — concept illustration](assets/readme/next-trainer-multi-engine.png)

**Kohya · Anima Fast · Musubi · AI Toolkit · DiffSynth-Studio · MOSS (anima_lora)**

Install engines from **Settings → Training engines**, then select the appropriate engine on the training page. After upgrading from 3.1.1 or older, install Kohya once before running Kohya training. Available engines depend on your trainer version; not every model or feature supported upstream is integrated here.

For Qwen-Image-2.1, select **DiffSynth-Studio → LoRA**, then choose **Text-to-image** or **Edit**. Edit currently requires batch size 1 and can use gradient accumulation for a larger effective batch.

For MOSS-Image LoRA, use **Kohya** (recommended and selected by default). **MOSS (anima_lora)** remains available as a secondary engine.

## Supported models

![Supported models — concept illustration, not model output samples](assets/readme/next-trainer-models.png)

**MOSS-Image · Qwen-Image-2.1 · Anima · SD 1.5 · SDXL · Flux · FLUX.2 Klein · Krea 2 · Ideogram 4**

Training targets, hardware requirements, and optional engine installation vary by model. See the training tutorials below.

### Model / engine compatibility

✅ = an integrated LoRA entry; — = no integrated entry. This table follows this branch's training modules, not the full capabilities of upstream engines. Model variants and hardware requirements still depend on the selected engine.

| Model | Kohya | Anima Fast | Musubi | AI Toolkit | DiffSynth-Studio | MOSS (anima_lora) |
| --- | :---: | :---: | :---: | :---: | :---: | :---: |
| MOSS-Image | ✅ | — | — | — | — | ✅ |
| Qwen-Image-2.1 | — | — | — | ✅ | ✅ | — |
| Krea 2 | — | — | ✅ | ✅ | — | — |
| Anima | ✅ | ✅ | — | ✅ | — | — |
| FLUX.2 Klein | — | — | — | ✅ | — | — |
| Ideogram 4 | — | — | ✅ | ✅ | — | — |
| Flux | ✅ | — | — | ✅ | — | — |
| SDXL | ✅ | — | — | ✅ | — | — |
| SD 1.5 | ✅ | — | — | ✅ | — | — |

Kohya also provides full fine-tuning entries for Anima, SDXL, and SD 1.5. MOSS-Image defaults to Kohya; `MOSS (anima_lora)` is an alternative. Lumina has a Kohya LoRA entry accessible via `?model=lumina`, but is hidden from the normal model picker.

The illustrations above are conceptual; their artwork is not a benchmark or a sample generated by each labelled model.

## Training tutorials

- [MOSS-Image](docs/MOSS.md)
- [Qwen-Image-2.1](docs/diffsynth.md)
- [Anima](docs/anima-training.md)
- [Anima Fast](docs/anima-fast.md)
- [Krea 2 (Linux / multi-GPU)](docs/krea2-linux-multigpu.md)
- [Ideogram 4 (Musubi)](docs/ideogram4-musubi.md)
- [TOML / CLI](docs/cli-args.md)

[Interface tour](docs/interface-tour.md) · [Tagger model setup](docs/tagger-models.md) · [Training monitor](docs/train-monitor.md) · [All documentation](docs/README.md)


---

[Documentation](docs/README.md) · [Report an issue](https://github.com/wochenlong/lora-scripts-next/issues) · [Credits](docs/credits.md) · [Contributors](CONTRIBUTORS.md)
