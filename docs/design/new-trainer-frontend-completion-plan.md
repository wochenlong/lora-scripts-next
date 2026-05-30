# New Trainer Frontend Completion Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a source-owned training UI that keeps SD Trainer Next independent from missing legacy frontend source, restores practical full training forms route by route, and presents a polished trainer experience that is visually and behaviorally familiar to Akiba/original trainer users while being cleaner, more searchable, and safer to run.

**Architecture:** `frontend/source` remains the source of truth, `build/frontend-source-dist` is the generated artifact, and `frontend/dist` is committed only from the guarded sync script. Mature training routes should move from compatibility cards to shared schema-rendered forms by adapting existing `mikazuki/schema/*.ts` contracts into local `TrainingSectionSpec` modules. Anima stays the reference implementation for workflow, preview, save/load/import/export, and run submission behavior.

**Tech Stack:** Vue 3 render functions, Vite, Playwright, pytest, `scripts/sync_frontend_source_dist.py`, `scripts/verify_frontend_source.py`, `scripts/verify_frontend_dist_matches_source.py`.

---

## Feasibility Verdict

This is feasible. The hardest dependency problem has already been broken: production `frontend/dist` can now be generated from `frontend/source`, and the committed dist can be proven byte-for-byte equal to the source build.

The remaining work is product reconstruction, not blocked-source recovery. The main cost is schema migration volume:

- Anima routes are already source-owned and should be polished into the reference training experience.
- Mature training routes already have source compatibility shells and can be restored one route at a time.
- Existing schema files under `mikazuki/schema/` provide field names, defaults, groups, and option sets. They are not directly executable in the browser source app, so each restored route needs a local schema adapter module.
- The current renderer already supports text, number, checkbox, select, textarea, table arrays, visibility rules, file/folder browse affordances, section navigation, search, previews, and run submission.

The target visual direction should be "Akiba-familiar, SD Trainer Next cleaner": left navigation, dense grouped forms, right-side parameter preview/run workflow, compact controls, clear section navigation, and fewer decorative blocks. This is a source-owned reconstruction of the old trainer experience, not a blank new shell. We should not copy old minified CSS; we should recreate the useful layout language from readable `frontend/source` code.

## Updated Acceptance Intent

The user-facing target is closer to pixel-parity than compatibility scaffolding. The old frontend's practical surface area is the benchmark:

- Training routes that existed in the old frontend should not be empty or card-only unless they are explicitly marked as temporary migration fallbacks.
- Training parameter coverage should be restored from the existing schema contracts and backend-facing parameter names.
- The core layout should preserve the recognizable old workflow: left navigation, central grouped parameter editor, right parameter preview/actions panel.
- Buttons, switches, numeric controls, file/folder affordances, save/load/import/export controls, and start/stop training actions should feel familiar to existing users.
- Improvements are welcome when they make the UI clearer, denser, more searchable, or safer, but not when they make the trainer feel unrelated to the old product.
- Backend training behavior is a red line. Prefer adapting source frontend schemas, renderers, and payload builders to existing APIs instead of changing backend launch semantics.

In short: source independence is necessary but not sufficient. The finished product must also restore the old frontend's pages, parameter editing experience, and visual rhythm from maintainable source.

## Completion Definition

The new training frontend is considered complete when all P0 acceptance labels pass.

### P0 Acceptance Labels

