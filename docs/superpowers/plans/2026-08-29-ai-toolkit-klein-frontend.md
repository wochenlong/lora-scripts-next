# AI Toolkit Klein Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a reusable capability-driven `训练任务` selector and paired reference-directory control to the dynamic training form, with Klein 4B/9B coverage and verified frontend behavior.

**Architecture:** Backend schema metadata remains the source of model capabilities and field semantics. The frontend adapter normalizes that metadata into `AdaptedSchema`, while `DynamicSchemaForm` renders the selector and specialized directory field without a Klein-specific page. `serializeModel()` remains the only filtering boundary before preview, preflight, export, and run.

**Tech Stack:** Vue 3, TypeScript, Element Plus, Schemastery, Vitest, Vite.

---

### Task 1: Extend the schema AST with capability metadata

**Files:**
- Modify: `frontend/src/schema/adapter.ts`
- Test: `frontend/src/schema/adapter.test.ts`
- Modify: `mikazuki/schema/klein-lora.ts`

- [ ] **Step 1: Write failing adapter tests**

Add tests that execute a schema source containing `meta.extra.capabilities` and
`meta.extra.task`, then assert these values are present on `AdaptedSchema`.
Add a second test asserting a field's `extra` metadata preserves
`role: "paired-directories"` and a task condition.

- [ ] **Step 2: Run the focused adapter tests**

Run:

```text
npx vitest run src/schema/adapter.test.ts
```

Expected: the new assertions fail because `AdaptedSchema` has no capability or
task metadata.

- [ ] **Step 3: Implement the minimal adapter metadata**

Add typed `capabilities: string[]` and optional `task` properties to
`AdaptedSchema`. Read them from schema metadata extra values in
`executeSchemaSources`, defaulting to an empty capability list and no task.
Keep field `extra` unchanged so specialized roles remain generic.

- [ ] **Step 4: Declare Klein capabilities and task discriminators**

Update `mikazuki/schema/klein-lora.ts` so the root schema declares
`capabilities: ["lora", "text-to-image", "image-edit"]` and the dataset fields
are conditioned by a `task` discriminator. Set the default task to
`text-to-image`; keep reference-directory values available in the form model
but inactive for serialization in text-to-image mode.

- [ ] **Step 5: Run the focused tests**

Run:

```text
npx vitest run src/schema/adapter.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit**

```text
git add frontend/src/schema/adapter.ts frontend/src/schema/adapter.test.ts mikazuki/schema/klein-lora.ts
git commit -m "feat(ai-toolkit): expose klein training capabilities"
```

### Task 2: Add task-aware serialization and section ordering

**Files:**
- Modify: `frontend/src/schema/adapter.ts`
- Test: `frontend/src/schema/adapter.test.ts`
- Modify: `frontend/src/components/DynamicSchemaForm.vue`
- Test: `frontend/src/components/DynamicSchemaForm.test.ts`

- [ ] **Step 1: Write failing serialization tests**

Add tests for a dual-capability schema with `task` conditions:

```ts
expect(serializeModel(schema, { task: "text-to-image", train_data_dir: "./images", control_data_dirs: ["./controls"] }))
  .not.toHaveProperty("control_data_dirs")
expect(serializeModel(schema, { task: "image-edit", train_data_dir: "./images", control_data_dirs: ["./controls"] }))
  .toHaveProperty("control_data_dirs", ["./controls"])
```

Add an adapter test for the stable section order metadata.

- [ ] **Step 2: Verify the tests fail**

Run:

```text
npx vitest run src/schema/adapter.test.ts src/components/DynamicSchemaForm.test.ts
```

Expected: task-conditioned fields are not yet represented correctly and the
section order assertion fails.

- [ ] **Step 3: Implement stable ordering and active-field behavior**

Add a shared section-order map in the adapter keyed by the approved section
group metadata. Sort only sections that declare a known group; preserve source
order for unknown sections. Ensure active field selection and serialization
continue to use the task discriminator.

- [ ] **Step 4: Render the generic task selector**

In `DynamicSchemaForm.vue`, derive the task selector from
`schema.capabilities` and the `task` field metadata. Render it before the
dataset fields when both task capabilities are present. Emit a normal model
update; do not add Klein-specific conditionals.

- [ ] **Step 5: Verify green**

Run:

```text
npx vitest run src/schema/adapter.test.ts src/components/DynamicSchemaForm.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit**

```text
git add frontend/src/schema/adapter.ts frontend/src/schema/adapter.test.ts frontend/src/components/DynamicSchemaForm.vue frontend/src/components/DynamicSchemaForm.test.ts
git commit -m "feat(frontend): add capability-driven training task"
```

### Task 3: Implement paired-directory field behavior

