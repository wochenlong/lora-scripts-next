# Qwen 2.1 structural fixtures

Only tensor names and shapes, read from the safetensors headers of
[Comfy-Org/Qwen-Image-2.1](https://huggingface.co/Comfy-Org/Qwen-Image-2.1) BF16 DiT,
Qwen3-VL-8B text encoder and VAE on 2026-09-21. No tensor values are included.

Tests create sparse files for header-only validation. Never load these sparse
fixtures as real model weights. Conversion value and LoRA patch tests use small,
separately generated tensors.
