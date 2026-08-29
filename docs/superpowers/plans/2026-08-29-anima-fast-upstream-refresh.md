# Anima Fast Upstream Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task with verification checkpoints.

**Goal:** Upgrade the Anima Fast plugin to the upstream stable backend that supports Anima 2.9B and T-LoRA while keeping the project integration limited to curated LoRA-family workflows and excluding upstream GUI/ComfyUI-only features.

**Architecture:** Keep `extensions/anima_lora/source` as an install-time upstream snapshot selected by `source_commit`. Extend the project adapter and schema with a curated T-LoRA variant, while retaining a single Fast engine and separate runtime environment. Add model-aware preflight/cache protection so base Anima and Anima 2.9B cannot silently share incompatible caches.

**Tech Stack:** Python, TypeScript/Vue schema definitions, TOML dependency constraints, pytest, existing Fast engine installer and API contracts.

---

### Task 1: Establish the upstream stable snapshot

**Files:**
- Modify: `config/anima_fast_backend.toml`
- Modify: `mikazuki/engines/anima_fast/manifest.py`
- Test: `tests/test_anima_fast_backend.py`
- Test: `tests/test_anima_fast_routes.py`

- [x] **Step 1: Write the failing pin/provenance tests**

Add assertions that the manifest and backend config use the selected upstream stable commit, and that the installer preserves that commit in `.source_commit`.

- [x] **Step 2: Run the focused tests and verify the expected failure**

Run:

```powershell
pytest tests/test_anima_fast_backend.py tests/test_anima_fast_routes.py -q
```

Expected: the new commit assertions fail because the repository still pins `87819818975e08167cda8a6f615776e46e889f80`.

- [x] **Step 3: Update the source pin**

Set both project pins to the verified `v1.17.1` stable commit:

```text
b43928b5e4b82b907bfca1a322383a33088d0bdd
```

Do not point the shipped plugin at the moving upstream `main`.

- [x] **Step 4: Run the focused tests**

Run:

```powershell
pytest tests/test_anima_fast_backend.py tests/test_anima_fast_routes.py -q
```

Expected: all focused tests pass.

- [ ] **Step 5: Commit**

```powershell
git add config/anima_fast_backend.toml mikazuki/engines/anima_fast/manifest.py tests/test_anima_fast_backend.py tests/test_anima_fast_routes.py
git commit -m "feat(anima-fast): refresh upstream source pin"
```

### Task 2: Add curated T-LoRA configuration

**Files:**
- Modify: `mikazuki/schema/anima-lora-fast.ts`
- Modify: `mikazuki/engines/anima_fast/adapter.py`
- Modify: `config/presets/anima-fast-lora-character.toml`
- Modify: `config/presets/anima-fast-lora-style.toml`
- Test: `tests/test_anima_fast_backend.py`
- Test: `tests/test_anima_fast_integration_static.py`

- [x] **Step 1: Write the failing adapter/schema tests**

Cover these exact behaviors:

```python
def test_tlora_variant_injects_only_curated_upstream_flags():
    adapted = adapt_config({"fast_variant": "tlora"}, runtime, "run-1")
    assert adapted.values["method"] == "lora"
    assert "use_timestep_mask=true" in adapted.values["network_args"]
    assert "min_rank=1" in adapted.values["network_args"]

def test_unknown_fast_variant_is_rejected():
    with pytest.raises(AdapterError):
        adapt_config({"fast_variant": "turbo"}, runtime, "run-1")
```

The schema test must confirm that the UI exposes only `lora` and `tlora`, while `turbo` and arbitrary upstream methods are absent.

- [x] **Step 2: Run the new tests and verify they fail**

Run:

```powershell
pytest tests/test_anima_fast_backend.py tests/test_anima_fast_integration_static.py -q
```

Expected: the new variant assertions fail because the current schema has a hidden constant `lora_type = "lora"` and the adapter rejects non-MVP variants.

- [x] **Step 3: Implement the minimal curated variant mapping**

