# Dataset Workflow Implementation Plan

> **For agentic workers:** Use subagent-driven-development or executing-plans. Preserve existing uncommitted dataset UI changes.

**Goal:** Connect managed datasets to preview, tagging and editing without accidental navigation or data loss.

**Architecture:** Keep management as horizontal folder rows. Add a read-only contents API and detail view, share a managed folder picker, and explicitly clear editor session state on unload. Mutations use existing sandbox, operation locks and training guards.

**Tech Stack:** Vue, TypeScript, Element Plus, FastAPI, Vitest, pytest.

## Tasks

- [x] Backend: test and implement `POST /datasets/{name}/rename` and `GET /datasets/{name}/contents?path=`.
  - Reject traversal, collisions, unsafe links and in-use mutations.
  - Preserve files and return normalized server paths.
- [x] Editor: test session unload then implement it; confirm drafts before clearing, invalidate late scans, do not delete disk files.
- [x] Shared picker: test folder selection; list managed datasets and nested directories; retain external path input.
- [x] Detail: test navigation from management; add preview, subdirectories, upload and explicit tool links.
  - Reuse copy preprocessing for transparent-to-white output; preserve source.
- [x] Management: add rename menu action with busy/error handling and retain trash-based deletion.
- [x] Verification: frontend checks, targeted backend tests, live populated dataset workflow and independent review.

## Verification Results

- Frontend `npm run check`: 56 test files, 328 tests passed; typecheck, lint and build passed with existing warnings.
- Backend detail, trash and SPA route tests: 67 passed, 1 skipped. A repeat run passed after transient Windows socket permission errors (WinError 10013).
- Broader backend run: 100 passed, 4 failed, 1 skipped; the four failures required Windows symlink privileges (WinError 1314).
- Live GUI: nested folder selection, privacy-controlled preview, editor load/unload, tagger path selection and management menu checked.
- Live API: paired image/caption deletion, rename, trash ownership retargeting, restore and transparent-to-white copy checked.
- Temporary acceptance datasets and their specific trash batches removed; user datasets preserved.
- Independent re-review found no remaining blocking issue.

## Verification Commands

```powershell
npx vitest run src/pages/DatasetManagePage.test.ts src/composables/useDatasetEditorSession.test.ts
npm run check
D:\ai\lora-scripts-next\venv\Scripts\python.exe -m pytest tests/test_datasets_api.py -q
```

Use temporary acceptance data only. Never publish or alter the user's own images during verification.