- **[P0-A1 Source Ownership]** Every public frontend route in `frontend/source/src/routes.json` is generated from source and covered by `scripts/verify_frontend_source.py --require-built-output`.
- **[P0-A2 Production Sync]** `frontend/dist` matches `build/frontend-source-dist` byte-for-byte after `scripts/sync_frontend_source_dist.py --apply --backup`.
- **[P0-A3 Production Browser Smoke]** `npm run smoke:dist` passes against committed `frontend/dist`.
- **[P0-A4 Native Tag Editor]** `/native-tageditor.html`, `/native-tageditor-standalone.html`, and `/dataset-editor.html` render the source-owned native editor and do not require old VuePress chunks.
- **[P0-A5 Classic Tag Editor Retirement]** `/tageditor.html` remains a stable route but does not depend on `/proxy/tageditor/`; it guides users to native editor routes.
- **[P0-A6 Anima Full Form]** `/lora/sd3.html` and `/lora/anima-finetune.html` expose all currently migrated Anima sections, submit the expected `model_train_type`, show run result links, provide save/load/import/export, and retain old-style parameter density with a right-side parameter preview/actions panel.
- **[P0-A7 Mature Training Forms]** `/lora/basic.html`, `/lora/master.html`, `/lora/flux.html`, and `/dreambooth/index.html` no longer stop at compatibility cards; each has a source-owned form with model, dataset, output, training, optimizer, cache, preview, and advanced sections mapped from existing schema contracts.
- **[P0-A8 Legacy Visual Parity]** Core training pages preserve the old frontend's recognizable layout and interaction model: left navigation, central grouped parameter editor, right parameter preview/actions panel, compact controls, visible file/folder affordances, and prominent training controls.
- **[P0-A9 Backend Red Line]** Restored pages submit existing backend-facing parameter names and train-type contracts. Backend changes are allowed only for small compatibility fixes that do not alter training launch semantics.
- **[P0-A10 Verification Gate]** This command set passes from repo root:

```powershell
cd frontend\source
npm run check
npm run build
npm run smoke
npm run smoke:dist
cd ..\..
.\venv\Scripts\python.exe scripts\verify_frontend_source.py --require-built-output
.\venv\Scripts\python.exe scripts\sync_frontend_source_dist.py
.\venv\Scripts\python.exe scripts\verify_frontend_dist_matches_source.py
.\venv\Scripts\python.exe -m pytest tests\test_frontend_source.py tests\test_dataset_editor_api.py tests\test_tagger_progress_api.py tests\test_portable_packaging_scripts.py -q
```

### P1 Acceptance Labels

- **[P1-B1 Akiba-Familiar Layout]** Training pages use dense left/main forms, grouped fieldsets, compact action bars, and right-side preview/run panels. They should feel familiar to existing trainer users without inheriting old brittle CSS.
- **[P1-B2 Better Than Old UX]** Each training page has search, section jump navigation, workflow summary, required-path status, and generated parameter preview.
- **[P1-B3 Reviewable Dist]** Any dist replacement commit is dist-only and accompanied by a preceding source commit plus `verify_frontend_dist_matches_source.py` output.
- **[P1-B4 Interaction Parity]** Common controls behave like users expect from the old UI: toggles feel like toggles, numeric controls stay compact, file/folder browse affordances are obvious, save/load/import/export controls sit near the preview, and start/stop training actions are prominent.
- **[P1-B5 No Empty Public Pages]** Public routes from the old frontend either provide real source-owned content or an explicit source-owned fallback explaining the migration state and linking to a working replacement.

### P2 Acceptance Labels

- **[P2-C1 Visual Polish]** Mobile and desktop screenshots show no overlapping controls at 390px, 768px, 1365px, and 1600px widths.
- **[P2-C2 Form Ergonomics]** Repeated option groups use reusable section specs rather than ad hoc route-specific code.
- **[P2-C3 Runtime Grace]** If backend APIs are unavailable, pages show useful status text instead of blank panels.
- **[P2-C4 Pixel-Parity Audit]** For the core training pages, compare screenshots against the old frontend and fix obvious spacing, density, button, panel, and preview mismatches unless the new design is intentionally cleaner.
- **[P2-C5 Source-Only Styling]** Visual parity must come from readable `frontend/source` CSS/components, not copied minified assets or hidden legacy bundles.

---

## Files And Responsibilities

- `frontend/source/src/trainingRenderer.ts`  
  Shared schema renderer: fields, rows, visibility rules, section rendering, preview, run controls, browse bridge.

