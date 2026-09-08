# Anima Fast Main Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote the validated Anima Fast v1.17.1, Anima 2.9B, and curated T-LoRA support to `main` without promoting the `dev` engine architecture.

**Architecture:** Port the behavior into `mikazuki/anima_fast_backend`, retaining the existing `main` routes and CLI. Keep installation, adaptation, preflight, and launch responsibilities separate, and verify the complete path in a fresh extension directory before opening the PR.

**Tech Stack:** Python 3.10 host tests, isolated Python 3.13 Anima runtime, pytest/unittest, uv, PyTorch 2.12 CUDA 13.2, TypeScript schema, TOML presets.

---

### Task 1: Record And Stabilize The Main Baseline

**Files:**
- Modify: `tests/test_anima_fast_environment_installer.py`
- Modify only if the behavior is demonstrably wrong: `mikazuki/anima_fast_backend/environment.py`
- Do not modify as part of this feature: `mikazuki/anima_backend/upstream.py`

- [ ] **Step 1: Reproduce the focused baseline**

Run:

```powershell
python -m pytest -q `
  tests/test_anima_fast_backend.py `
  tests/test_anima_fast_environment_installer.py `
  tests/test_anima_fast_integration_static.py `
  tests/test_anima_fast_plugin_api.py `
  tests/test_anima_fast_preprocess.py `
  tests/test_anima_fast_preview.py `
  tests/test_anima_fast_progress_metrics.py `
  tests/test_anima_fast_settings.py `
  tests/test_anima_fast_source_root.py `
  tests/test_install_anima_fast_cli.py `
  tests/test_anima_backend_upstream.py
```

Expected baseline: 132 passes, 5 passing subtests, 4 failures.

- [ ] **Step 2: Trace the frozen-plan task failure**

Run the single failing test with task logging enabled:

```powershell
python -m pytest -vv -s tests/test_anima_fast_environment_installer.py::AnimaFastEnvironmentInstallerTests::test_start_install_resolves_source_root_on_frozen_plan
```

Inspect the completed task error and determine whether the failure is caused by
the test fixture, task scheduling, or `start_install_task`.

- [ ] **Step 3: Add a failing regression test only if production behavior is wrong**

The regression must assert that the source root returned by
`ensure_install_source_ready` is copied into the immutable install plan before
`install_environment` is called.

- [ ] **Step 4: Implement the smallest production correction**

Change only the identified source-root propagation point. Do not alter standard
Anima pin policy in this PR.

- [ ] **Step 5: Verify and commit**

```powershell
python -m pytest -q tests/test_anima_fast_environment_installer.py
git add tests/test_anima_fast_environment_installer.py mikazuki/anima_fast_backend/environment.py
git commit -m "test(anima-fast): stabilize main install baseline"
```

If the failure is environmental or fixture-only, document it in the PR and do
not create a production-code commit.

### Task 2: Port The Runtime And Dependency Refresh

**Files:**
- Modify: `config/anima_fast_backend.toml`
- Delete: `config/anima_fast_environment/anima-constraints-cu130.txt`
- Delete: `config/anima_fast_environment/anima-overrides-cu130.txt`
- Create: `config/anima_fast_environment/anima-constraints-cu132.txt`
- Create: `config/anima_fast_environment/anima-overrides-cu132.txt`
- Modify: `mikazuki/anima_fast_backend/environment.py`
- Modify: `mikazuki/anima_fast_backend/extension_state.py`
- Modify: `mikazuki/anima_fast_backend/installer.py`
- Modify: `mikazuki/anima_fast_backend/launcher.py`
- Modify: `mikazuki/anima_fast_backend/preprocess.py`
- Modify: `tests/test_anima_fast_environment_installer.py`
- Modify: `tests/test_install_anima_fast_cli.py`

- [ ] **Step 1: Add failing dependency-selection tests**

Cover:

```python
assert "triton-windows==3.7.0.post26" in anima_pip_dependency_targets("win32")
assert "triton-windows==3.7.0.post26" not in anima_pip_dependency_targets("linux")
assert "cu132" in flash_attn_dependency_target("win32", "AMD64")
assert "linux_x86_64" in flash_attn_dependency_target("linux", "x86_64")
assert "linux_aarch64" in flash_attn_dependency_target("linux", "aarch64")
```

Also assert the install command contains the explicit core targets and does not
contain `--no-cache`.

- [ ] **Step 2: Verify the new tests fail**

```powershell
python -m pytest -q tests/test_anima_fast_environment_installer.py tests/test_install_anima_fast_cli.py
```

Expected: failures mention missing CUDA 13.2 targets, Triton, wheel selection, or
the existing `--no-cache` flag.

- [ ] **Step 3: Port the validated dependency implementation**

Use the `origin/dev` Anima Fast environment behavior, changing imports only to
the old package path. Preserve:

```python
ANIMA_CONSTRAINTS = ENVIRONMENT_DIR / "anima-constraints-cu132.txt"
ANIMA_OVERRIDES = ENVIRONMENT_DIR / "anima-overrides-cu132.txt"
ANIMA_WINDOWS_TRITON_TARGET = "triton-windows==3.7.0.post26"
ANIMA_CUDA_TAG = "cu132"
```

Keep `anima_pip_dependency_targets(platform)` platform-aware and
`flash_attn_dependency_target(platform, machine, github_url_prefix)`
architecture-aware.

- [ ] **Step 4: Port the idempotent checkpoint-prefix behavior**

Add a failing test where upstream already uses `_DIT_PREFIXES` with
`"model.diffusion_model."`; it must return no changed files. Retain the loud
anchor-miss error for unknown source layouts.

- [ ] **Step 5: Verify and commit**

```powershell
python -m pytest -q tests/test_anima_fast_environment_installer.py tests/test_install_anima_fast_cli.py
git diff --check
git add config/anima_fast_backend.toml config/anima_fast_environment `
  mikazuki/anima_fast_backend tests/test_anima_fast_environment_installer.py `
  tests/test_install_anima_fast_cli.py
