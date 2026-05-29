# Frontend Source-of-Truth Recovery Plan

Status: draft  
Branch context: `editor`  
Created: 2026-05-30

## Progress

- 2026-05-30: Added `scripts/patch_frontend_dist.py` to reapply and validate the current native tag editor dist patches. The script covers the VuePress app route mapping, sidebar JSON, native page-data chunk, native page preload contract, settings cache-bust URL, and SSR sidebar snapshots.
- 2026-05-30: The first script run found older SSR pages that still exposed the single `标签编辑` sidebar entry. Those snapshots were updated to split `经典标签编辑` and `原生标签编辑`, with regression coverage in `tests/test_dataset_editor_api.py`.
- 2026-05-30: Expanded the patch script to also cover the older Anima/SD3 dist text patches documented in `frontend/VENDOR.md`, including the app sidebar, `sd3` render chunk, `sd3` page-data chunk, and `lora/sd3.html` SSR copy.
- 2026-05-30: Created `codex/frontend-source` with `frontend/source`, a minimal Vite + Vue 3 + TypeScript shell. It declares public compatibility routes in `src/routes.json`, builds static output to `build/frontend-source-dist`, writes HTML route aliases, and has `scripts/verify_frontend_source.py` for source/build contract checks.
- 2026-05-30: Started incremental migration by adding a source-owned `/other/settings.html` page. It reads and writes the existing `ui-configs` and `sd-trainer-ui-advanced-links` localStorage keys, includes native tag editor API settings, masks the API key field, and is covered by `tests/test_frontend_source.py`.
- 2026-05-30: Added low-risk Anima source route scaffolding for `/lora/sd3.html` and `/lora/anima-finetune.html`. The source app now records the stable route, `model_train_type`, schema file, and backend entrypoint contracts without touching the mature SD/Flux training pages.
- 2026-05-30: Migrated the native tag editor entry into `frontend/source`. The source app owns `/native-tageditor.html`, packages the native editor JS/CSS assets into the source build output, and adds a Playwright browser smoke script for the generated source frontend.
- 2026-05-30: Migrated the first tagger source route. `/tagger.html` now has a source-owned form scaffold and packages the tagger progress dock asset into the source build output while preserving the existing `/api/tagger/*` and `/api/interrogate` backend contracts.
- 2026-05-30: Removed the source frontend dependency on the copied `tagger-progress.js` asset. The source tagger page now owns its form state, progress dock, status polling, prefetch, start, cancel, and reset calls in TypeScript.
- 2026-05-30: Routed the source `/dataset-editor.html` fallback/debug page to the same native editor source entry as `/native-tageditor.html`, preserving the separate public URLs while avoiding a placeholder fallback in the generated source frontend.

## Background

SD Trainer Next currently serves the trainer WebUI from `frontend/dist/`. That directory is a vendored prebuilt VuePress/Vue application, originally sourced from `hanamizuki-ai/lora-gui-dist`.

Public upstream history suggests the trainer frontend was published to the main Akegarasu repository as a dist submodule from its first visible integration:

- `Akegarasu/lora-scripts` first added `frontend` as a submodule in commit `8ea34ab` on 2023-04-23.
- That submodule pointed to `https://github.com/hanamizuki-ai/lora-gui-dist`.
- The visible history of `hanamizuki-ai/lora-gui-dist` contains prebuilt `dist/` files from its earliest commits, not a source project with `package.json`, `src/`, or VuePress config.

As a result, this fork currently patches compiled assets directly. This has worked for targeted fixes, but it is not a healthy long-term maintenance model.

## Problem

Important UI behavior is hidden inside minified build artifacts such as:

- `frontend/dist/assets/app.547295de.js`
- hashed page-data chunks under `frontend/dist/assets/`
- SSR HTML snapshots under `frontend/dist/**/*.html`

This creates recurring maintenance risks:

- Route changes require hand-editing minified bundles.
- Sidebar changes must often be patched in both JS runtime data and SSR HTML.
- Encoding mistakes can corrupt Chinese text.
- Cache-busting and hashed asset names make fixes fragile.
- Multiple agents editing `frontend/dist/` can easily conflict.
- A simple search on a minified single-line bundle can produce huge tool output and destabilize agent sessions.

The native tag editor work exposed this sharply: `/native-tageditor.html` returned HTTP 200 and loaded the native editor entry script, but VuePress still rendered the classic tag editor because `v-native-tageditor` was mapped to the classic `tageditor.html.*.js` page-data chunk inside `app.547295de.js`.

## Goal

Create a maintainable frontend source-of-truth owned by this project.

In plain terms: future UI changes should be made in source files, then built into `frontend/dist/`, instead of manually patching compiled JavaScript and HTML.

## Non-Goals

This project must not become a broad UI rewrite while the native tag editor is still being stabilized.

Do not do the following in the first phase:

- Replace the trainer WebUI in `main`.
- Rewrite all training pages at once.
- Change portable contract directories or launch scripts.
- Break existing `frontend/dist/` serving behavior.
- Remove the classic editor before the native editor is proven stable.

