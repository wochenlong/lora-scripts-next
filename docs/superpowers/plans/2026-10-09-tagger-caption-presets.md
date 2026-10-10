# Tagger Caption Presets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Store natural-language Tagger prompt templates in `user_data/presets` through the existing user preset API, including one-time migration from the legacy browser entry.

**Architecture:** Add a focused `captionPresets` module that owns record validation, API payload mapping, CRUD operations, and idempotent legacy migration. `TaggerPage.vue` consumes that module and keeps only view state, while the built-in default remains frontend-owned and immutable.

**Tech Stack:** Vue 3, TypeScript, Vitest, Vue Test Utils, Element Plus, existing `/api/user-data/presets` client.

---

### Task 1: Define And Test The Caption Preset Adapter

**Files:**
- Create: `frontend/src/tagger/captionPresets.ts`
- Create: `frontend/src/tagger/captionPresets.test.ts`
- Use: `frontend/src/api/userPresets.ts`

- [ ] **Step 1: Write failing adapter tests**

Create tests that inject a mocked `userPresetsApi`-shaped client and assert:

```ts
expect(client.list).toHaveBeenCalledWith("tagger-caption")
expect(await service.list()).toEqual([
  { id: "preset-1", name: "Portrait", prompt: "Describe the portrait.", language: "en" },
])
expect(client.create).toHaveBeenCalledWith({
  name: "Portrait",
  train_type: "tagger-caption",
  config: { prompt: "Describe the portrait.", language: "en" },
})
expect(client.update).toHaveBeenCalledWith("preset-1", {
  name: "Portrait",
  config: { prompt: "Updated prompt.", language: "zh-CN" },
})
expect(client.remove).toHaveBeenCalledWith("preset-1")
```

Also assert malformed records whose `config.prompt` or `config.language` is not a string are omitted.

- [ ] **Step 2: Run the adapter test and verify RED**

Run:

```powershell
cd frontend
npx vitest run src/tagger/captionPresets.test.ts
```

Expected: FAIL because `captionPresets.ts` and its exported service do not exist.

- [ ] **Step 3: Implement the minimal adapter**

Define:

```ts
export const TAGGER_CAPTION_TRAIN_TYPE = "tagger-caption"

export interface CaptionPreset {
  id: string
  name: string
  prompt: string
  language: string
}

export interface CaptionPresetInput {
  name: string
  prompt: string
  language: string
}

export function createCaptionPresetService(client = userPresetsApi) {
  return {
    async list(): Promise<CaptionPreset[]> {
      return (await client.list(TAGGER_CAPTION_TRAIN_TYPE)).flatMap(mapCaptionPreset)
    },
    async create(input: CaptionPresetInput): Promise<CaptionPreset> {
      return requireCaptionPreset(await client.create(toCreatePayload(input)))
    },
    async update(id: string, input: CaptionPresetInput): Promise<CaptionPreset> {
      return requireCaptionPreset(await client.update(id, toUpdatePayload(input)))
    },
    async remove(id: string): Promise<void> {
      await client.remove(id)
    },
  }
}
```

Implement `mapCaptionPreset`, `requireCaptionPreset`, `toCreatePayload`, and
`toUpdatePayload` as private helpers. `mapCaptionPreset` returns an empty array
for malformed records and a one-element array for valid records;
`requireCaptionPreset` throws `Error("Invalid tagger caption preset")` when that
array is empty. Payload helpers copy `name`, `prompt`, and `language` exactly,
with `train_type` included only on create.

- [ ] **Step 4: Run the adapter test and verify GREEN**

Run:

```powershell
npx vitest run src/tagger/captionPresets.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit the adapter**

```powershell
git add frontend/src/tagger/captionPresets.ts frontend/src/tagger/captionPresets.test.ts
git commit -m "feat(tagger): add caption preset adapter"
```

### Task 2: Add Idempotent Legacy Migration

**Files:**
- Modify: `frontend/src/tagger/captionPresets.ts`
- Modify: `frontend/src/tagger/captionPresets.test.ts`

- [ ] **Step 1: Write failing migration tests**

Cover these behaviors with a fake `Storage` and mocked client:

```ts
localStorage.setItem("nt.tagger.captionTemplates", JSON.stringify({
  "custom-one": "Legacy prompt one",
  "custom-two": "Legacy prompt two",
}))
```

Assert successful migration creates two records with deterministic descriptions such as:

```ts
description: "legacy-tagger-caption:custom-one"
```

and removes the browser key only after both creates resolve. Assert a rejected second create leaves the original browser JSON untouched. Assert an existing server record with the same marker skips creation and still permits cleanup once all legacy entries are accounted for. Assert malformed JSON and non-string/blank prompt values never create records.

- [ ] **Step 2: Run migration tests and verify RED**

Run:

```powershell
npx vitest run src/tagger/captionPresets.test.ts
```

Expected: FAIL because migration is not implemented.

- [ ] **Step 3: Implement migration**

Add constants and a method:

```ts
export const LEGACY_CAPTION_TEMPLATES_KEY = "nt.tagger.captionTemplates"
const LEGACY_MARKER_PREFIX = "legacy-tagger-caption:"