- `frontend/source/src/anima.ts`  
  Reference full training page workflow: route-specific payload, save/load/import/export, run submission, summary, result links.

- `frontend/source/src/animaSchema.ts`  
  Reference source schema module with defaults and section specs.

- `frontend/source/src/matureTraining.ts`  
  Temporary compatibility template for mature routes. This should be replaced route-by-route with real schema-backed pages.

- `frontend/source/src/matureTrainingSchema.ts`  
  Create this file to hold shared mature training defaults and section factories used by Basic, SD, Flux, and Dreambooth.

- `frontend/source/src/matureTrainingPage.ts`  
  Create this file to host the generic full-form page for mature routes, modeled after `anima.ts` but parameterized by route plan.

- `frontend/source/scripts/smoke-source-frontend.spec.mjs`  
  Source preview smoke coverage.

- `frontend/source/scripts/smoke-dist-frontend.spec.mjs`  
  Production dist smoke coverage.

- `scripts/verify_frontend_source.py`  
  Static source contract verification.

- `scripts/verify_frontend_dist_matches_source.py`  
  Dist review aid proving generated production output is exact.

- `tests/test_frontend_source.py`  
  Python-side source contract tests.

---

## Implementation Plan

### Task 1: Lock The Current Production Baseline

**Files:**
- Modify: `docs/design/frontend-source-of-truth-plan.md`
- Test: `tests/test_frontend_source.py`

- [ ] **Step 1: Verify current baseline**

Run:

```powershell
cd frontend\source
npm run check
npm run build
npm run smoke
npm run smoke:dist
cd ..\..
.\venv\Scripts\python.exe scripts\verify_frontend_source.py --require-built-output
.\venv\Scripts\python.exe scripts\verify_frontend_dist_matches_source.py
.\venv\Scripts\python.exe -m pytest tests\test_frontend_source.py tests\test_dataset_editor_api.py tests\test_tagger_progress_api.py tests\test_portable_packaging_scripts.py -q
```

Expected:

```text
43+ source smoke tests passed
3 production dist smoke tests passed
frontend source contract OK (21 routes)
frontend dist matches source build
65 passed
```

- [ ] **Step 2: Add a baseline note**

Append a dated line to `docs/design/frontend-source-of-truth-plan.md`:

```markdown
- 2026-05-31: Production `frontend/dist` is now generated from `frontend/source` and verified with `scripts/verify_frontend_dist_matches_source.py`; mature training routes remain the next full-form recovery target.
```

- [ ] **Step 3: Commit**

```powershell
git add docs/design/frontend-source-of-truth-plan.md tests/test_frontend_source.py
git commit -m "docs(frontend): record production source baseline"
```

### Task 2: Extract Mature Training Route Plans

**Files:**
- Create: `frontend/source/src/matureTrainingSchema.ts`
- Modify: `frontend/source/src/matureTraining.ts`
- Test: `frontend/source/scripts/smoke-source-frontend.spec.mjs`

- [ ] **Step 1: Write failing route-plan smoke**

Add expectations to the existing `mature training route uses shared source template` test:

```js
await expect(page.locator(".training-compat-page")).toContainText("Schema source");
await expect(page.locator(".training-compat-page")).toContainText("mikazuki/schema");
```

Run:

```powershell
cd frontend\source
npx playwright test scripts/smoke-source-frontend.spec.mjs -g "mature training route"
```

Expected: fails because route plans do not expose schema source metadata yet.

- [ ] **Step 2: Create route plan module**

Create `frontend/source/src/matureTrainingSchema.ts`:

```ts
import type { AppRoute } from "./routes";

export interface MatureTrainingRoutePlan {
  path: string;
  family: string;
  schemaFile: string;
  backendEntrypoint: string;
  summary: string;
}

export const MATURE_TRAINING_ROUTES: Record<string, MatureTrainingRoutePlan> = {
  "/lora/basic.html": {
    path: "/lora/basic.html",
    family: "LoRA compatibility",
    schemaFile: "mikazuki/schema/lora-basic.ts",
    backendEntrypoint: "scripts/stable/train_network.py",
    summary: "Basic LoRA training route restored from source-owned schema sections.",
  },
  "/lora/master.html": {
    path: "/lora/master.html",
    family: "Stable Diffusion compatibility",
    schemaFile: "mikazuki/schema/lora-master.ts",
    backendEntrypoint: "scripts/dev/train_network.py",
    summary: "Stable Diffusion route restored without touching Anima workflows.",
  },
  "/lora/flux.html": {
    path: "/lora/flux.html",
    family: "Flux compatibility",
    schemaFile: "mikazuki/schema/flux-lora.ts",
    backendEntrypoint: "scripts/dev/flux_train_network.py",
    summary: "Flux LoRA route prepared for source-owned form recovery.",
  },
  "/dreambooth/index.html": {
    path: "/dreambooth/index.html",
    family: "Dreambooth compatibility",
    schemaFile: "mikazuki/schema/dreambooth.ts",
    backendEntrypoint: "scripts/stable/train_db.py",
    summary: "Dreambooth route prepared for source-owned form recovery.",
  },
};

export function matureTrainingPlanFor(route: AppRoute) {
  return MATURE_TRAINING_ROUTES[route.path];
}
```

- [ ] **Step 3: Render plan metadata in mature template**

Modify `frontend/source/src/matureTraining.ts` to import `matureTrainingPlanFor` and display:

```ts
h("dt", "Schema source"),
h("dd", plan.schemaFile),
h("dt", "Backend entrypoint"),
h("dd", plan.backendEntrypoint),
```

- [ ] **Step 4: Verify**

```powershell
cd frontend\source
npm run check
npx playwright test scripts/smoke-source-frontend.spec.mjs -g "mature training route"
```

Expected: all mature route tests pass.

- [ ] **Step 5: Commit**

```powershell
git add frontend/source/src/matureTraining.ts frontend/source/src/matureTrainingSchema.ts frontend/source/scripts/smoke-source-frontend.spec.mjs
git commit -m "feat(frontend): add mature training route plans"
```

### Task 3: Restore Basic LoRA Full Form First

**Files:**
- Create: `frontend/source/src/basicLoraSchema.ts`
- Create: `frontend/source/src/matureTrainingPage.ts`
- Modify: `frontend/source/src/main.ts`
- Modify: `frontend/source/scripts/smoke-source-frontend.spec.mjs`

- [ ] **Step 1: Write failing Basic LoRA smoke**

Add a test:

```js
test("basic lora route renders full source form", async ({ page }) => {
  await page.goto("/lora/basic.html");
  await expect(page.locator("#mature-train-form")).toBeVisible();
  await expect(page.locator("#basic-pretrained-model")).toBeVisible();
  await expect(page.locator("#basic-train-data-dir")).toBeVisible();
  await expect(page.locator("#basic-output-dir")).toBeVisible();
  await expect(page.locator("#basic-network-dim")).toBeVisible();
  await expect(page.locator("#basic-preview-code")).toContainText('model_train_type = "lora-basic"');
});
```

Run:

```powershell
cd frontend\source
npx playwright test scripts/smoke-source-frontend.spec.mjs -g "basic lora route renders full source form"
```

Expected: fails because `/lora/basic.html` still renders the compatibility template.

- [ ] **Step 2: Create Basic LoRA schema module**

Create `frontend/source/src/basicLoraSchema.ts` with these sections:

```ts
import { defineTrainingRow, defineTrainingSection, defineTrainingSections, type TrainingSectionSpec } from "./trainingRenderer";

export interface BasicLoraForm {
  [key: string]: unknown;
  pretrained_model_name_or_path: string;
  train_data_dir: string;
  reg_data_dir: string;
  resolution: string;
  output_name: string;
  output_dir: string;
  save_every_n_epochs: number;
  max_train_epochs: number;
  train_batch_size: number;
  unet_lr: string;
  text_encoder_lr: string;
  lr_scheduler: "cosine" | "cosine_with_restarts" | "constant" | "constant_with_warmup";
  lr_warmup_steps: number;
  lr_scheduler_num_cycles: number;
  optimizer_type: "AdamW8bit" | "Lion";
  enable_preview: boolean;
  sample_prompts: string;
  sample_sampler: string;
  sample_every_n_epochs: number;
  network_weights: string;
  network_dim: number;
  network_alpha: number;
  shuffle_caption: boolean;
  keep_tokens: number;
  mixed_precision: "no" | "fp16" | "bf16";
  no_half_vae: boolean;
  xformers: boolean;
  cache_latents: boolean;
}

export const basicLoraDefaults: BasicLoraForm = {
  pretrained_model_name_or_path: "./sd-models/model.safetensors",
  train_data_dir: "./train/aki",
  reg_data_dir: "",
  resolution: "512,512",
  output_name: "aki",
  output_dir: "./output",
  save_every_n_epochs: 2,
  max_train_epochs: 10,
  train_batch_size: 1,
  unet_lr: "1e-4",
  text_encoder_lr: "1e-5",
  lr_scheduler: "cosine_with_restarts",
  lr_warmup_steps: 0,
  lr_scheduler_num_cycles: 1,
  optimizer_type: "AdamW8bit",
  enable_preview: false,
  sample_prompts: "(masterpiece, best quality:1.2), 1girl, solo",
  sample_sampler: "euler_a",
  sample_every_n_epochs: 2,
  network_weights: "",
  network_dim: 32,
  network_alpha: 32,
  shuffle_caption: true,
  keep_tokens: 0,
  mixed_precision: "fp16",
  no_half_vae: false,
  xformers: true,
  cache_latents: true,
};

export const basicLoraSections: TrainingSectionSpec<BasicLoraForm>[] = defineTrainingSections([
  defineTrainingSection("Model", [
    { kind: "text", key: "pretrained_model_name_or_path", id: "basic-pretrained-model", label: "pretrained_model_name_or_path", role: "file" },
  ]),
  defineTrainingSection("Dataset", [
    { kind: "text", key: "train_data_dir", id: "basic-train-data-dir", label: "train_data_dir", role: "folder" },
    { kind: "text", key: "reg_data_dir", id: "basic-reg-data-dir", label: "reg_data_dir", role: "folder" },
    { kind: "text", key: "resolution", id: "basic-resolution", label: "resolution" },
  ]),
  defineTrainingSection("Output", [
    { kind: "text", key: "output_name", id: "basic-output-name", label: "output_name" },
    { kind: "text", key: "output_dir", id: "basic-output-dir", label: "output_dir", role: "folder" },
    { kind: "number", key: "save_every_n_epochs", id: "basic-save-every-n-epochs", label: "save_every_n_epochs", min: 1 },
  ]),
  defineTrainingSection("Training", [
    defineTrainingRow([
      { kind: "number", key: "max_train_epochs", id: "basic-epochs", label: "max_train_epochs", min: 1 },
      { kind: "number", key: "train_batch_size", id: "basic-train-batch-size", label: "train_batch_size", min: 1 },
    ]),
    defineTrainingRow([
      { kind: "text", key: "unet_lr", id: "basic-unet-lr", label: "unet_lr" },
      { kind: "text", key: "text_encoder_lr", id: "basic-text-encoder-lr", label: "text_encoder_lr" },
    ]),
    { kind: "select", key: "lr_scheduler", id: "basic-lr-scheduler", label: "lr_scheduler", options: ["cosine", "cosine_with_restarts", "constant", "constant_with_warmup"] },
    { kind: "number", key: "lr_scheduler_num_cycles", id: "basic-lr-scheduler-num-cycles", label: "lr_scheduler_num_cycles", min: 1, visibleWhen: { key: "lr_scheduler", equals: "cosine_with_restarts" } },
    { kind: "select", key: "optimizer_type", id: "basic-optimizer", label: "optimizer_type", options: ["AdamW8bit", "Lion"] },
  ]),
  defineTrainingSection("Network", [
    { kind: "text", key: "network_weights", id: "basic-network-weights", label: "network_weights", role: "file" },
    defineTrainingRow([
      { kind: "number", key: "network_dim", id: "basic-network-dim", label: "network_dim", min: 8, max: 256, step: 8 },
      { kind: "number", key: "network_alpha", id: "basic-network-alpha", label: "network_alpha", min: 1 },
    ]),
  ]),
  defineTrainingSection("Caption", [
    { kind: "checkbox", key: "shuffle_caption", id: "basic-shuffle-caption", label: "shuffle_caption" },
    { kind: "number", key: "keep_tokens", id: "basic-keep-tokens", label: "keep_tokens", min: 0, max: 255 },
  ]),
  defineTrainingSection("Preview", [
    { kind: "checkbox", key: "enable_preview", id: "basic-enable-preview", label: "enable_preview" },
    { kind: "textarea", key: "sample_prompts", id: "basic-sample-prompts", label: "sample_prompts", visibleWhen: { key: "enable_preview", equals: true } },
    { kind: "select", key: "sample_sampler", id: "basic-sample-sampler", label: "sample_sampler", options: ["ddim", "pndm", "lms", "euler", "euler_a", "heun"] },
    { kind: "number", key: "sample_every_n_epochs", id: "basic-sample-every-n-epochs", label: "sample_every_n_epochs", min: 1 },
  ]),
  defineTrainingSection("Performance", [
    { kind: "select", key: "mixed_precision", id: "basic-mixed-precision", label: "mixed_precision", options: ["no", "fp16", "bf16"] },
    { kind: "checkbox", key: "no_half_vae", id: "basic-no-half-vae", label: "no_half_vae" },
    { kind: "checkbox", key: "xformers", id: "basic-xformers", label: "xformers" },
    { kind: "checkbox", key: "cache_latents", id: "basic-cache-latents", label: "cache_latents" },
  ]),
]);
```

