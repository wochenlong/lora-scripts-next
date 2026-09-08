# Anima Fast Main Refresh Design

## Goal

Promote the validated Anima Fast update from `dev` to `main` through a focused
PR without merging the new engine registry, AI Toolkit, marketplace, or task
workbench changes.

## Scope

The PR updates the existing `main` implementation under
`mikazuki/anima_fast_backend` and keeps its public API and extension layout.
It includes:

- the validated Anima upstream v1.17.1 source pin;
- the CUDA 13.2 / PyTorch 2.12 dependency set;
- explicit Windows Triton installation and dependency audit;
- Windows and Linux flash-attn wheel selection;
- idempotent handling of the ComfyUI checkpoint prefix patch;
- Anima 2.9B model detection and preflight facts;
- curated LoRA and T-LoRA variants;
- removal of obsolete v1.17.1 fields and legacy cache translation;
- Anima Fast installer cache reuse;
- presets, schema, documentation, and regression tests required by those
  behaviors.

DGX Spark support is included only where it is already part of the shared
dependency selection code. No unrelated engine or frontend architecture is
promoted.

## Architecture

The implementation is ported into the old `main` package names rather than
copying `dev` paths. Existing routes and CLI entry points continue importing
`mikazuki.anima_fast_backend`. Configuration remains adapted through the
current `main` adapter, then validated by preflight before the copied upstream
trainer is launched.

The installer remains responsible for creating the Python 3.13 environment,
copying the pinned upstream snapshot, localizing platform-specific
dependencies, applying only still-required source patches, installing explicit
targets, and auditing the completed environment.

## Compatibility Boundary

- Existing Anima Fast LoRA configurations remain accepted.
- `fast_variant` defaults to `lora`; `tlora` adds only the curated timestep-mask
  network arguments.
- Removed upstream fields are ignored with warnings instead of being forwarded.
- Unsupported memory options remain blocked until separately validated.
- `main` keeps its current API routes, task model, and frontend architecture.

## Verification

Automated verification covers adapter output, T-LoRA argument control, model
facts, source pinning, dependency targets, platform wheel selection, patch
idempotence, install command construction, preflight, routes, CLI, and static
integration.

Release verification uses a fresh Anima Fast extension directory:

1. Run the automatic installer without manually adding packages.
2. Confirm the environment audit, including Triton on Windows.
3. Train Anima 2.9B LoRA for a short run and verify progress, loss, and a
   readable `.safetensors` output.
4. Run a short T-LoRA smoke if T-LoRA is advertised in the PR.
5. Re-run the focused automated suite and relevant main regression tests.

## Known Baseline

At `origin/main` commit `6cb5a590`, the focused baseline produced 132 passes,
5 passing subtests, and 4 failures. Three failures are in the legacy standard
Anima upstream pin tests and one is in the frozen-plan install task test. These
failures must be investigated and clearly separated from regressions introduced
by this PR.
