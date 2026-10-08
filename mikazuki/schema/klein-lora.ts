SHARED_SCHEMAS.AI_TOOLKIT({
  "label": "Klein 4B",
  "family": "klein",
  "arch": "flux2_klein_4b",
  "modes": [
    "model_directory",
    "single_file"
  ],
  "editing": true,
  "dit_filename": "flux-2-klein-base-4b.safetensors",
  "te_hidden_size": 2560,
  "text_encoder": "Qwen/Qwen3-4B",
  "variants": [
    "base",
    "distilled"
  ],
  "train_types": [
    "klein-4b-lora",
    "klein-9b-lora"
  ]
})
