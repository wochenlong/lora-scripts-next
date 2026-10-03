# Engine List Implementation Plan

**Goal:** Implement the approved compact, searchable, user-ordered engine list.
**Architecture:** Keep lifecycle APIs intact; isolate browser-local ordering in
an engine helper and render the filtered view in the existing settings page.
**Stack:** Vue 3, TypeScript, Element Plus icons, Vitest.

- [x] Add failing tests for order normalization, persistence, filtered moves,
  search/status filters, and unchanged training preferences.
- [x] Implement `frontend/src/engines/listPreferences.ts`, with guarded storage
  and pure ID-based ordering helpers.
- [x] Add component tests for controls and drag events before wiring the page.
- [x] Update `EnginesSettingsPage.vue`, `anima-fast.css`, and both locales:
  compact rows, explicit states, search/filter toolbar, drag handle, move menu,
  restore order, and metadata in the existing detail dialog.
- [x] Run focused tests, then `npm run check` in `frontend`.
- [x] Start a free-port Vite server and inspect real desktop/mobile GUI;
  verify drag, refresh persistence, filtering and safe lifecycle controls.

Acceptance follows the approved specification in
`docs/superpowers/specs/2026-10-01-engine-list-design.md`.
Do not install/uninstall engines or change the product default during testing.

## Results

- `npm run check`: 44 files / 278 tests passed; typecheck and build passed.
  Two pre-existing EngineStatusBar lint warnings and existing build warnings remain.
- Browser: Anima Fast dragged before Kohya; reload retained order and did not
  change the default engine. Keyboard move restored the original order.
- Installed filter showed Anima Fast and DiffSynth on the local server.
- Desktop and 390px layouts inspected, without horizontal overflow on mobile.
- Dark theme inspected and badge contrast improved; light theme restored.
- Preview: http://127.0.0.1:5173/settings/engines (backend on port 28000).
- No engine install/uninstall or training performed.
- Restarted the Vite service and opened a new browser tab: saved order restored.
  Persistence is per browser profile and origin, not shared across ports/devices.
- Independent review identified stale pointer targets after dragging back to the
  origin. Reproduced with a failing test and fixed the activation threshold.
  Added return/cancel/lost-capture and filtered-page shrink regression coverage.
- Python package-boundary regression: four tests passed.
- Follow-up: fixed five-item pagination; seven-engine test fixtures cover
  page slicing, global search, and moving from page two to the global top.
  The live five-engine catalog hides pagination as intended.