**Files:**
- Modify: `frontend/src/components/SchemaField.vue`
- Test: `frontend/src/components/DynamicSchemaForm.test.ts`
- Modify: `frontend/src/styles/schema-form.css`
- Modify: `frontend/src/i18n/locales/zh-CN.ts`

- [ ] **Step 1: Write failing component tests**

Mount the form with a `paired-directories` field and assert that an existing
directory is rendered, an add control creates a second empty row, and removing
the second row updates the emitted array. Assert that the helper text includes
the filename-pairing instruction.

- [ ] **Step 2: Verify the tests fail**

Run:

```text
npx vitest run src/components/DynamicSchemaForm.test.ts
```

Expected: the current textarea renderer has no add/remove controls and does not
render the pairing guidance.

- [ ] **Step 3: Implement the smallest reusable control**

In `SchemaField.vue`, branch on `field.role === "paired-directories"`.
Render one server-path-picker input per array item, an add button, and remove
buttons for rows after the first. Emit a cloned array on every mutation.
Reuse `useServerPathPick` for browsing server-side directories.

- [ ] **Step 4: Add localized labels and styles**

Add concise Chinese labels for add/remove/reference-directory/pairing guidance
through the existing i18n namespace. Add styles to `schema-form.css` for a
stable row grid that collapses to one column below 720px.

- [ ] **Step 5: Verify green**

Run:

```text
npx vitest run src/components/DynamicSchemaForm.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit**

```text
git add frontend/src/components/SchemaField.vue frontend/src/components/DynamicSchemaForm.test.ts frontend/src/styles/schema-form.css frontend/src/i18n/locales/zh-CN.ts
git commit -m "feat(frontend): add paired directory field"
```

### Task 4: Align Klein schema labels and end-to-end form behavior

**Files:**
- Modify: `mikazuki/schema/klein-lora.ts`
- Modify: `frontend/src/pages/TrainingPage.vue`
- Test: `frontend/src/pages/TrainingPage.test.ts`
- Modify: `mikazuki/engines/ai_toolkit/FIELD_NOTES.md`

- [ ] **Step 1: Write failing page tests**

Add page tests for Klein defaults and task switching. Assert that the rendered
form starts in `文生图`, switches to `图像编辑`, preserves a reference
directory, and sends a run payload containing that directory only in edit mode.

- [ ] **Step 2: Run the page tests**

Run:

```text
npx vitest run src/pages/TrainingPage.test.ts
```

Expected: the selector and edit-mode payload assertions fail.

- [ ] **Step 3: Make Klein metadata match the approved groups**

Add stable group metadata to Klein's sections and rename visible section
descriptions to the PR #298 order. Keep model installation/download out of the
schema form. Keep preview, logging, and advanced fields within the shared
groups.

- [ ] **Step 4: Verify submit uses the shared output**

Use the existing `output` computed value for preview, preflight, and run. Add
only the generic task-aware serialization needed for edit mode; do not create a
Klein-specific request path.

- [ ] **Step 5: Run the focused frontend suite**

Run:

```text
npx vitest run src/pages/TrainingPage.test.ts src/schema/adapter.test.ts src/components/DynamicSchemaForm.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit**

```text
git add mikazuki/schema/klein-lora.ts frontend/src/pages/TrainingPage.vue frontend/src/pages/TrainingPage.test.ts mikazuki/engines/ai_toolkit/FIELD_NOTES.md
git commit -m "feat(ai-toolkit): adapt klein training form"
```

### Task 5: Verify the frontend and prepare real-machine handoff

**Files:**
- Modify: `frontend/src/MIGRATION.md` only if the new capability contract
  changes migration status.

- [ ] **Step 1: Run focused tests and typecheck**

Run:

```text
cd frontend
npx vitest run src/schema/adapter.test.ts src/components/DynamicSchemaForm.test.ts src/pages/TrainingPage.test.ts
npm run typecheck
```

Expected: all focused tests and typecheck pass.

- [ ] **Step 2: Run lint and production build**

Run:

```text
npm run lint
npm run build
```

Expected: lint and build pass without modifying source-generated `dist/`.

- [ ] **Step 3: Start the local frontend**

Run:

```text
npm run dev -- --host 127.0.0.1
```

Open the reported URL and check Klein at desktop and mobile widths. Confirm
the selector, edit-mode reference rows, right-side TOML preview, validation
feedback, and submit/preflight error display.

- [ ] **Step 4: Check the worktree**

Run:

```text
git diff --check
git status --short
```

Keep runtime directories and generated files untracked. Preserve the existing
`FIELD_NOTES.md` evidence change.

- [ ] **Step 5: Stop before PR creation**

Report the local URL and exact real-machine test steps. Do not create a PR or
merge anything until the user confirms a real frontend Klein text-to-image or
image-edit training run completed successfully.
