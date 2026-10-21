# KohakuMoss Edition Quick Start

[Home](../README.md) · [Training guide (Chinese)](MOSS.md) · [中文](getting-started.md)

> `KohakuMoss` is a standalone MOSS-Image edition, not the general-purpose `main` or `dev` product.

## Windows Portable Package

Windows 10/11, an NVIDIA GPU, and sufficient local storage are required. The runtime is bundled; the MOSS model needs roughly 27 GB separately.

1. Extract the archive, keeping at least 60 GB of free space.
2. Run `启动.bat`; the UI normally opens at `http://127.0.0.1:28000`.
3. Training must open directly on **MOSS-Image / KohakuMossTrainer / LoRA** with the engine ready.
4. Run `tools\Download-MOSS-Model.bat` and wait for the ModelScope download and SHA256 checks.
5. Put each image and its matching UTF-8 `.txt` caption in `Next-Trainer\train\moss-image\`.
6. Run a 50-step smoke test before full training.

If the portable package asks to install KohakuMossTrainer, the runtime was not bundled correctly.

## From Source

```powershell
git clone --branch KohakuMoss https://github.com/wochenlong/lora-scripts-next.git
cd lora-scripts-next
.\run_gui.bat
```

Install KohakuMossTrainer once from the Training page. It creates an isolated Python 3.12 runtime under `extensions/kohaku-moss/`.

## Updates

Portable updates must remain on the `KohakuMoss` branch. Do not overwrite this edition with a general `main` / `dev` release or copy Kohya, Musubi, or Anima Fast runtimes into it.

[Training guide](MOSS.md) · [Documentation](README.md) · [Report an issue](https://github.com/wochenlong/lora-scripts-next/issues)
