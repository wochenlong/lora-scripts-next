# Parameter evidence rules

- Version: `2026-08-26`
- Scope: all LoRA parameter recommendations.
- Evidence status: project contract.

Separate three layers in every answer:

1. Publicly disclosed facts, with a source path or URL.
2. Observed distributions, with sample size and missingness.
3. Model inference or a proposed experiment, clearly labelled as such.

Popularity is discovery evidence only. Missing `trainingDetails` stays unknown. A generated TOML draft must pass `training_config_validate`, normalization, preflight, semantic diff, and explicit user confirmation before import.
