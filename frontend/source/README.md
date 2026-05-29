# Source-Owned Frontend Shell

This directory is the Phase 2 source-of-truth recovery scaffold. It does not
replace the production `frontend/dist/` yet.

## Purpose

- Keep route and sidebar data in source files.
- Build static HTML/CSS/JS that can be served by the existing FastAPI
  `StaticFiles` setup.
- Prove the source-to-dist path before migrating mature trainer pages.

## Commands

```powershell
cd frontend\source
npm install
npm run check
npm run build
```

The build writes to:

```text
build/frontend-source-dist/
```

You can point the backend at that generated output for smoke checks:

```powershell
$env:MIKAZUKI_FRONTEND_DIST='build/frontend-source-dist'
python gui.py --dev --skip-prepare-environment --disable-tensorboard --disable-train-monitor --port 28182
```

## Verification

```powershell
python scripts\verify_frontend_source.py --require-built-output
python -m pytest tests\test_frontend_source.py -q
```

## Current Scope

The current source app is intentionally a minimal shell with compatibility
routes. It is not a replacement for the trainer forms yet.

Migrating real pages should happen incrementally after the native tag editor
is stable and each migrated route has route, visual, and portable checks.
