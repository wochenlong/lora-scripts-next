# Anima standard vs Anima Fast engine differences

- Version: `2026-08-29`
- Scope: what changes when the same Anima LoRA intent moves between the standard `anima-lora` page and the `anima-lora-fast` page (plugin-based fast backend), and which fields belong to which engine.
- Evidence status: project contract — shipped presets (`config/presets/anima-*.toml`), autosave config shape, bundled environment constraint files (`config/anima_fast_environment/`). No causal benchmarks here; layer 1 for mechanics.
- Aliases / 检索关键词: anima fast, 快速, 插件, torch_compile, compile, flash, automagic, AdamW8bit, skip_cache_check, 引擎差异, dataset_config

## Same intent, different page

Both pages train Anima character/style LoRAs (`networks.lora_anima`, same base triple: anima-base + qwen3-0.6B + qwen_image_vae). The Fast engine is a different execution backend, so **the field vocabulary is not identical** — a draft is always validated against its own `pageTrainType`.

## Contract differences (from shipped presets and autosave shape)

| Aspect | anima-lora (standard) | anima-lora-fast |
|---|---|---|
| Automagic optimizer | available (shipped default preset uses it) | **not supported**; shipped preset uses `optimizer_type = "AdamW8bit"` instead |
| Latents/TE caching | presets enable `cache_latents(_to_disk)`, `cache_text_encoder_outputs(_to_disk)` | shipped preset sets all caches **false** and `skip_cache_check = true` |
| Compile knobs | — | `torch_compile`, `compile_mode = "blocks"`, `dynamo_backend = "inductor"`, `static_token_count` (preset: 4096), `attn_mode = "flash"` |
| Dataset wiring | single training TOML | training TOML carries `dataset_config = "<path>"`; the dataset file has its own `[[datasets]]` structure (`resolution`, `batch_size`, `enable_bucket`, `validation_split_num`, `validation_seed`, `subsets` with `num_repeats`, `recursive`) |
| Environment | main app environment | separate pinned environment constraint files under `config/anima_fast_environment/` (CUDA-specific) |

## Practical rules

- Do not copy cache settings between engines: a standard-page habit (`cache_latents = true`) can be wrong on the fast page; the fast preset's stance is caches off + `skip_cache_check = true`.
- Do not propose `Automagic` for a fast-page draft; propose `AdamW8bit` (preset default) or an optimizer the validator accepts for that page.
- Field-level questions ("does this key exist on the fast page?") are settled by `training_config_validate` with `pageTrainType = "anima-lora-fast"` — not by this document.
- lr magnitude for anima does not automatically carry between engines; re-check the normalized draft.
