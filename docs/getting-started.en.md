# Quick Start

[Home](../README.md) · [Documentation](README.md) · [中文](getting-started.md)

## Choose a Version

The 3.1.0 source release is on `main`. The published portable release is still **v3.0.0** and does not include the 3.1.0 updates. Check [Releases](https://github.com/wochenlong/lora-scripts-next/releases) for 3.1.0 archive availability.

## Windows Portable

Requires Windows 10/11 64-bit and an NVIDIA GPU; RTX 20 series or newer is recommended. VRAM requirements depend on the model, training target, and configuration. Check the relevant [training guide](README.md#training--训练) first.

1. Download a formal package from [GitHub Releases](https://github.com/wochenlong/lora-scripts-next/releases) or a mirror linked in the release notes.
2. Extract to a path without spaces or non-ASCII characters. Download all parts of a split archive before extracting.
3. Use `run_gui.bat` for lite packages; for other packages, follow the included launcher instructions (for example, `启动.bat`).
4. Complete environment setup as prompted, then open the address printed in the terminal, normally `http://127.0.0.1:28000`.
5. Confirm the sidebar version matches your download before preparing models and datasets.

### Package Selection

| Package | Best suited for |
| --- | --- |
| lite | Smaller download; dependencies are prepared online on first launch |
| Kohya | A preinstalled Kohya training environment |
| Musubi / Kohya-Musubi | Musubi or dual-engine environments; availability depends on release assets |

Anima Fast uses an optional, separate environment and is not preinstalled in these packages. In the 3.1.0 workspace, install engines from Settings; see [Anima Fast](anima-fast.md). Older archives may have a different interface.

Some archives retain the `SD-Trainer/` directory and older updater names for compatibility. Do not rename them.

## From Source

Install Git and Python 3.10. Initial setup needs internet access for dependencies; training also requires the appropriate models, dataset, and engine environment.

```sh
git clone https://github.com/wochenlong/lora-scripts-next.git
cd lora-scripts-next
```

Windows (PowerShell):

```powershell
.\run_gui.bat
```

Linux:

```sh
bash run_gui.sh
```

Use the address printed in the terminal. See [frontend development](../frontend/README.md), [repository layout](repo-layout.md), and [TOML / CLI](cli-args.md) for development and command-line workflows.

## Branches and Updates

| Branch | Purpose |
| --- | --- |
| `main` | Stable source release line, including 3.1.0 |
| `dev` | Next-version integration and acceptance; may contain unreleased changes |
| `legacy/v2.9.1` | Older UI baseline |

Portable users should follow formal Releases and included update instructions, without switching Git branches.

For source installations, check your branch with `git branch --show-current` and local changes with `git status`. Once local changes are handled, update the stable branch:

```sh
git switch main
git pull --ff-only
```

For next-version development, use `git fetch origin` and `git switch dev`. Do not force-reset a workspace containing changes you need to keep.

Import older TOML files through the training page, then review the model, engine, target, and generated configuration. Do not copy old browser storage directly into a new version.

## Next Steps

[Interface tour](interface-tour.md) · [Training guides](README.md#training--训练) · [Tagger models](tagger-models.md) · [Report an issue](README.md#help-and-credits--反馈与致谢)
