# network_dim / network_alpha

- Version: `2026-08-29`
- Scope: what `network_dim` / `network_alpha` control, common tiers, project-observed values, capacity troubleshooting.
- Evidence status: layer 1 (LoRA mechanics are public) + layer 2 (project preset defaults and two real observed runs) + inference where marked.
- Aliases / 检索关键词: dim, alpha, network_dim, network_alpha, 秩, 维度, 容量, conv_dim, conv_alpha

## Roles

- `network_dim`: LoRA rank — capacity. Larger learns more detail, costs more (VRAM, file size, over-fit risk).
- `network_alpha`: scaling denominator; effective strength scales as `alpha / dim`. Common practice is `alpha = dim/2` … `alpha = dim`.
- To "make the LoRA hit harder" prefer inference weight first; do not blindly inflate dim.

## Tiers and observed values

- Style/concept: dim 8–32 usually suffices; characters (detail-heavy): dim 32–64 is common (layer 1).
- Project shipped presets start at `dim 16 / alpha 16` for anima-lora and anima-fast character pages (layer 2: `config/presets/anima-*-lora-character*.toml`).
- Real local character runs used `dim 32 / alpha 24` (see `model-families/anima-lora-parameter-baseline.md`, `model-families/anima-character-case-v1.md`).

## Troubleshooting

- Maxed-out dim still can't learn → almost never capacity first: check captioning quality and lr before touching dim.
- Model file unexpectedly large → check dim (and conv-side dimensions when a LyCORIS-style module is used; the resulting `network_args` encode them — verify the final shape via `training_config_validate` normalized output).

> Any dim/alpha pair must still pass `training_config_validate` for the target page; the schema is authoritative for field names, this document is for choosing values.
