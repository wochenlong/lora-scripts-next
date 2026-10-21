<p align="center">
  <img src="frontend/src/assets/moss-kohaku-poster-16-9.svg" alt="Next Trainer KohakuMoss Edition" width="760" />
</p>

<p align="center">
  <strong>A dedicated MOSS-Image × KohakuMossTrainer workbench</strong><br />
  Local LyCORIS training for MOSS-Image Base and SFT.
</p>

<p align="center">
  <a href="docs/getting-started.en.md">Quick start</a> ·
  <a href="docs/MOSS.md">Training guide (Chinese)</a> ·
  <a href="docs/team/kohaku-moss-portable-build.md">Portable build plan</a> ·
  <a href="README-zh.md">简体中文</a>
</p>

> [!IMPORTANT]
> `KohakuMoss` is a standalone MOSS-specific branch. It is not the general-purpose `main` or `dev` trainer and is not intended to merge back into `dev`.

## What this edition provides

- MOSS-Image Base / SFT as the sole model family.
- KohakuMossTrainer and the native `kogine` CLI as the default training path.
- LoKr, LoRA, LoCon, LoHa, OFT, BOFT, GLoRA, DyLoRA, T-LoRA, and other LyCORIS algorithms.
- Comfy-style split files or a native Hugging Face model directory.
- Both LyCORIS and ComfyUI weight exports.
- An isolated Python 3.12, CUDA PyTorch, KohakuMoss, KohakuEngine, and LyCORIS environment.

Kohya, Musubi, Anima Fast, AI Toolkit, and DiffSynth training environments are intentionally excluded. Use `main` or `dev` for the multi-model product.

## Windows portable package

The dedicated portable package must include the complete KohakuMossTrainer runtime. The roughly 27 GB MOSS model is downloaded separately.

**Baidu Netdisk:** [Next-Trainer-v3.3.0-KohakuMoss-Portable-preview.1.7z](https://pan.baidu.com/s/1owF17doNHaccZhHwfoStrw?pwd=uqsh) (code: `uqsh`)

1. Extract the package and run `启动.bat`.
2. Run `tools\Download-MOSS-Model.bat` to download training-compatible Base BF16 files from ModelScope.
3. Put images and matching `.txt` captions in `Next-Trainer\train\moss-image\`.
4. Open Training; **MOSS-Image / KohakuMossTrainer** is selected by default.
5. Run a 50-step smoke test before a full training run.

See the [MOSS-Image training guide](docs/MOSS.md) for layouts, parameters, memory profiles, and troubleshooting.

## Run from source

```powershell
git clone --branch KohakuMoss https://github.com/wochenlong/lora-scripts-next.git
cd lora-scripts-next
.\run_gui.bat
```

Source users still install the isolated KohakuMossTrainer runtime from the training page. The dedicated portable build must bundle it.

## Upstream projects

Training is powered by [KohakuBlueleaf/KohakuMossTrainer](https://github.com/KohakuBlueleaf/KohakuMossTrainer) and [KohakuBlueleaf/LyCORIS](https://github.com/KohakuBlueleaf/LyCORIS). MOSS-Image is published by the OpenMOSS team.

---

[Documentation](docs/README.md) · [Report an issue](https://github.com/wochenlong/lora-scripts-next/issues) · [Credits](docs/credits.md)
