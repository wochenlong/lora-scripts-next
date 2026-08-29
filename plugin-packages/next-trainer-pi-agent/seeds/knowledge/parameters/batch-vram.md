# Batch size, VRAM and exposure budget

- Version: `2026-08-29`
- Scope: what to trade when VRAM is short; batch/lr linkage; the total-exposure accounting; cache switches and their conflicts.
- Evidence status: layer 1 (general practice) + project contract for engine-specific cache rules (see `engines/anima-fast-vs-standard.md`) + inference where marked.
- Aliases / 检索关键词: 显存, 爆显存, OOM, vram, batch, batch_size, train_batch_size, gradient_checkpointing, cache_latents, gradient_accumulation, 步数, epochs

## Order of trades when VRAM is short

1. `gradient_checkpointing = true` — time for memory, almost always worth it.
2. `cache_latents` (+ `cache_latents_to_disk`) — saves VRAM and speeds up runs, **but conflicts with on-the-fly image augmentation** (e.g. colour augmentation / random crop). The authoritative conflict list is what `training_config_validate` reports; trust it over memory.
3. Lower `resolution`, or rely on bucketing instead of forcing a large fixed resolution.
4. Only then reduce `train_batch_size` (use `gradient_accumulation_steps` to keep effective batch when throughput matters).

## Batch ↔ lr ↔ exposure accounting

- Doubling batch permits a modest lr raise (linear-scaling rule is a starting heuristic, not law).
- The quantity to reason about is total exposure ≈ `batch × steps × repeats` (or epochs); keep it in the sane band when changing any factor. Observed reference: a ~100-image character set at 32–36 epochs × batch 2 × grad-accum 2 is already a **high** per-image exposure (layer 2) — see `training/curve-reading-guide.md` for choosing checkpoints instead of "final epoch".

## Other VRAM consumers

- Training the text encoder costs noticeably more than UNet-only; `text_encoder_lr = 0` + `network_train_unet_only = true` is the cheap default observed for characters (layer 2).
- `full_fp16` / `full_bf16` and fp8 base switches save memory with higher numerical risk — last resorts on small cards.
- `cache_text_encoder_outputs` frees encoder-forward memory but is incompatible with caption-shuffling schemes that need the encoder at train time; again, `training_config_validate` output wins.
