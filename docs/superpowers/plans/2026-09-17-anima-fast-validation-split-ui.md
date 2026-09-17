# Anima Fast Validation Split GUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an Anima Fast GUI field for `validation_split_num` that is visible in dataset settings, defaults to `0`, and survives frontend import/serialization into the backend payload.

**Architecture:** Extend only the Anima Fast Schemastery definition. The existing dynamic form will render the number field, and the existing model hydration and serialization flow will carry imported values. The existing Anima Fast adapter remains responsible for writing the value to dataset TOML.

**Tech Stack:** TypeScript, Schemastery, Vue 3 dynamic forms, Vitest, Python unittest/pytest

---

### Task 1: Define and expose the Anima Fast field

**Files:**
- Modify: `frontend/src/schema/adapter.test.ts`
- Modify: `mikazuki/schema/anima-lora-fast.ts`

- [ ] **Step 1: Write the failing frontend schema test**

Add a test that loads the real Anima Fast schema and verifies the field metadata,
default model, and imported value serialization:

```ts
it("exposes and serializes the Anima Fast validation image count", () => {
  const schemaDir = resolve(process.cwd(), "../mikazuki/schema")
  const realSources = readdirSync(schemaDir).filter((name) => name.endsWith(".ts")).map((file) => ({
    name: file.slice(0, -3),
    hash: file,
    schema: readFileSync(resolve(schemaDir, file), "utf8"),
  }))
  const fast = executeSchemaSources(realSources, "anima-lora-fast")
  const dataset = fast.sections.find((section) => section.title === "数据集设置")!
  const field = dataset.fields.find((item) => item.key === "validation_split_num")

  expect(field).toMatchObject({
    type: "number",
    min: 0,
    step: 1,
    defaultValue: 0,
  })
  expect(createDefaultModel(fast)).toMatchObject({ validation_split_num: 0 })

  const imported = normalizeModelForSchema(
    fast,
    { ...createDefaultModel(fast), validation_split_num: 8 },
    { explicitKeys: new Set(["validation_split_num"]) },
  )
  expect(serializeModel(fast, imported)).toMatchObject({ validation_split_num: 8 })
})
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
Set-Location frontend
npm test -- src/schema/adapter.test.ts
```

Expected: FAIL because `validation_split_num` is absent from the real Anima Fast
schema.

- [ ] **Step 3: Add the minimal schema field**

Add this field to the Anima Fast `数据集设置` object:

```ts
validation_split_num: Schema.number()
    .min(0)
    .step(1)
    .default(0)
    .description("验证集图片数量；0 表示关闭验证集，大于 0 时从训练图片中保留对应数量用于验证。小数据集建议保持 0"),
```

- [ ] **Step 4: Run the focused frontend test and verify GREEN**

Run:

```powershell
Set-Location frontend
npm test -- src/schema/adapter.test.ts
```

Expected: all tests in `adapter.test.ts` pass.

- [ ] **Step 5: Commit the tested frontend change**

```powershell
git add frontend/src/schema/adapter.test.ts mikazuki/schema/anima-lora-fast.ts
git commit -m "fix(anima-fast): expose validation split in GUI"
```

### Task 2: Verify frontend and backend integration

**Files:**
- Verify: `frontend/src/schema/adapter.test.ts`
- Verify: `mikazuki/engines/anima_fast/adapter.py`
- Verify: `tests/test_anima_fast_backend.py`

- [ ] **Step 1: Run the full frontend quality gate**

Run:

```powershell
Set-Location frontend
npm run typecheck
npm run lint
npm test
npm run build
```

Expected: all commands succeed with no new warnings or failures.

- [ ] **Step 2: Run focused backend validation split tests**

Run from the repository root:

```powershell
python -m pytest tests/test_anima_fast_backend.py -q -k "validation_split"
```

Expected: the default-`0` and explicit-value dataset TOML tests pass.

- [ ] **Step 3: Inspect the rendered form**

Start the application or frontend development server, open the Anima Fast
training page, and confirm the `验证集图片数量` number input appears in `数据集设置`
with value `0`.

- [ ] **Step 4: Inspect final diff and repository state**

Run:

```powershell
git diff origin/main...HEAD --check
git status --short --branch
```

Expected: only the design, plan, focused schema test, and Anima Fast schema
changes are present; the working tree is clean.
