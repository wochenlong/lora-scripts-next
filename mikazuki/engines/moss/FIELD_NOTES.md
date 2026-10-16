# MOSS integration field notes

This integration exposes only **MOSS-Image Base/SFT LoRA** through engine `moss`,
model `moss-image`, and schema/train type `moss-image-lora`. Validation described
here is CPU/header-only or mocked unless explicitly stated otherwise. It does not
establish real installation, GPU training, inference, or trained-LoRA compatibility.
User-facing setup and limitations: [docs/MOSS.md](../../../docs/MOSS.md).

## Source of truth

- Source: [`sorryhyun/anima_lora`](https://github.com/sorryhyun/anima_lora), branch
  `moss_lora`, exact commit `1df6181fcea45926932fb63d5924f6f3dfd7c7d0`.
- Native request contract: [library/moss/requests.py](https://github.com/sorryhyun/anima_lora/blob/1df6181fcea45926932fb63d5924f6f3dfd7c7d0/library/moss/requests.py).
- Architecture/invariants: [library/moss/CLAUDE.md](https://github.com/sorryhyun/anima_lora/blob/1df6181fcea45926932fb63d5924f6f3dfd7c7d0/library/moss/CLAUDE.md).
- Upstream user notes: [docs/experimental/moss_lora.md](https://github.com/sorryhyun/anima_lora/blob/1df6181fcea45926932fb63d5924f6f3dfd7c7d0/docs/experimental/moss_lora.md).
- The engine's `manifest.py` declares no source patches. Training uses the pinned
  `scripts.moss.cache` and `scripts.moss.train` entry points, not Anima's config
  chain, a copied model, or a replacement training loop.

MOSS uses a 42-block single-stream DiT, Qwen3.5-9B text embeddings at natural
length, and packed FLUX.2 VAE latents. These invariants differ from Anima. The
shared block swapper requires two resident blocks: manual `blocks_to_swap` is
limited to 40, not 41 or 42.

## Input and adaptation boundaries

`model_dir` is the parent of `MOSS-Image-Base/` and optionally
`MOSS-Image-SFT/`. SFT supplies its transformer while Base supplies text encoder,
VAE and tokenizer. Existing-cache mode can omit preprocessing components that
are not needed; positive caption dropout still requires the native text encoder
and tokenizer. This is not a flat Comfy-file loader or an automatic conversion
path. Quantized weights and remapped text-only Qwen prefixes are rejected.

The model preflight checks native configs, exact transformer keys/shapes,
required `language_model.*` text keys and embedding shape, tokenizer chat
configuration, selected critical VAE stages, shard-index consistency, permitted
dtypes and tensor byte ranges. It never reads tensor payloads. Text/VAE checks
are structural sentinels, not a complete value-level loader audit.

`adapter.py` retains upstream request names and emits BooleanOptionalAction flags
including `--no-compile` and `--no-grad_checkpointing`. Necessary UI adaptations:

- `cache_dir` → cache request `out` and train request `cache`.
- `overwrite_cache` → cache request `overwrite`.
- `output_dir` + `output_name` → train request `output`.
- `run_preprocess` controls the two-stage coordinator; `gpu_ids` selects at most
  one device through the launcher, not the MOSS request parser.
- Relative paths resolve against the Next Trainer project root.

There are no Kohya network/optimizer conversions. The frontend's shared schema
serializer, TOML preview/export, config import and `/api/run` are reused.
Compile defaults to false here rather than the pinned upstream's true; Windows
compile is rejected. Native defaults otherwise remain in `adapter.py` and the
schema. Batch size is fixed at one; no distributed training, repeats, resume,
LoRA warm-start, full fine-tuning or in-training previews are exposed.

Caches use native file names/shapes plus `.next-moss-cache.json` provenance.
The identity includes frozen-asset paths, sizes/mtimes and cache settings; it is
not a full cryptographic hash of every model tensor. Changed/unknown caches,
orphans, duplicate dimensions, malformed pairs and stale source/caption metadata
are checked. External cache-only mode cannot prove caption/model provenance;
its warning is intentional. Unknown/changed empty-prompt provenance requires a
fresh cache directory. `save_crops` cannot write beneath the input dataset.

Output reservation covers final `.safetensors`, `.json` reports, `_eN.safetensors`
and overlapping active/queued MOSS task names. This prevents silent overwrite;
it is not a resume mechanism. Task insights use the native stdout loss/progress
format and do not scan unrelated TensorBoard/previews.

## Isolated one-click environment

Owned paths: `extensions/moss/source`, `.python`, `.venv`, `install_state.json`.
`LORA_ENABLE_MOSS=0` disables the engine; default is enabled. The installer clones
`moss_lora` then checks out the exact commit, creating a managed Python 3.13 venv.
Important dependency pins from the upstream stack are:

- `torch==2.14.1+cu132`, `torchvision==0.29.1+cu132`.
- `transformers==5.16.1`, `accelerate==1.13.0`, `safetensors==0.8.0`.
- Diffusers commit `80c7ed262aeffbeb43ef13ae04baeb9b84515a69`.
- anime-tools commit `53af580c84fab07372e852b04a6f1880d2ebab4d`, installed with
  `--no-deps`; source is editable-installed with `--no-deps` too.
- Windows adds `triton-windows==3.8.0.post29`; there is no optional flash-attn build.

See `environment.py` for the complete dependency closure; some utility packages
retain upstream ranges, so this is not a fully locked wheel set. The full upstream
project also contains unrelated GUI/curation/Comfy dependencies: do not replace
this install plan with a wholesale `uv sync`.

Environment audit verifies the pin, tracked-source cleanliness, interpreter/venv
ownership, key package versions, actual cache/train imports, CUDA 13.2 and BF16
availability. Ready state requires a successful audit and a current fingerprint;
source/package metadata drift, corrupt state and interrupted installs are handled.
Submission rechecks readiness. Training starts with isolated Python flags
`-E -s -u -X utf8`, sanitized environment and offline Hugging Face flags; it does
not download missing model assets. Repair recreates only the three managed runtime
directories; uninstall removes the extension root. Keep user assets outside it.

Installation, recovery, cancellation and locking are tested with injected process
boundaries. They have not been validated by an actual dependency installation on
Linux or Windows in this change.

## Official metadata fixture provenance

Model metadata was retrieved from OpenMOSS-Team/MOSS-Image-Base on 2026-10-16.
HTTP resolution pinned it to repository revision
`5f40f07a304541840b6019d2d34d30f966756787`. Sources include:

- [transformer/config.json](https://huggingface.co/OpenMOSS-Team/MOSS-Image-Base/blob/5f40f07a304541840b6019d2d34d30f966756787/transformer/config.json)
  and the [transformer index](https://huggingface.co/OpenMOSS-Team/MOSS-Image-Base/blob/5f40f07a304541840b6019d2d34d30f966756787/transformer/diffusion_pytorch_model.safetensors.index.json).
- [text_encoder/config.json](https://huggingface.co/OpenMOSS-Team/MOSS-Image-Base/blob/5f40f07a304541840b6019d2d34d30f966756787/text_encoder/config.json)
  and the [text encoder index](https://huggingface.co/OpenMOSS-Team/MOSS-Image-Base/blob/5f40f07a304541840b6019d2d34d30f966756787/text_encoder/model.safetensors.index.json).
- [vae/config.json](https://huggingface.co/OpenMOSS-Team/MOSS-Image-Base/blob/5f40f07a304541840b6019d2d34d30f966756787/vae/config.json)
  and [tokenizer/tokenizer_config.json](https://huggingface.co/OpenMOSS-Team/MOSS-Image-Base/blob/5f40f07a304541840b6019d2d34d30f966756787/tokenizer/tokenizer_config.json).

`tests/fixtures/moss/provenance.json` records URLs, resolved revisions, timestamps,
HTTP headers and hashes of normalized metadata JSON. Retained config/key fixtures
are under `tests/fixtures/moss/`: 463 transformer index keys and 759 full text
encoder index keys; the required language-model subset is compared independently.
No actual model tensor payloads were downloaded. VAE shape sentinels are derived
from pinned Diffusers and config, not claimed as a complete official VAE header.

Backend fixtures create sparse synthetic safetensors files with structural headers
and placeholder byte ranges. These are not loadable evidence of correct weights
or numerical model behavior. Test tokenizer contents are also synthetic.

## Reproduce lightweight verification

Use an existing Next Trainer development/test environment with pytest, Pillow and
backend test dependencies; these commands do not install the MOSS environment.
A sparse-file-capable filesystem avoids physically allocating synthetic tensor
payload sizes. From the project root:

```sh
python -m pytest -q tests/test_moss_engine.py tests/test_moss_environment.py tests/test_moss_task_insights.py
```

To also exercise the real, torch-free parser from a separately available checkout:

```sh
MOSS_UPSTREAM_SOURCE=/path/to/pinned/anima_lora \
  python -m pytest -q tests/test_moss_engine.py -k actual_pinned_upstream_parser
```

That test checks the exact source commit, uses the real `CacheRequest` /
`TrainRequest` dataclasses and argparse round-trip, and stubs only the unrelated
weight-download catalog dependency. It asserts ML packages were not imported.
Without `MOSS_UPSTREAM_SOURCE`, this optional test is explicitly skipped.

With Node 22 and existing frontend dependencies:

```sh
cd frontend
npm run typecheck
npm run lint
npm test -- --run src/training/moss.test.ts src/api/moss.test.ts src/pages/MossGatePage.test.ts src/pages/TrainingPage.test.ts src/components/TrainingSelector.test.ts src/pages/EnginesSettingsPage.test.ts
```

`src/training/moss.test.ts` compares the actual schema → `serializeModel` →
`buildTrainingConfig` output against the shared 33-field
`tests/fixtures/moss/form-submission.json`. The backend test consumes that exact
fixture through real FastAPI `/api/engines/moss/preflight`, `/dry-run` and
`/api/run`, substituting runtime readiness and task creation/submission boundaries.
Local input validation and persisted native cache/train config remain real. No
training subprocess is spawned. Mock SSE tests cover install progress, cancellation,
repeat clicks, unmount cleanup, disabled states and preflight rejection.

For read-only inspection with actual local inputs, POST the flat form JSON to
`/api/engines/moss/dry-run`. It reports `training_started=false`, adapted requests,
planned commands and header checks without requiring an installed runtime.
`/preflight` additionally requires the real environment audit. Neither response
establishes training success.

## Remaining acceptance

- Rendered desktop/mobile browser inspection is pending. The available cloud
  command/browser boundary prevented opening the local mock app; automated DOM
  component tests and a successful build do not substitute for screenshot review.

- Real one-click dependency installation, retry/repair/uninstall and process-tree
  cancellation on supported Linux and Windows hosts.
- Full native Base and SFT model loading, text/VAE caching, actual single-GPU
  LoRA training and save/report verification, including memory/block-swap behavior.
- Numerical validity and training quality; practical VRAM/time requirements.
- Reload a real exported LoRA in the intended inference stack, including native
  ComfyUI if desired. No trained-LoRA or synthetic Comfy loader compatibility
  test has been performed for MOSS here.

Upstream's reported runs are upstream evidence only; they are not Next Trainer
acceptance results. Keep these limits explicit when reporting this integration.