- [ ] **Step 3: Create a generic mature form page**

Create `frontend/source/src/matureTrainingPage.ts` modeled on `anima.ts` with:

- reactive form from route defaults
- `payload()` adding `model_train_type`
- `renderTrainingSchemaSections`
- `renderParameterPreview(previewToml(payload()), "basic-preview-code")`
- save/load/reset/export/import/run controls
- status and submitted task links

Use storage key:

```ts
const MATURE_TRAINING_STORAGE_KEY = "sd-trainer-source-mature-training-configs";
```

- [ ] **Step 4: Route Basic LoRA into the full form**

Modify `frontend/source/src/main.ts`:

```ts
import { BasicLoraPage } from "./matureTrainingPage";

// before MatureTrainingPage compatibility route
route.path === "/lora/basic.html"
  ? h(BasicLoraPage, { route })
```

- [ ] **Step 5: Verify and commit**

```powershell
cd frontend\source
npm run check
npx playwright test scripts/smoke-source-frontend.spec.mjs -g "basic lora route renders full source form"
cd ..\..
git add frontend/source/src/basicLoraSchema.ts frontend/source/src/matureTrainingPage.ts frontend/source/src/main.ts frontend/source/scripts/smoke-source-frontend.spec.mjs
git commit -m "feat(frontend): restore basic lora source form"
```

### Task 4: Apply The Basic Pattern To Stable Diffusion, Flux, And Dreambooth

**Files:**
- Create: `frontend/source/src/stableDiffusionSchema.ts`
- Create: `frontend/source/src/fluxLoraSchema.ts`
- Create: `frontend/source/src/dreamboothSchema.ts`
- Modify: `frontend/source/src/matureTrainingPage.ts`
- Modify: `frontend/source/src/main.ts`
- Test: `frontend/source/scripts/smoke-source-frontend.spec.mjs`

