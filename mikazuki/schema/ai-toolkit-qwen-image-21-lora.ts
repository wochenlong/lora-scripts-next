SHARED_SCHEMAS.AI_TOOLKIT({
  "label": "Qwen Image 2.1",
  "arch": "qwen_image_2",
  "sample_multiple": 32,
  "modes": [
    "model_directory",
    "comfyui_files"
  ],
  "editing": true,
  "components": [
    "transformer",
    "text_encoder",
    "vae"
  ],
  "tokenizers": [
    "processor"
  ],
  "family": "qwen-image-21",
  "train_types": [
    "ai-toolkit-qwen-image-21-lora"
  ]
})
