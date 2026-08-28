# SDXL LoRA parameter baseline

- Version: `2026-08-29`
- Scope: SDXL 1.0 character/style LoRA.
- Evidence status: **heuristic** — widely used community starting points for small (tens to low hundreds of images) character sets. Not measured in this project; treat as a starting box to sweep, not a rule.

## Conservative starting box

| Field | Start | Notes |
|---|---|---|
| network dim / alpha | 16 / 8 (or dim/2) | raise dim only with validation evidence of underfitting |
| learning rate (unet) | 1e-4 | 5e-5 if the set is very small or overfits fast |
| learning rate (text encoder) | 5e-5 or frozen | freeze TE first for pure character identity |
| resolution / buckets | 1024 with 512–1024 buckets | SDXL is bucket-tolerant; keep no-upscale for mixed sources |
| steps | 1500–3000 for ~100 images | ≈ 10–20 epochs; stop on validation saturation |
| batch / grad-accum | 1 / 2–4 | effective batch 2–4 |
| optimizer / scheduler | AdamW8bit or Prodigy / cosine (warmup 5–10%) | |
| save cadence | every 250–500 steps or per epoch | comparison needs several candidates |
| clip skip | 1–2 | |

## Failure modes to check

- Overfitting: train loss keeps falling while fixed-prompt validation/preview stops improving or degrades (hands, hair, background bleed).
- Underfitting: identity not stable across poses at the last checkpoint; raise steps/dim before lowering LR.
- LR too high: loss spikes or oscillation; step down 2–3×.