Use a project-facing `fast_variant` field with values `lora` and `tlora`. Keep the upstream invocation as `method = "lora"` and `network_module = "networks.lora_anima"; enable T-LoRA through the exact upstream network/config flags required by the pinned source.

Reject `lokr`, `turbo`, `controlnet`, and unknown values before launch. Do not turn the existing custom network argument field into an unrestricted pass-through.

- [x] **Step 4: Add separate character/style T-LoRA presets**

Add T-LoRA presets that inherit the existing Fast LoRA defaults and explicitly set the curated timestep-mask options. Preserve the current basic LoRA presets unchanged for backward compatibility.

- [x] **Step 5: Run the focused tests**

Run:

```powershell
pytest tests/test_anima_fast_backend.py tests/test_anima_fast_integration_static.py -q
```

Expected: all adapter and static integration tests pass.

- [ ] **Step 6: Commit**

```powershell
git add mikazuki/schema/anima-lora-fast.ts mikazuki/engines/anima_fast/adapter.py config/presets/anima-fast-lora-*.toml tests/test_anima_fast_backend.py tests/test_anima_fast_integration_static.py
git commit -m "feat(anima-fast): expose curated T-LoRA variant"
```

### Task 3: Add Anima 2.9B model detection and cache isolation

**Files:**
- Modify: `mikazuki/engines/anima_fast/preflight.py`
- Modify: `mikazuki/engines/anima_fast/adapter.py`
- Modify: `mikazuki/engines/anima_fast/preprocess.py`
- Modify: `mikazuki/schema/anima-lora-fast.ts`
- Test: `tests/test_anima_fast_backend.py`
- Test: `tests/test_anima_fast_preprocess.py`

- [ ] **Step 1: Write failing model-aware tests**

Cover:

```python
def test_preflight_reports_anima_29b_model_family():
    result = run_preflight(config_for("anima-2.9b.safetensors"), runtime, probe=stub_probe)
    assert result.facts["anima_model_variant"] == "2.9b"

def test_model_variants_use_distinct_cache_roots():
    base = default_dataset_cache_dir("train/data", runtime, "run-1", "lora", model_variant="base")
    large = default_dataset_cache_dir("train/data", runtime, "run-1", "lora", model_variant="2.9b")
    assert base != large
```

- [ ] **Step 2: Run the new tests and verify they fail**

Run:

```powershell
pytest tests/test_anima_fast_backend.py tests/test_anima_fast_preprocess.py -q
```

Expected: the current preflight has no model-family fact and the cache helper derives paths only from the dataset.

- [ ] **Step 3: Implement model detection without hardcoding user paths**

Detect the model variant from the checkpoint metadata or filename fallback. Preserve the existing base model default, recognize Anima 2.9B, and fail with a clear preflight error for an unknown Anima architecture when the upstream loader cannot identify it.

- [ ] **Step 4: Include model variant and upstream snapshot in cache identity**

Make latent/text-encoder/LoRA cache paths include a stable model identity and source snapshot identity. Existing caches must remain readable only when their recorded identity matches the requested model.

- [ ] **Step 5: Add 2.9B documentation and validation messages**

Document that 2.9B is supported, that it generally needs more VRAM, and that the user should use the matching VAE/text encoder assets. Do not change the default base model path.

- [ ] **Step 6: Run the focused tests**

Run:

```powershell
pytest tests/test_anima_fast_backend.py tests/test_anima_fast_preprocess.py -q
```

Expected: all model detection and cache isolation tests pass.

- [ ] **Step 7: Commit**

```powershell
git add mikazuki/engines/anima_fast/preflight.py mikazuki/engines/anima_fast/adapter.py mikazuki/engines/anima_fast/preprocess.py mikazuki/schema/anima-lora-fast.ts tests/test_anima_fast_backend.py tests/test_anima_fast_preprocess.py docs/anima-fast.md
git commit -m "feat(anima-fast): support Anima 2.9B model identity"
```

### Task 4: Refresh and prune the isolated runtime dependencies

**Files:**
- Modify: `config/anima_fast_environment/anima-constraints-cu130.txt`
- Modify: `config/anima_fast_environment/anima-overrides-cu130.txt`
- Modify: `mikazuki/engines/anima_fast/installer.py`
- Modify: `mikazuki/engines/anima_fast/environment.py`
- Test: `tests/test_anima_fast_environment_installer.py`

- [ ] **Step 1: Write failing dependency policy tests**

Assert that the install plan excludes upstream `custom_nodes`, `bench`, and GUI-only directories, removes SAM3-only dependency lines from the copied `pyproject.toml`, and retains only the packages required by core LoRA/T-LoRA training.

- [ ] **Step 2: Run the tests and verify the expected failure**

Run:

```powershell
pytest tests/test_anima_fast_environment_installer.py -q
```

Expected: the new dependency-version and exclusion assertions fail against the old CUDA 13.0 / torch 2.11 constraints.

- [ ] **Step 3: Update constraints from the pinned upstream stable source**

Align Python, torch, torchvision, transformers, diffusers, Triton, and optimizer versions with the selected stable upstream source. Keep CUDA and ROCm dependency groups separate; do not add ComfyUI or upstream GUI packages.

- [ ] **Step 4: Make source filtering explicit**

Keep the existing snapshot allowlist and add tests/documentation that it is intentional. The copied source must contain the training core and required configs/networks/scripts, but not `custom_nodes`, `bench`, `_archive`, or upstream GUI assets.

- [ ] **Step 5: Run installer tests**

Run:

```powershell
pytest tests/test_anima_fast_environment_installer.py -q
```

Expected: all installer and dependency policy tests pass.

- [ ] **Step 6: Commit**

```powershell
git add config/anima_fast_environment mikazuki/engines/anima_fast/installer.py mikazuki/engines/anima_fast/environment.py tests/test_anima_fast_environment_installer.py
git commit -m "build(anima-fast): refresh and prune plugin runtime"
```

### Task 5: Add regression coverage and update the handoff/PR documentation

**Files:**
- Modify: `docs/anima-fast.md`
- Modify: `docs/anima-fast-merge-checklist.md`
- Modify: `tests/test_anima_fast_backend.py`
- Modify: `tests/test_anima_fast_integration_static.py`
- Create: `docs/team/anima-fast-upstream-refresh.md`

- [ ] **Step 1: Add the explicit coverage matrix**

Document and test the supported matrix:

```text
Supported in this PR:
- Anima base model
- Anima 2.9B
- basic LoRA
- T-LoRA
- existing project-side preprocess/cache/preview/progress flow

