# Learning rate selection

- Version: `2026-08-29`
- Scope: starting `learning_rate` magnitude, scheduler and warmup choices for SD 1.5 / SDXL / Anima LoRA; adaptive-optimizer special cases; over/under-fit signals.
- Evidence status: layer 1 (publicly disclosed defaults) + layer 2 (observed local runs, see `model-families/anima-lora-parameter-baseline.md` and `model-families/anima-character-case-v1.md`) + inference where marked.
- Aliases / 检索关键词: 学习率, lr, learning_rate, unet_lr, text_encoder_lr, lr_scheduler, 预热, warmup

## Starting magnitudes (discovery defaults, tune to dataset size)

| Family | Typical start | Notes |
|---|---|---|
| SD 1.5 LoRA | `learning_rate = 1e-4` | common community start (layer 1) |
| SDXL LoRA | `1e-5` … `5e-5` | more divergence-sensitive than 1.5; on failure halve lr first (layer 1) |
| Anima character LoRA | `learning_rate = 3e-5` (unet) | observed in two real local runs (anonymized v1/v2 character runs, layer 2), with `text_encoder_lr = 0` (UNet-only) |

- unet/text-encoder split: text encoder usually runs lower than unet (e.g. `5e-5`) or is frozen (`0`).
- Small datasets (tens of images): prefer the low end; large well-regularized sets tolerate more.

## Scheduler and warmup

- `cosine` or `constant` are the usual picks; `cosine_with_restarts` (both observed Anima runs used 2 cycles) helps read plateau behaviour across restarts.
- Warmup ≈ 5–10 % of total steps stabilises the opening, especially at high lr (observed runs used 50–100 steps).

## Adaptive optimizers special case

- D-Adaptation / Prodigy style optimizers typically ignore or force the nominal lr (often pinned to 1) and self-tune; pair with `constant` scheduler and tune their own coefficient (e.g. `d_coef`) instead of conventional lr folklore.
- Before assuming the lr you typed is the lr used, check the normalized fields returned by `training_config_validate` — normalization is authoritative.

## Over/under-fit signals

- Output matches training images almost immediately but generalises poorly → lr too high or too many steps; reduce lr first (also see `training/curve-reading-guide.md`).
- Almost nothing learned after the planned budget → lr too low, steps too few, or captioning problems (also see `errors/common-errors.md`).

> These are starting points, not guarantees. Popularity of a value is discovery evidence only, never proof.
