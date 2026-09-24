# Native Path Picker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a configurable native/web path picker policy that defaults to native selection when the training host supports it.

**Architecture:** Store the picker policy in the existing `ui-configs` browser preference object. Extend the shared `useServerPathPick` composable to dispatch to the existing native endpoint or open the existing web dialog, keeping every current picker consumer on one code path.

**Tech Stack:** Vue 3, TypeScript, Element Plus, Vitest, localStorage, existing FastAPI picker endpoints.

---

### Task 1: Path Picker Preference

**Files:**
- Create: `frontend/src/utils/pathPickerPreference.ts`
- Create: `frontend/src/utils/pathPickerPreference.test.ts`

- [ ] **Step 1: Write failing preference tests**

Cover the default `auto` value, all three valid stored values, malformed
`ui-configs`, invalid values, and preservation of unrelated settings when
writing.

- [ ] **Step 2: Run the focused tests**

Run: `npm test -- pathPickerPreference.test.ts`

Expected: FAIL because the preference module does not exist.

- [ ] **Step 3: Implement the preference helper**

Export:

```ts
export type PathPickerPreference = "auto" | "native" | "web"
export function readPathPickerPreference(): PathPickerPreference
export function writePathPickerPreference(value: PathPickerPreference): void
```

Use `UI_CONFIGS_KEY`, validate values explicitly, default to `auto`, and
preserve existing `ui-configs` properties when writing.

- [ ] **Step 4: Re-run the focused tests**

Run: `npm test -- pathPickerPreference.test.ts`

Expected: PASS.

### Task 2: Unified Picker Dispatch

**Files:**
- Modify: `frontend/src/composables/useServerPathPick.ts`
- Create: `frontend/src/composables/useServerPathPick.test.ts`
- Modify: `frontend/src/api/schemas.ts`
- Modify: `mikazuki/utils/tk_window.py`
- Modify: `mikazuki/app/api.py`
- Create: `tests/test_native_picker.py`

- [ ] **Step 1: Write failing composable tests**

Mock the native picker API and preference helper. Verify:

```ts
// web: opens PathPickerDialog without calling the native API
// auto/native success: resolves the native path without opening the dialog
// CANCELLED: resolves null without opening the dialog
// GUI_PICKER_UNAVAILABLE: opens the web dialog
// unexpected native failure: opens the web dialog
```

- [ ] **Step 2: Run the focused tests**

Run: `npm test -- useServerPathPick.test.ts`

Expected: FAIL because the composable always opens the web dialog.

- [ ] **Step 3: Type native picker failures**

Add a native picker result/error shape in `frontend/src/api/schemas.ts` while
retaining the existing `/api/pick_file` endpoint.

- [ ] **Step 4: Implement dispatch and fallback**

Keep the returned composable interface unchanged. Map `PathBrowserMode` `file`
to backend picker type `model-file`; map `folder` to `folder`. Detect
`ApiError.response?.data.code`, treat `CANCELLED` as cancellation, and route
other failures to the existing web dialog state.

Raise a dedicated backend exception when tkinter fails at runtime so the API can
return `NATIVE_PICKER_ERROR`. Keep an empty picker result reserved for genuine
user cancellation.

- [ ] **Step 5: Re-run the focused tests**

Run: `npm test -- useServerPathPick.test.ts`

Expected: PASS.

### Task 3: Settings Control

**Files:**
- Modify: `frontend/src/pages/SettingsContainerPage.vue`
- Create: `frontend/src/pages/SettingsContainerPage.test.ts`
- Modify: `frontend/src/i18n/messages/zh-CN.ts`
- Modify: `frontend/src/i18n/messages/en-US.ts`

- [ ] **Step 1: Write failing settings tests**

Mount the UI settings tab and verify the segmented control reflects the stored
value, Save persists the selected value, and Reset restores `auto`.

- [ ] **Step 2: Run the focused tests**

Run: `npm test -- SettingsContainerPage.test.ts`

Expected: FAIL because the picker control is absent.

- [ ] **Step 3: Add the settings control**

Add `path_picker` to the settings form through the preference helper. Render
three segmented buttons for `auto`, `native`, and `web`, with localized label
and hint. Save and reset must update both reactive state and local storage.

- [ ] **Step 4: Re-run the focused tests**

Run: `npm test -- SettingsContainerPage.test.ts`

Expected: PASS.

### Task 4: Regression Verification

**Files:**
- Verify only.

- [ ] **Step 1: Run picker and settings tests**

Run:

```powershell
npm test -- pathPickerPreference.test.ts useServerPathPick.test.ts SettingsContainerPage.test.ts SchemaField.test.ts
```

Expected: PASS.

- [ ] **Step 2: Run frontend type checking**

Run: `npm run typecheck`

Expected: PASS.

- [ ] **Step 3: Run frontend build**

Run: `npm run build`

Expected: PASS.

- [ ] **Step 4: Check the diff**

Run: `git diff --check`

Expected: no whitespace errors.

- [ ] **Step 5: Leave changes uncommitted**

Report the isolated branch and worktree path. Do not commit, push, or create a
pull request until requested.
