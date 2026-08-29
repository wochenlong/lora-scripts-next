# Anima LoRA parameter baseline

- Version: `2026-08-29`
- Scope: Anima base (`anima-base-V1.0.safetensors`, Qwen-Image-VAE + Qwen3-0.6B text encoder) character/style LoRA.
- Evidence status: **real local training run**（发布脱敏：run 名以 `oc_char_v2_anima_char` 代称，机器路径未收录；参数保持真实观察值）— started 2026-08-16, 97-image character dataset, 36 epochs, per-epoch checkpoints. This is a local project observation, not a causal claim.

## Parameters of the reference run

| Group | Field | Value |
|---|---|---|
| Model | pretrained / vae / qwen3 | anima-base-V1.0 / qwen_image_vae / qwen_3_06b_base |
| Model | qwen3_max_token_length, t5_max_token_length | 512 / 512 |
| Flow | timestep_sampling, discrete_flow_shift, weighting_scheme | shift / 3 / uniform |
| Data | resolution, enable_bucket, min/max bucket | 1024×1024, bucket 512–2048 step 64 |
| Data | cache_latents (to disk), caption_dropout / tag_dropout | true(true) / 0.02 / 0.05 |
| Optim | optimizer, lr (unet-only), scheduler | CAME / 3e-5 / cosine_with_restarts (2 cycles, 50 warmup) |
| Optim | text_encoder_lr, network_train_unet_only | 0 (frozen) / true |
| Network | module, dim, alpha, dropout | networks.lora_anima / 32 / 24 / 0.05 |
| Loop | epochs, batch, grad-accum, grad-ckpt | 36 / 2 / 2 / true |
| Loop | save_every_n_epochs, precision | 1 / bf16 |
| Preview | sample at 1024, cfg 4, 40 steps euler, every 4 epochs | fixed prompt + seed 42 |
| Log | tensorboard logging_dir | per-run directory |

## Observations from the run

- Checkpoints saved every epoch (`-0000NN.safetensors`, ~92MB each); TensorBoard scalars under `logs/<run>/network_train`.
- 36 epochs over a ~100-image set is a **high** exposure per image — the reference run shows why checkpoint comparison (not "final epoch") is the right selection method.
- UNet-only training with frozen text encoder was used for the character run; keep the text encoder frozen unless style transfer is the goal.
- Preview samples (fixed prompt + seed, every 4 epochs) are the built-in overfitting monitor for this family.

## Guidelines

- Start conservative: dim 16–32, alpha ≈ 0.75×dim, unet LR 1e-5–3e-5, 8–20 epochs for a first pass on a ~100-image set; scale epochs only with validation/preview evidence.
- Compare checkpoints under one fixed protocol (same prompts, seed, sampler, steps) before choosing a release candidate.
- Do not import Civitai popularity as evidence for Anima parameter choices; Anima is a niche family with little public `trainingDetails`.
