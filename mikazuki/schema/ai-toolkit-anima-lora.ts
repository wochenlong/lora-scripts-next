SHARED_SCHEMAS.AI_TOOLKIT({
  "label": "Anima",
  "arch": "anima",
  "modes": [
    "model_directory"
  ],
  "sample_multiple": 32,
  "components": [
    "transformer",
    "text_encoder",
    "text_conditioner",
    "vae"
  ],
  "tokenizers": [
    "tokenizer",
    "t5_tokenizer"
  ],
  "family": "anima",
  "train_types": [
    "ai-toolkit-anima-lora"
  ]
})
