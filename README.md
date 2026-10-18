<p align="center">
  <img src="assets/readme/next-trainer-cover.png" alt="Next Trainer" width="720" />
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

![Qwen-Image-2.1 LoRA training with the DiffSynth engine in Next Trainer](assets/readme/vue3/02-training-qwen-image-21-diffsynth.png)

Train Qwen-Image-2.1 LoRA with the DiffSynth engine, with training configuration and TOML preview side by side. [Qwen-Image-2.1 beginner's guide (Chinese)](docs/diffsynth.md) · [Explore the workspace](docs/interface-tour.md).

## What's new in 3.2.0

- **Caption editor rebuilt:** the image wall leads, the editor panel opens with the selection; tag and free-text modes, batch operations and history.
- **Offline Chinese glosses:** a bundled Danbooru dictionary (~330k entries) with dictionary / local model / API sources; the dictionary works fully offline.
- **Settings restructure:** UI, Training Engines, API, Plugins, Advanced, About; the new **API** page holds shared endpoint and local-model configuration, network and download sources moved under Advanced.
- **Training task queue:** runs queue automatically, survives a service restart, and failed or stopped tasks can re-enter the queue with their original config.
- **MOSS-Image LoRA:** MOSS-Image training is available with Kohya as the recommended/default engine; the anima_lora runtime remains an optional secondary path. See the [MOSS-Image guide](docs/MOSS.md).
- **Ideogram 4 LoRA on Musubi:** FP8-only, non-commercial weights you fetch yourself (upstream still marks it experimental).
- **Fixes:** LoKr / LoHa / T-LoRA parameters on the Anima page are no longer reset when reloading or importing a config; the dataset-config preflight now rejects subsets that would be skipped silently.

[Full changelog](CHANGELOG.md) · [Qwen-Image-2.1 guide (Chinese)](docs/diffsynth.md) · [Anima Fast guide](docs/anima-fast.md)

## Supported training engines

**Kohya · Anima Fast · Musubi · AI Toolkit · DiffSynth-Studio · MOSS (anima_lora)**

Install engines from **Settings → Training engines**, then select the appropriate engine on the training page. After upgrading from 3.1.1 or older, install Kohya once before running Kohya training. Available engines depend on your trainer version; not every model or feature supported upstream is integrated here.

For Qwen-Image-2.1, select **DiffSynth-Studio → LoRA**, then choose **Text-to-image** or **Edit**. Edit currently requires batch size 1 and can use gradient accumulation for a larger effective batch.

For MOSS-Image LoRA, use **Kohya** (recommended and selected by default). **MOSS (anima_lora)** remains available as a secondary engine; setup and model layout details are in the [MOSS-Image guide](docs/MOSS.md).

## Supported models

**MOSS-Image · Qwen-Image-2.1 · Anima · SD 1.5 · SDXL · Flux · FLUX.2 Klein · Krea 2 · Ideogram 4**

Training targets, hardware requirements, and optional engine installation vary by model. See the [training guides](docs/README.md#training--训练).

## Get started

**Windows users:** [download a portable package](https://github.com/wochenlong/lora-scripts-next/releases), extract it, and use the included launcher. An NVIDIA GPU is required; see [setup and package selection](docs/getting-started.en.md).

**Release status:** 3.2.0 source is on `main`. Portable packages have their own release schedule; check the version and release notes on Releases. Older packages may not include DiffSynth or Qwen-Image-2.1 support.

For the 3.2.0 source version or Linux setup, follow [run from source](docs/getting-started.en.md#from-source).

Command-line runs use `scripts/cli/train_anima_by_toml.sh` and `scripts/cli/train_anima_fast_by_toml.sh` to submit Anima / Anima Fast configs; see the [CLI reference](docs/cli-args.md).

---

[Documentation](docs/README.md) · [Report an issue](https://github.com/wochenlong/lora-scripts-next/issues) · [Credits](docs/credits.md) · [Contributors](CONTRIBUTORS.md)