## Recommended Strategy

Use a staged recovery rather than a big-bang rewrite.

### Phase 0: Stabilize Current Editor Work

Finish the native tag editor on the `editor` branch first.

Required guardrails:

- Keep `/dataset-editor.html` as standalone fallback/debug.
- Keep `/native-tageditor.html` as the trainer-embedded native editor.
- Keep `/tageditor.html` as the classic editor.
- Keep direct `frontend/dist/` patches small and test-covered.
- Keep the current regression tests for native route mapping, sidebar JSON, and settings behavior.

Exit criteria:

- Native editor loads reliably without falling back to the classic editor.
- Real dataset QA covers scan, thumbnails, selection, batch edit/tagging, save, undo, and redo.
- The branch has no known 404/mojibake/cache regressions.

### Phase 1: Make Dist Patching Reproducible

Before building a new frontend source tree, script the existing dist patches so they are repeatable.

Deliverables:

- A patch script under `scripts/`, for example `scripts/patch_frontend_dist.py`.
- The script should:
  - detect expected input assets and hashes,
  - patch route mappings,
  - patch sidebar/theme data,
  - patch SSR HTML where needed,
  - validate that JSON blocks still parse,
  - fail loudly when upstream dist layout changes.
- Tests should assert the final observable behavior, not just string replacement.

This phase reduces risk immediately and gives the future frontend rebuild a baseline to compare against.

### Phase 2: Create a Parallel Source Frontend Branch

Create a separate branch, suggested name:

```text
frontend-source
```

or:

```text
app-shell-rebuild
```

This branch should not block the `editor` branch.

Initial source project requirements:

- Use a modern, boring stack, preferably Vite + Vue 3 + TypeScript.
- Reuse the existing trainer visual language where practical.
- Keep output compatible with the current FastAPI static serving model.
- Produce a `dist` folder that can be served by the existing backend without npm at runtime.
- Keep build tooling out of portable runtime requirements.

Recommended early pages:

- Trainer shell/sidebar.
- Settings page.
- Native tag editor page.
- Minimal compatibility routes for existing links.

Do not migrate all training pages in the first pass unless necessary.

### Phase 3: Compatibility Layer

The rebuilt frontend must preserve current public routes or provide backend redirects.

Important routes include:

- `/`
- `/tagger.html`
- `/tageditor.html`
- `/native-tageditor.html`
- `/dataset-editor.html`
- `/tensorboard.html`
- `/other/settings.html`
- `/lora/*`

The source frontend should define routes explicitly in source, with tests covering generated output.

### Phase 4: Incremental Migration

Once the new app shell is buildable and served successfully, migrate one page family at a time.

Suggested order:

1. Settings and utility pages.
2. Native tag editor.
3. Tagger page and tagging model settings.
4. Training pages only after shell and settings are stable.

Each migrated area should include:

- route tests,
- visual smoke checks,
- compatibility checks for old links,
- portable package validation where relevant.

### Phase 5: Retire Manual Dist Surgery

When the source frontend can generate the necessary production `dist`, stop hand-editing minified bundles.

Retirement criteria:

- No required behavior depends on manual edits to `app.*.js`.
- Sidebar and route data come from source files.
- Settings schema and sensitive-field behavior are source-owned.
- Native editor entry is source-owned.
- Build output is reproducible from a clean checkout.

## Investigation Tasks for the Next Agent

The next Codex/agent should start with evidence gathering, not implementation.

Checklist:

- Read `frontend/VENDOR.md`.
- Read `agent_allinone.md`.
- Read this document.
- Inspect `mikazuki/app/application.py` static serving behavior.
- Inspect existing tests in `tests/test_dataset_editor_api.py`.
- Confirm current branch state with:

```powershell
git status --short --untracked-files=all
git log --oneline --decorate -5
```

- Confirm upstream frontend history if needed:

```powershell
git fetch akegarasu main
git show 8ea34ab3d8e5289b09f6977728979bd704fa806b:.gitmodules
git clone --bare --filter=blob:none https://github.com/hanamizuki-ai/lora-gui-dist.git ../_tmp_lora_gui_dist_bare
git --git-dir=../_tmp_lora_gui_dist_bare ls-tree -r --name-only 62b5805
```

Clean up temporary clones after investigation.

## Risks

- Rebuilding the frontend source tree can accidentally regress mature training forms.
- Users rely on current URLs and portable packaging behavior.
- The existing WebUI has many hidden SSR/hydration assumptions.
- Multiple frontend efforts can conflict if they all edit `frontend/dist/` directly.
- A full rewrite before the native editor is stable would multiply risk.

## Recommendation

Do not start the full frontend source recovery until the native tag editor reaches a stable milestone.

After that, create a separate branch and treat this as an engineering infrastructure project:

1. Make current dist patches reproducible.
2. Build a parallel source-owned shell.
3. Migrate routes incrementally.
4. Retire manual dist patching only after the generated frontend passes compatibility tests.

This lets the project stop depending on unavailable upstream frontend source without jeopardizing the current editor work.