async migrateLegacy(existing: UserPreset[], storage: Storage = localStorage): Promise<CaptionPreset[]>
```

Parse only plain-object entries with non-empty string prompts. Use each legacy key to build the marker, skip records already carrying that exact marker, create missing records as `tagger-caption` presets with language `"en"`, and call `storage.removeItem` only after all valid entries are imported or already present. Let create failures reject without modifying the stored JSON.

- [ ] **Step 4: Run migration tests and verify GREEN**

Run:

```powershell
npx vitest run src/tagger/captionPresets.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit migration**

```powershell
git add frontend/src/tagger/captionPresets.ts frontend/src/tagger/captionPresets.test.ts
git commit -m "feat(tagger): migrate legacy caption templates"
```

### Task 3: Integrate Server Presets Into The Tagger Page

**Files:**
- Modify: `frontend/src/pages/TaggerPage.test.ts`
- Modify: `frontend/src/pages/TaggerPage.vue`
- Modify: `frontend/src/i18n/messages/zh-CN.ts`
- Modify: `frontend/src/i18n/messages/en-US.ts`

- [ ] **Step 1: Replace localStorage component tests with failing server-backed tests**

Mock `../tagger/captionPresets` before importing the component. Add tests that:

- wait for initialization and verify the page lists a returned preset by name;
- load a preset and copy both prompt and language into the editor;
- create a named preset from the current editor values;
- update the selected preset and preserve selection from the returned record;
- delete the selected preset and reset to the built-in default;
- keep prompt and selection unchanged when update/delete rejects;
- keep the editor usable and show `ElMessage.error` when initial loading rejects;
- disable mutation buttons while loading or mutating;
- verify the built-in default cannot be updated or deleted.

Use `flushPromises()` after mount and after every async click. Mock `window.prompt` for the template name used by “Save as template”.

- [ ] **Step 2: Run component tests and verify RED**

Run:

```powershell
npx vitest run src/pages/TaggerPage.test.ts
```

Expected: FAIL because the page still reads and writes `localStorage` directly.

- [ ] **Step 3: Implement server-backed page state**

In `TaggerPage.vue`:

- import `createCaptionPresetService` and `CaptionPreset`;
- replace `Record<string, string>` with `ref<CaptionPreset[]>([])`;
- add `captionLanguage`, `captionPresetsLoading`, and `captionPresetMutating`;
- load server records on activation, then run migration and merge returned records;
- keep the current prompt untouched on load failure and report `tagger.msg.templateLoadFail`;
- use the preset name as option text and preset id as option value;
- request a name before create and send `{ name, prompt, language }`;
- update and delete through the service, replacing/removing local records only after success;
- preserve editor and selection when an operation rejects;
- disable create/update/delete while loading or mutating;
- remove all direct `localStorage` access from the component.

Add translation keys for template name input, load/create/update/delete failures, and migration failure in both locale files.

- [ ] **Step 4: Run component tests and verify GREEN**

Run:

```powershell
npx vitest run src/pages/TaggerPage.test.ts
```

Expected: PASS.

- [ ] **Step 5: Run focused Tagger tests**

Run:

```powershell
npx vitest run src/tagger/captionPresets.test.ts src/pages/TaggerPage.test.ts src/api/tagger.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit page integration**

```powershell
git add frontend/src/pages/TaggerPage.vue frontend/src/pages/TaggerPage.test.ts frontend/src/i18n/messages/zh-CN.ts frontend/src/i18n/messages/en-US.ts
git commit -m "feat(tagger): persist caption templates in user data"
```

### Task 4: Full Verification And Cleanup

**Files:**
- Verify: `frontend/src/tagger/captionPresets.ts`
- Verify: `frontend/src/tagger/captionPresets.test.ts`
- Verify: `frontend/src/pages/TaggerPage.vue`
- Verify: `frontend/src/pages/TaggerPage.test.ts`
- Verify: `frontend/src/i18n/messages/zh-CN.ts`
- Verify: `frontend/src/i18n/messages/en-US.ts`

- [ ] **Step 1: Run the full frontend check**

Run:

```powershell
cd frontend
npm run check
```

Expected: typecheck, lint, all Vitest files, and production build pass. The two known `EngineStatusBar.vue` lint warnings may remain, but no new warnings are introduced.

- [ ] **Step 2: Remove generated build output**

Run:

```powershell
cd ..
git restore -- frontend/dist/index.html
```

Expected: generated `frontend/dist/index.html` is absent from `git status --short`.

- [ ] **Step 3: Inspect the final diff**

Run:

```powershell
git diff --check
git status --short
git diff --stat
```

Expected: no whitespace errors and only the planned source, test, locale, and plan changes remain.

- [ ] **Step 4: Commit any verification fixes**

If verification required source or test fixes:

```powershell
git add frontend/src/tagger/captionPresets.ts frontend/src/tagger/captionPresets.test.ts frontend/src/pages/TaggerPage.vue frontend/src/pages/TaggerPage.test.ts frontend/src/i18n/messages/zh-CN.ts frontend/src/i18n/messages/en-US.ts
git commit -m "test(tagger): verify user-data caption presets"
```

Otherwise, leave the already committed implementation unchanged.
