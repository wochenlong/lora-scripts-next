---
name: next-trainer-train-params
description: 根据用户的目标、硬件资源与数据集概览，起草 Next Trainer 训练参数提案（字段级补丁，而非整表重写），并以知识库与模板为依据。当用户要求"生成 / 推荐 / 填写 LoRA 训练参数"时使用。Draft a Next Trainer training-parameter proposal (a field-level patch, not a whole-form rewrite) from the user's goal, resources and dataset summary, grounded in the knowledge base and templates. Use when the user asks to "generate / recommend / fill in LoRA training parameters".
---

# Generate training parameters (proposal)

Produce a **parameter patch**, never an unbounded rewrite of the whole form, and
never auto-submit a training run.

## Workflow

1. **Resolve known inputs from the CURRENT training parameters before asking
   anything.** The user is usually already filling in the training form in the
   Next Trainer frontend, and those parameters contain the machine paths they
   typed (dataset directory, model/checkpoint, output dir). Call the host tool
   `training_config_current` (optionally with `trainType`) FIRST and read its
   `savedParams`. Paths there may be **relative** — resolve them against the
   project root (your working directory) and verify each path exists on disk
   before trusting it. Only if a value is still missing or invalid after that
   step may you search the filesystem yourself or ask the user — and if you ask,
   mention what you already found in the current parameters (e.g. "current
   training params point the dataset to ./train/aki, which I could not find").
   Never guess machine paths.
2. **Ground it.** Use `next_trainer_knowledge` (`list`/`search`/`read`) to find
   the applicable knowledge and any TOML template that matches the model family
   and LoRA type (e.g. `knowledge/model-families/anima-lora-parameter-baseline.md`
   for Anima, `.../sd15-...` / `.../sdxl-...` for those families,
   `knowledge/parameters/parameter-evidence-rules.md` for evidence layering, and
   `templates/<family>-lora-conservative.toml`). Treat templates as empirical
   starting points, not guarantees; keep the three evidence layers separate
   (disclosed fact / observed distribution / inference).
3. **Read current context.** Read the current form / final submitted config and
   the relevant schema. Strip sensitive fields (API keys, tokens, private paths)
   before reasoning about them; never echo secret values.
4. **Validate inline, before presenting — do NOT defer.** Compose the proposed
   fields into a minimal TOML draft (you may also write it to a file in the
   working directory, e.g. `training-draft.toml`, for the user to keep), then call
   the host `training_config_validate` with the draft's **full text** in
   `content` — **never a file path** — i.e. `{ "content": "<full TOML text>",
   "format": "toml", "pageTrainType": "<anima-lora|sd-lora|...>" }`. Record its
   result (normalized fields + any schema / conflict / engine preflight findings)
   in the proposal's `validation` section. If a field fails, fix the draft and
   re-validate. Never present an unvalidated patch, and never promise to validate
   it later — the `validation` section of every proposal must reflect a real
   validate call.
5. **Present the patch.** For each changed field give: the value, a one-line
   rationale, the source (knowledge file / template / schema), a confidence
   level (high/medium/low), the fields still needing the user, and any warnings
   or applicability boundaries.
6. **Confirm before applying.** Only after explicit user confirmation, apply via
   the host `training_config_commit` (which enforces the two-stage confirmation
   ticket). Do not submit the training run automatically.

## Output contract

```text
TrainingProposal
- target: model / engine / training goal
- patch: only the fields to change
- rationale: per-field reason
- sources: knowledge file / template / schema citations
- confidence: high / medium / low
- validation: schema / conflict / preflight results
- missing_inputs: what the user still must provide
- warnings: risks and applicability boundaries
```

Do not emit fields the schema does not recognize. Do not copy a Civitai
popularity ranking as the reason for a parameter choice.