git commit -m "feat(anima-fast): refresh CUDA 13.2 runtime"
```

### Task 3: Port Anima 2.9B And T-LoRA Adaptation

**Files:**
- Modify: `mikazuki/anima_fast_backend/adapter.py`
- Modify: `mikazuki/anima_fast_backend/preflight.py`
- Modify: `mikazuki/schema/anima-lora-fast.ts`
- Create: `config/presets/anima-fast-lora-character-tlora.toml`
- Create: `config/presets/anima-fast-lora-style-tlora.toml`
- Modify: `config/presets/anima-fast-lora-character.toml`
- Modify: `config/presets/anima-fast-lora-style.toml`
- Modify: `tests/test_anima_fast_backend.py`
- Modify: `tests/test_anima_fast_integration_static.py`
- Modify: `tests/test_anima_fast_plugin_api.py`
- Modify: `tests/test_anima_fast_preprocess.py`

- [ ] **Step 1: Add failing T-LoRA adapter tests**

Verify:

```python
adapted = adapt_config({"fast_variant": "tlora", ...}, runtime, "run")
assert adapted.values["use_timestep_mask"] is True
assert adapted.values["min_rank"] == 1
assert adapted.values["alpha_rank_scale"] == 1.0
```

Also verify user-supplied curated top-level arguments cannot override the
variant, unknown variants fail, removed v1.17.1 fields are not forwarded, and
legacy cache fields translate to `use_vae_cache` / `use_text_cache`.

- [ ] **Step 2: Verify the tests fail**

```powershell
python -m pytest -q tests/test_anima_fast_backend.py tests/test_anima_fast_integration_static.py
```

- [ ] **Step 3: Port the adapter and preflight behavior**

Retain `main` path handling and preview behavior while introducing:

```python
SUPPORTED_FAST_VARIANTS = {"lora", "tlora"}
TLORA_NETWORK_ARGS = {
    "use_timestep_mask": "true",
    "min_rank": "1",
    "alpha_rank_scale": "1.0",
}
```

Port v1.17.1 field cleanup and 2.9B checkpoint facts without importing the
`mikazuki.engines` registry.

- [ ] **Step 4: Update schema and presets**

Add `fast_variant` with `lora` as the default. Keep the existing main form
sections and add two explicit T-LoRA presets.

- [ ] **Step 5: Verify and commit**

```powershell
python -m pytest -q `
  tests/test_anima_fast_backend.py `
  tests/test_anima_fast_integration_static.py `
  tests/test_anima_fast_plugin_api.py `
  tests/test_anima_fast_preprocess.py
git diff --check
git add mikazuki/anima_fast_backend/adapter.py `
  mikazuki/anima_fast_backend/preflight.py `
  mikazuki/schema/anima-lora-fast.ts config/presets `
  tests/test_anima_fast_backend.py tests/test_anima_fast_integration_static.py `
  tests/test_anima_fast_plugin_api.py tests/test_anima_fast_preprocess.py
