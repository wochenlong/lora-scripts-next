"""Independent musubi-tuner backend integration for lora-scripts-next.

Supported training types: Krea 2 LoRA (krea2-lora) and Ideogram 4 LoRA
(ideogram4-lora). TRAIN_TYPE stays the pack's primary/legacy type for callers
that only need one; multi-type callers should read manifest.TRAIN_TYPES.
"""

TRAIN_TYPE = "krea2-lora"
