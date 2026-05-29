# Agent All-in-One Handoff: Native Tag Editor

## Project

Repository: `D:\ai\lora-scripts-next`

Active branch for this work: `editor`

This branch is intentionally separate from `main` because the native tag editor UI touches the trainer WebUI shell and can regress navigation, caching, and route behavior.

## Must Read First

Read these files before making changes:

- `doc/local/AGENT_INTERNAL.md`
- `doc/local/HANDOFF_DATASET_EDITOR_2026-05-29.md`
- `.cursor/rules/00-project-overview.mdc`
- `.cursor/rules/embedded-service-ports.mdc`
- `docs/repo-layout.md`
- `docs/portable-packaging-git-update.md`
- `docs/team/risk-memo.md`
- `docs/team/backlog-priorities.md`

## Hard Constraints

- Do not push this UI work directly to `main`.
- Do not run npm build for the current frontend work. Edit `frontend/dist/` directly.
- Do not change portable contract directory names or the portable launch chain unless explicitly requested.
- Do not delete or commit local HuggingFace lock files under `huggingface/hub/.locks/`.
- Old Gradio tag editor must remain opt-in only through `--enable-legacy-tageditor`.
- `/dataset-editor.html` is the standalone native editor fallback/debug page.
- `/native-tageditor.html` is the native editor embedded in the trainer shell.
- `/tageditor.html` is the classic/legacy tag editor page.
- Keep changes scoped to dataset/tag editor integration unless the user explicitly asks otherwise.

## Current Dev Server

Common command:

```powershell
python gui.py --dev --skip-prepare-environment --disable-tensorboard --disable-train-monitor --port 28182
```

Useful URLs:

- `http://127.0.0.1:28182/tagger.html`
- `http://127.0.0.1:28182/tageditor.html`
- `http://127.0.0.1:28182/native-tageditor.html`
- `http://127.0.0.1:28182/dataset-editor.html`
- `http://127.0.0.1:28182/other/settings.html`

## What This Branch Contains

- Native dataset/tag editor backend API in `mikazuki/dataset_editor.py`.
- Native editor frontend in `frontend/dist/dataset-editor.html` and `frontend/dist/assets/dataset-editor.*`.
- Trainer-embedded native editor entry in `frontend/dist/assets/dataset-editor-entry.js`.
- Separate navigation entries:
  - Classic Tag Editor: `经典标签编辑`, `/tageditor.md`
  - Native Tag Editor: `原生标签编辑`, `/native-tageditor.html`
- Dataset editor tagging controls for local/API tagging, tag/natural-language caption mode, model selection, conflict handling, and settings integration.
- Local tagger model storage helpers in `mikazuki/tagger/local_models.py`.
- Preferred local tagger model layout:
  - `tagger-models/wd14/<model-key>/`
  - `tagger-models/vlm/<model-key>/`
  - Legacy flat `tagger-models/<model-key>/` remains compatible.
- Portable packaging updates to create/copy the tagger model directories.
- Cache-control workaround in `mikazuki/app/application.py` for patched dist core assets.
- Regression tests for route/sidebar JSON parsing and Chinese nav labels.

## Important Recent Bug

The VuePress app bundle `frontend/dist/assets/app.547295de.js` contains theme sidebar data as:

```js
const WE=JSON.parse(`...`)
```

Manual edits previously broke this JSON and then corrupted Chinese menu text. The current fix stores that JSON with ASCII-only `\uXXXX` escapes so runtime text still renders Chinese while file writes are less likely to corrupt encoding.

If navigation becomes 404-like, stuck on `Loading...`, or shows mojibake, first inspect and parse this `WE=JSON.parse(...)` block.

Relevant test:

```powershell
python -m pytest tests\test_dataset_editor_api.py::test_vuepress_theme_sidebar_json_stays_parseable -q
```

## Verification Commands

Run before claiming the branch is healthy:

```powershell
python -m pytest tests\test_dataset_editor_api.py tests\test_tagger_progress_api.py tests\test_portable_packaging_scripts.py -q
```

Last known result before this handoff:

```text
47 passed, 4 warnings
```

Browser smoke checks:

- Open `/tagger.html`, confirm no 404 and sidebar Chinese is readable.
- Open `/native-tageditor.html`, confirm it uses the trainer shell and native editor.
- Open `/dataset-editor.html`, confirm standalone fallback still loads.
- Open `/other/settings.html`, confirm tagger API settings are present.

## Known Local Noise

Do not commit these runtime files:

- `huggingface/hub/.locks/models--SmilingWolf--wd-convnext-tagger-v3/*.lock`
- `huggingface/hub/.locks/models--SmilingWolf--wd-v1-4-moat-tagger-v2/*.lock`

## Suggested Next Work

1. Continue visual QA of `/native-tageditor.html` in the trainer shell.
2. Use a real dataset to test scan, thumbnails, selection, batch tagging, save, undo, and redo.
3. Improve native editor UI carefully, one small change at a time, with browser checks after each change.
4. Keep the classic editor and native editor separate in navigation.
5. Avoid broad frontend shell rewrites until the current editor flow is stable.

