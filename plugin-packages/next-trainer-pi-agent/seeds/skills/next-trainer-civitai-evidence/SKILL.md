---
name: next-trainer-civitai-evidence
description: 通过官方 Site API 收集公开 Civitai LoRA 证据，汇总为群体统计摘要，并在人工评审后据此起草 Skill。当用户要求"收集公开训练经验 / 找 LoRA 及其公开参数 / 用社区数据构建 Skill"时使用。Collect public Civitai LoRA evidence (official Site API) into a cohort statistics summary and, after human review, draft a Skill from it. Use when the user asks to "gather public training experience / find LoRAs and their disclosed parameters / build a Skill from community data".
---

# Civitai public evidence and Skill production

Build the research path: public evidence → statistics summary → **human review**
→ Skill. Use the official Civitai Site API (not web scraping), via the host
tools `civitai_search_loras` (discovery), `civitai_fetch_version` (version
details) and `civitai_cohort_report` (cohort statistics).

## Discovery

Search by base model, `types=LORA`, time window and sort. `baseModel` takes the
platform **display name** — `SD 1.5`, `SD 2.1`, `SDXL 1.0`, `Pony`, `Illustrious`,
`Flux.1 D` — not slugs such as `sd1.5` (an unrecognized value silently returns an
empty set). Group by base model and LoRA type (character, style, clothing,
concept). Fetch creator-disclosed training parameters, `trainedWords`, optional
`trainingDetails`, version info, platform statistics and preview metadata.

## Resolving undisclosed parameters (before the cohort)

The search listing only carries the first version's sparse details. Before
building the cohort, call `civitai_fetch_version` with the `modelVersionId` of
the top candidates (up to 5 ids per call) to pull the full version record:
disclosed `trainingDetails` (learning rate, steps, batch, network dim/alpha,
scheduler…), `trainedWords` and stats. Use the **version records** (not the raw
listing) as the cohort input so that missingness and distributions reflect the
actual version data. If a fetch fails or returns no `trainingDetails`, that
field stays unknown — do not infer it from popularity.

## Principles

- Publicly disclosed content is a fact; missing parameters stay **unknown**.
- Platform popularity is for **discovering samples only** — it is never direct
  evidence of best practice.
- Present parameters as **distributions, quantiles, missingness and
  counter-examples** — never copy a single popular value.
- Preview images are not the original training set; never claim to know the real
  dataset composition from them.
- `trainingDetails: null` stays unknown; label every field as
  creator_declared / api_metadata / platform_statistic / inferred / unknown.

## Cohort output

```text
LoraEvidenceCohort
- base_model, lora_category, discovery_query, retrieved_at
- sample_count
- parameter_distributions
- disclosed_dataset_patterns
- missingness
- popularity_bias
- source_records (URLs)
- confidence
```

## Human-review gate (do not skip)

Before a Skill is produced, retain source URLs, retrieval time, sample size,
bias, confidence and a **human review record**. A Skill drafted from evidence
(`SkillDraft`) must carry scope, recommendations, evidence summary, exceptions,
unknowns, `local_validation_status` and source links. A generated Skill must be
validated by at least one real local training in this project, **or** explicitly
marked "not yet locally validated". An unreviewed Skill does not enter the formal
resource directory. To save a drafted Skill into the local library, write it under
the knowledge root via the data-root files (the user manages that directory).