- [ ] **Step 1: Add route smoke tests**

Add one test per route:

```js
test("stable diffusion route renders full source form", async ({ page }) => {
  await page.goto("/lora/master.html");
  await expect(page.locator("#mature-train-form")).toBeVisible();
  await expect(page.locator("#sd-pretrained-model")).toBeVisible();
  await expect(page.locator("#sd-train-data-dir")).toBeVisible();
  await expect(page.locator("#sd-preview-code")).toContainText('model_train_type = "lora-master"');
});

test("flux route renders full source form", async ({ page }) => {
  await page.goto("/lora/flux.html");
  await expect(page.locator("#mature-train-form")).toBeVisible();
  await expect(page.locator("#flux-pretrained-model")).toBeVisible();
  await expect(page.locator("#flux-train-data-dir")).toBeVisible();
  await expect(page.locator("#flux-preview-code")).toContainText('model_train_type = "flux-lora"');
});

test("dreambooth route renders full source form", async ({ page }) => {
  await page.goto("/dreambooth/index.html");
  await expect(page.locator("#mature-train-form")).toBeVisible();
  await expect(page.locator("#dreambooth-pretrained-model")).toBeVisible();
  await expect(page.locator("#dreambooth-train-data-dir")).toBeVisible();
  await expect(page.locator("#dreambooth-preview-code")).toContainText('model_train_type = "dreambooth"');
});
```

- [ ] **Step 2: Build schema modules by copying the Basic module structure**

For each route:

- Include at least Model, Dataset, Output, Training, Optimizer, Network/Architecture, Caption, Preview, Cache/Performance, Advanced.
- Use field keys from the corresponding `mikazuki/schema/*.ts`.
- Preserve backend-facing key names exactly.
- Add route-specific preview code IDs: `sd-preview-code`, `flux-preview-code`, `dreambooth-preview-code`.

- [ ] **Step 3: Register each route**

In `matureTrainingPage.ts`, export:

```ts
export const StableDiffusionPage = createMatureTrainingPage(stableDiffusionRouteSpec);
export const FluxLoraPage = createMatureTrainingPage(fluxLoraRouteSpec);
export const DreamboothPage = createMatureTrainingPage(dreamboothRouteSpec);
```

In `main.ts`, route them before the compatibility template.

- [ ] **Step 4: Verify and commit**

```powershell
cd frontend\source
npm run check
npm run smoke
cd ..\..
.\venv\Scripts\python.exe scripts\verify_frontend_source.py --require-built-output
git add frontend/source/src/stableDiffusionSchema.ts frontend/source/src/fluxLoraSchema.ts frontend/source/src/dreamboothSchema.ts frontend/source/src/matureTrainingPage.ts frontend/source/src/main.ts frontend/source/scripts/smoke-source-frontend.spec.mjs
git commit -m "feat(frontend): restore mature training source forms"
```

### Task 5: Visual Polish Pass

**Files:**
- Modify: `frontend/source/src/styles.css`
- Modify: `frontend/source/scripts/smoke-source-frontend.spec.mjs`
- Modify: `frontend/source/scripts/smoke-dist-frontend.spec.mjs`

- [ ] **Step 1: Add viewport smoke**

Add a Playwright test that checks no horizontal document overflow on key pages:

```js
for (const route of ["/lora/sd3.html", "/lora/basic.html", "/lora/master.html", "/lora/flux.html", "/dreambooth/index.html"]) {
  test(`training route has no horizontal overflow ${route}`, async ({ page }) => {
    await page.setViewportSize({ width: 1365, height: 900 });
    await page.goto(route);
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  });
}
```

- [ ] **Step 2: Apply visual rules**

In `styles.css`:

- Keep form fieldsets at `border-radius: 8px`.
- Use restrained neutral backgrounds.
- Keep right preview panel sticky only above tablet width.
- Ensure `.training-field-row` collapses to one column below 900px.
- Do not use decorative orb/gradient backgrounds.