Not covered in this PR:
- LoKr
- Turbo/distillation
- ControlNet / EasyControl / Qwen Image editing
- upstream standalone GUI
- ComfyUI custom nodes
- SAM3 and Tagger
- upstream model downloader/Hugging Face GUI
- other experimental methods
```

- [ ] **Step 2: Add command-line smoke-test instructions**

Document the two required 100-step smoke tests, one for base Anima and one for Anima 2.9B, including expected output LoRA files and the T-LoRA variant check.

- [ ] **Step 3: Run the complete Fast test suite**

Run:

```powershell
pytest tests/test_anima_fast_*.py tests/test_anima_backend_adapter.py tests/test_anima_backend_upstream.py -q
```

Expected: zero failures.

- [ ] **Step 4: Run static repository checks**

Run:

```powershell
python -m compileall mikazuki/engines/anima_fast mikazuki/schema
git diff --check
```

Expected: both commands exit successfully with no whitespace errors.

- [ ] **Step 5: Commit**

```powershell
git add docs/anima-fast.md docs/anima-fast-merge-checklist.md docs/team/anima-fast-upstream-refresh.md tests/test_anima_fast_*.py tests/test_anima_backend_adapter.py tests/test_anima_backend_upstream.py
git commit -m "docs(anima-fast): record refresh coverage and follow-ups"
```

### Task 6: Push and create the PR

**Files:**
- Review: all commits and `git diff origin/dev...HEAD`

- [ ] **Step 1: Run the final verification commands**

Run:

```powershell
pytest tests/test_anima_fast_*.py tests/test_anima_backend_adapter.py tests/test_anima_backend_upstream.py -q
python -m compileall mikazuki/engines/anima_fast mikazuki/schema
git diff --check
git status --short
```

Expected: tests pass, compileall and diff checks exit 0, and only intended files are changed.

- [ ] **Step 2: Push the branch**

```powershell
git push -u origin codex/anima-fast-upstream-refresh
```

- [ ] **Step 3: Create the PR**

Create a PR targeting `dev` with a human-readable title:

```text
feat(anima-fast): refresh upstream, add Anima 2.9B and T-LoRA
```

The PR body must include:

```markdown
## Included
- Refreshes the pinned upstream Anima Fast backend to stable v1.17.1.
- Adds Anima 2.9B model detection and cache isolation.
- Adds a curated T-LoRA variant alongside basic LoRA.
- Keeps the plugin environment separate from the main GUI environment.
- Prunes upstream GUI/ComfyUI/SAM3-only content from the plugin install.

## Explicitly not included in this PR
- LoKr
- Turbo/distillation
- ControlNet, EasyControl, Qwen Image editing
- upstream standalone GUI
- ComfyUI custom nodes
- SAM3 and Tagger
- upstream model downloader/Hugging Face GUI
- other experimental or inference-only methods

## Validation
- Fast backend unit/integration tests
- base Anima 100-step CLI smoke test
- Anima 2.9B 100-step CLI smoke test
- T-LoRA adapter/preset test
- cache identity and installer dependency tests
```

- [ ] **Step 4: Report the PR URL and exact verification results**

Include the PR URL, target branch, source commit, tests passed, and any hardware-dependent smoke test that could not run locally.
