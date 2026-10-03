# PR #399 Acceptance (2026-10-03)

## Scope

Reviewed PR head `927c7374f1cbc0fec988c279b81b4109b9054741`, integrated
`origin/dev` at `275c8884`, and tested the fixes on an isolated branch.
This report does not claim coverage of every model.

## Dev Integration

Following maintainer approval, the integration branch was synchronized with
dev `11a9cc0b` (including tag translation) without conflicts. Before merging,
the combined frontend passed `npm run check` with 297 tests and a successful
build; the AI Toolkit backend suite passed all 68 tests. The original GPU
evidence below predates this synchronization and was not rerun.
The integration includes PR #399's original commits, the acceptance fixes,
and English/Chinese README and development-progress updates. Main is unchanged.

## Fixes

1. Normalize frontend GPU labels to numeric IDs before the AI Toolkit early
   return. Otherwise `CUDA_VISIBLE_DEVICES` receives a display label.
2. Write dataset manifests with ASCII JSON escapes. The pinned upstream reads
   them with the platform default encoding, which can fail on Chinese paths
   or captions on Windows.
3. Disable a second image resize in the Qwen Image 2.1 processor only. Upstream
   already prepares reference images on its 32-pixel grid for both TE and VAE.
   The processor's minimum-area resize changed a 320x192 reference to 352x224,
   producing 77 TE slots against 60 VAE slots and failing training.
4. Update stale tests for the PR's local-model contract and additional models.
   Keep negative coverage for missing assets and unsupported configuration.
5. Resolve the TrainingPage import conflict while retaining dev dataset checks.

## Automated Checks

- Frontend `npm run check`: 290 tests passed; typecheck and build passed.
- ESLint: zero errors, two existing EngineStatusBar prop-default warnings.
- AI Toolkit backend suite: 68 tests passed.
- Incoming dev dataset copy/in-use/validation/file-list regressions: 37 passed.
- `git diff --check`: passed.
- Independent read-only review: no actionable findings in the scoped fixes.

## Real GPU Smoke

Windows, RTX 4090 24 GB, isolated Python 3.11.14 environment, torch
2.11.0+cu128, transformers 5.5.3. AI Toolkit snapshot:
`ecee894ed2b1f3716d9d7326693061ec1a3105bb`.
Diffusers snapshot: `c943837899b16cbae2f619b8dd4f7bb6f07dd81a`.

Used existing local Qwen Image 2.1 ComfyUI transformer, Qwen3-VL text encoder
and VAE files without copying weights. Small config/processor files were
provided locally. Both jobs used the actual adapter, environment audit,
preflight, unified task launcher and driver.

| Mode | Training | Preview | Result |
| --- | --- | --- | --- |
| Text-to-image | 3 steps, loss 0.3307 / 0.1810 / 0.2266 | 256x256, 20 sampling steps | Exit 0, LoRA saved, recognizable image |
| Image editing | 3 steps, loss 0.1422 / 0.07111 / 0.04356 | 256x256, 20 sampling steps, one reference | Exit 0, LoRA saved, recognizable image |

Two images covered 256x256 and 320x192 training buckets. Settings: batch 1,
rank/alpha 4, AdamW, learning rate 0.0001, bf16, float8 quantization for
transformer and TE, low-VRAM mode and layer offloading.
Both final LoRA files contain 384 tensors, all finite (no NaN/Inf).

The first edit attempt hit a CUDA allocation failure during initialization.
A rerun passed initialization and exposed the reproducible slot mismatch
above. After the resize fix, editing completed. The isolated allocation
failure was not conclusively diagnosed and remains an environment stability
caveat, not a claimed code fix.

## Limits

- Three-step smoke verifies execution, not convergence or output quality.
- Edit target and reference used the same source images; this checks reference
  plumbing, not learned editing ability.
- Initial two-step sampling produced a blurry preview; final acceptance used
  20 sampling steps and visual inspection.
- No full browser/HTTP end-to-end acceptance in this run.
- Other model families and alternative quantizers were not GPU-tested.
- The initial acceptance did not merge branches; subsequent dev integration
  is recorded separately above. No main merge or release is included.