- [ ] **Step 3: Verify and commit**

```powershell
cd frontend\source
npm run check
npm run smoke
git add frontend/source/src/styles.css frontend/source/scripts/smoke-source-frontend.spec.mjs frontend/source/scripts/smoke-dist-frontend.spec.mjs
git commit -m "style(frontend): polish source training pages"
```

### Task 6: Production Dist Update

**Files:**
- Modify generated files under `frontend/dist/`

- [ ] **Step 1: Rebuild and apply**

```powershell
cd frontend\source
npm run build
cd ..\..
.\venv\Scripts\python.exe scripts\sync_frontend_source_dist.py --apply --backup
.\venv\Scripts\python.exe scripts\verify_frontend_dist_matches_source.py
```

Expected:

```text
frontend dist matches source build
```

- [ ] **Step 2: Browser smoke production dist**

```powershell
cd frontend\source
npm run smoke:dist
```

Expected:

```text
3 passed
```

- [ ] **Step 3: Commit dist only**

```powershell
cd ..\..
git add frontend/dist
git diff --cached --name-only | powershell -Command "$input | Where-Object { $_ -notlike 'frontend/dist/*' } | ForEach-Object { throw \"unexpected staged path $_\" }"
git commit -m "chore(frontend): update production dist"
```

### Task 7: Final Acceptance Run

**Files:**
- No source files should change in this task.

- [ ] **Step 1: Run full gate**

```powershell
cd frontend\source
npm run check
npm run build
npm run smoke
npm run smoke:dist
cd ..\..
.\venv\Scripts\python.exe scripts\verify_frontend_source.py --require-built-output
.\venv\Scripts\python.exe scripts\sync_frontend_source_dist.py
.\venv\Scripts\python.exe scripts\verify_frontend_dist_matches_source.py
.\venv\Scripts\python.exe -m pytest tests\test_frontend_source.py tests\test_dataset_editor_api.py tests\test_tagger_progress_api.py tests\test_portable_packaging_scripts.py -q
```

- [ ] **Step 2: Verify acceptance labels**

Create a short PR comment or release note with:

```markdown
P0-A1 Source Ownership: PASS
P0-A2 Production Sync: PASS
P0-A3 Production Browser Smoke: PASS
P0-A4 Native Tag Editor: PASS
P0-A5 Classic Tag Editor Retirement: PASS
P0-A6 Anima Full Form: PASS
P0-A7 Mature Training Forms: PASS
P0-A8 Legacy Visual Parity: PASS
P0-A9 Backend Red Line: PASS
P0-A10 Verification Gate: PASS
P1-B1 Akiba-Familiar Layout: PASS
P1-B2 Better Than Old UX: PASS
P1-B3 Reviewable Dist: PASS
P1-B4 Interaction Parity: PASS
P1-B5 No Empty Public Pages: PASS
```

- [ ] **Step 3: Push**

```powershell
git push origin codex/frontend-source
```

---

## Review Notes

Do not treat generated `frontend/dist` as hand-reviewed source. Reviewers should inspect:

- `frontend/source/src/*.ts`
- `frontend/source/scripts/*.mjs`
- `scripts/verify_frontend_*.py`
- `tests/test_frontend_source.py`
- `tests/test_dataset_editor_api.py`
- `docs/design/*.md`

Then verify:

```powershell
.\venv\Scripts\python.exe scripts\verify_frontend_dist_matches_source.py
```

If it passes, the generated dist is reviewable by provenance instead of by eyeballing bundled assets.

## Self-Review

- Spec coverage: P0/P1/P2 labels map to tasks 1-7.
- Placeholder scan: no task contains open-ended "TBD" or "TODO".
- Type consistency: route plan names, file names, and preview code IDs are specified before use.
- Scope control: Basic LoRA is first full mature form; SD/Flux/Dreambooth follow the same route spec pattern after the first route proves the adapter.
