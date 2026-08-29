# Common errors and configuration traps (quick reference)

- Version: `2026-08-29`
- Scope: high-frequency "what does this mean / what do I check next" items — model-type confusions, config conflicts, path mistakes, loss anomalies, dataset pairing.
- Evidence status: project contract + validator behaviour (layer 1/2 as noted); run again through the tools named below rather than answering from memory.
- Aliases / 检索关键词: 报错, 错误, 失败, error, nan, loss, v2, sdxl, oft, 路径, 数据集, 标注, trigger

## Discriminator traps (config level)

- `v2 = true` means Stable Diffusion **2.x**, **not** SDXL; SDXL needs its own page / `model_train_type` (`sdxl-lora`).
- `networks.oft` supports SDXL only — the validator rejects it on other pages.
- Known conflict pairs (the `training_config_validate` findings are authoritative, this is memory aid): latents caching × on-the-fly augmentation (colour aug / random crop); text-encoder-output caching × caption shuffling that needs the encoder; `noise_offset` × multires noise.

## Paths

- Every path in a training config points at the **machine that runs the trainer**, not the browser machine. Paths that do not exist simply fail — verify with `training_config_current` (resolve relative paths against the project root) before editing anything.
- Do not invent machine paths; if `training_config_current` has none and the user gave none, ask.

## Training-run signals

- `loss = nan` → usually lr too high, fp16 overflow, or corrupt data. Halve lr, check for broken images / empty captions, then compare curves (`training/curve-reading-guide.md`).
- loss stuck at 0 or flat → dataset likely not actually read: image/caption pairing, file extensions, directory layout. Run `dataset_inventory` first.
- all-grey / all-black preview images → VAE or aggressive precision settings; check the `vae` path and any `full_fp16`/fp8 switches.

## Dataset-level traps

- Captions must pair 1:1 with images by file name (`caption_extension`); images without captions act as unsupervised noise.
- Trigger word must appear stably in captions for character training (style training may not need one). Keep it in front (tagger `keep tokens`, see `captions/wd14-tagging-guide.md`).
- Wrong regularization categories quietly wash out the concept you are trying to learn.
- Tagger conflict actions are matched **exactly, lowercase**: only `ignore` leaves existing captions untouched — see `captions/wd14-tagging-guide.md` (the `Skip` trap).

## Before submitting anything

- Every draft goes through `training_config_validate` (schema + conflicts + engine preflight findings in one call); never present an unvalidated patch, and never auto-submit training (`training_config_commit` requires the explicit confirmation ticket).
