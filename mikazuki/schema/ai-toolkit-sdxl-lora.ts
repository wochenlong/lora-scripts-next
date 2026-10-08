SHARED_SCHEMAS.AI_TOOLKIT({
  "label": "SDXL",
  "arch": "sdxl",
  "modes": [
    "model_directory",
    "single_file"
  ],
  "components": [
    "unet",
    "text_encoder",
    "text_encoder_2",
    "vae"
  ],
  "tokenizers": [
    "tokenizer",
    "tokenizer_2"
  ],
  "scheduler": "ddpm",
  "quantization": false,
  "family": "sdxl",
  "train_types": [
    "ai-toolkit-sdxl-lora"
  ]
})
