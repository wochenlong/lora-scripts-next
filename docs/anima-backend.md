# Anima Backend Maintenance

Anima training is maintained against [`kohya-ss/sd-scripts`](https://github.com/kohya-ss/sd-scripts), not `WhitecrowAurora/lora-rescripts`.

The stable local launch paths are:

- **LoRA / 网络训练**：`scripts/dev/anima_train_network.py` → 上游 `anima_train_network.py`（`model_train_type`: `anima-lora` / `sd3-lora`）
- **全量微调**：`scripts/dev/anima_train.py` → 上游 `anima_train.py`（`model_train_type`: `anima-finetune`）

Both are compatibility wrappers. The training implementation is loaded from the pinned upstream sd-scripts source configured in `config/anima_backend.toml`.

Local code may adapt GUI/TOML fields before delegating to upstream. Local changes to upstream trainer behavior must be documented as patches with the upstream commit they apply to and the reason they cannot live in the wrapper or adapter.

## Ownership boundary

- Upstream-owned: Anima trainer internals, model utilities, `networks.lora_anima`, and shared sd-scripts training utilities.
- Local-owned: WebUI schema, `/api/run` train type routing, the wrapper entrypoint, config adaptation, local defaults, and launch orchestration.

## Sync checklist

1. Review upstream `kohya-ss/sd-scripts` Anima changes.
2. Update `config/anima_backend.toml` only after selecting a reviewed upstream commit.
3. Run adapter, wrapper, resolver, and routing tests.
4. Run a wrapper parser smoke test with an Anima TOML fixture.
5. If GPU and model files are available, run a minimal Anima training smoke test.

## Wrapper smoke test

The smoke mode verifies the local wrapper can be launched in the same script shape used by `accelerate`, can import the local `mikazuki` adapter package, can rewrite a GUI TOML file, can verify the pinned upstream commit, and can resolve the upstream `anima_train_network.py` entrypoint. It stops before importing heavy training dependencies such as PyTorch.

```bash
ANIMA_BACKEND_WRAPPER_SMOKE=1 python3 scripts/dev/anima_train_network.py --config_file path/to/anima-lora.toml
ANIMA_BACKEND_WRAPPER_SMOKE=1 python3 scripts/dev/anima_train.py --config_file path/to/anima-finetune.toml
```

Expected output includes:

```text
Anima backend wrapper smoke OK: .../vendor/sd-scripts/anima_train_network.py
Anima backend wrapper smoke OK: .../vendor/sd-scripts/anima_train.py
```