git commit -m "feat(anima-fast): support Anima 2.9B and T-LoRA"
```

### Task 4: Update Focused Documentation

**Files:**
- Modify: `docs/anima-fast.md`
- Modify: `docs/anima-fast-merge-checklist.md`
- Create: `docs/research/2026-09-08-anima-fast-main-refresh.md`

- [ ] **Step 1: Document supported and unsupported boundaries**

State the pinned upstream version, Python/CUDA/PyTorch requirements, validated
GPU, LoRA/T-LoRA status, unsupported low-VRAM controls, and clean-install test
procedure.

- [ ] **Step 2: Check documentation references**

```powershell
rg -n "cu130|2\\.11\\.0|87819818975e08167cda8a6f615776e46e889f80" `
  docs/anima-fast.md docs/anima-fast-merge-checklist.md `
  config/anima_fast_backend.toml config/anima_fast_environment `
  mikazuki/anima_fast_backend tests/test_anima_fast*
```

Expected: no stale runtime facts in the refreshed Anima Fast surface.

- [ ] **Step 3: Commit**

```powershell
git add docs/anima-fast.md docs/anima-fast-merge-checklist.md `
  docs/research/2026-09-08-anima-fast-main-refresh.md
git commit -m "docs: update Anima Fast runtime guidance"
```

### Task 5: Automated Regression Verification

**Files:**
- No production edits unless a failing regression first demonstrates a defect.

- [ ] **Step 1: Run the full focused suite**

```powershell
python -m pytest -q `
  tests/test_anima_fast_backend.py `
  tests/test_anima_fast_environment_installer.py `
  tests/test_anima_fast_integration_static.py `
  tests/test_anima_fast_plugin_api.py `
  tests/test_anima_fast_preprocess.py `
  tests/test_anima_fast_preview.py `
  tests/test_anima_fast_progress_metrics.py `
  tests/test_anima_fast_routes.py `
  tests/test_anima_fast_settings.py `
  tests/test_anima_fast_source_root.py `
  tests/test_install_anima_fast_cli.py
```

- [ ] **Step 2: Run adjacent main regressions**

```powershell
python -m pytest -q `
  tests/test_cli_entrypoints.py `
  tests/test_task_lanes.py `
  tests/test_process_stub_isolation.py `
  tests/test_standard_run_api.py
```

- [ ] **Step 3: Run static checks**

```powershell
python -m compileall -q mikazuki scripts/cli
git diff --check origin/main...HEAD
```

### Task 6: Fresh Install And GPU Smoke

**Files:**
- Runtime output only under a fresh, untracked validation directory.

- [ ] **Step 1: Remove only the dedicated validation extension directory**

Resolve the exact validation root, verify it is inside the dedicated worktree,
and remove it with PowerShell `Remove-Item -LiteralPath ... -Recurse -Force`.
Do not reuse an existing Anima extension environment.

- [ ] **Step 2: Run the automatic installer**

```powershell
python scripts/cli/install_anima_fast.py --project-root . --yes
```

Confirm that installation reaches READY without manually installing Triton.

- [ ] **Step 3: Audit the environment**

Record Python, PyTorch, CUDA, Triton, flash-attn, transformers, diffusers,
accelerate, and safetensors versions.

- [ ] **Step 4: Run Anima 2.9B LoRA**

Use the previously validated local model and dataset paths. Run 100 steps unless
the existing smoke configuration is intentionally shorter. Confirm the first
optimizer step, numeric loss, progress output, normal termination, and readable
`.safetensors`.

- [ ] **Step 5: Run T-LoRA smoke**

Run a short T-LoRA job using `fast_variant=tlora`. Confirm the generated
configuration contains the curated timestep-mask arguments and produces a
readable output.

- [ ] **Step 6: Save non-secret evidence**

Add a concise validation table to
`docs/research/2026-09-08-anima-fast-main-refresh.md`. Do not commit model paths
that expose private user directories, tokens, or large artifacts.

### Task 7: Independent Review And Pull Request

**Files:**
- Modify only for review findings supported by a failing test.

- [ ] **Step 1: Request an independent code review**

Review `origin/main...HEAD` for correctness, compatibility, scope leakage,
installer safety, and missing tests.

- [ ] **Step 2: Address all critical and important findings**

For each behavior change, add a failing regression test before changing
production code.

- [ ] **Step 3: Re-run final verification**

Repeat Tasks 5 and 6 as needed after review fixes.

- [ ] **Step 4: Push and create the PR**

```powershell
git push -u origin codex/anima-fast-main-refresh
gh pr create -R wochenlong/lora-scripts-next `
  --base main `
  --head codex/anima-fast-main-refresh `
  --title "feat(anima-fast): promote Anima 2.9B runtime refresh to main" `
  --body-file tmp/pr-anima-fast-main-refresh.md
```

The PR body must list automated results, clean-install versions, GPU training
evidence, known limitations, the four pre-existing baseline failures and their
disposition, and explicitly state that the PR does not merge `dev`.
