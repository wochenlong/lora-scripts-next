"""Validated Toolkit input contracts. Keep generated schemas in sync via schema.py."""

MODELS = {
    "sdxl": {"label": "SDXL", "arch": "sdxl", "modes": ["model_directory", "single_file"],
             "components": ["unet", "text_encoder", "text_encoder_2", "vae"],
             "tokenizers": ["tokenizer", "tokenizer_2"], "scheduler": "ddpm", "quantization": False},
    "flux": {"label": "Flux.1 Dev", "arch": "flux", "modes": ["model_directory"],
             "components": ["transformer", "text_encoder", "text_encoder_2", "vae"],
             "tokenizers": ["tokenizer", "tokenizer_2"]},
    "klein-4b": {"label": "Klein 4B", "family": "klein", "arch": "flux2_klein_4b",
                 "modes": ["model_directory", "single_file"], "editing": True,
                 "dit_filename": "flux-2-klein-base-4b.safetensors", "te_hidden_size": 2560,
                 "text_encoder": "Qwen/Qwen3-4B", "variants": ["base", "distilled"]},
    "klein-9b": {"label": "Klein 9B", "family": "klein", "arch": "flux2_klein_9b",
                 "modes": ["model_directory", "single_file"], "editing": True,
                 "dit_filename": "flux-2-klein-base-9b.safetensors", "te_hidden_size": 4096,
                 "text_encoder": "Qwen/Qwen3-8B", "variants": ["base", "distilled"]},
    "krea2": {"label": "Krea 2", "arch": "krea2", "modes": ["model_directory", "single_file"],
              "dit_filename": "krea2.safetensors", "text_encoder": "Qwen3-VL", "variants": ["raw"]},
    "anima": {"label": "Anima", "arch": "anima", "modes": ["model_directory"],
              "sample_multiple": 32,
              "components": ["transformer", "text_encoder", "text_conditioner", "vae"],
              "tokenizers": ["tokenizer", "t5_tokenizer"]},
    "qwen-image-21": {"label": "Qwen Image 2.1", "arch": "qwen_image_2",
                      "sample_multiple": 32,
                      "modes": ["model_directory", "comfyui_files"], "editing": True,
                      "components": ["transformer", "text_encoder", "vae"], "tokenizers": ["processor"]},
}

TRAIN_TYPES = {
    (f"{key}-lora" if key.startswith("klein-") else f"ai-toolkit-{key}-lora"): key
    for key in MODELS
}


def schema_name(variant):
    return "klein-lora" if variant.startswith("klein-") else f"ai-toolkit-{variant}-lora"


def family(variant):
    return MODELS[variant].get("family", variant)


def train_type(variant):
    return next(key for key, value in TRAIN_TYPES.items() if value == variant)
