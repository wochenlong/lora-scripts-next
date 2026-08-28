---
name: next-trainer-artifact-selection
description: 用固定对比协议（相同 seed、prompt 与生成设置）从多个候选 checkpoint/LoRA 中选出最佳，并按每个候选的优点/风险排出 Top-K。Choose the best checkpoint/LoRA from several candidates using a fixed comparison protocol (same seed, prompt and generation settings) and rank them Top-K with per-candidate strengths/risks.
---

# Artifact (checkpoint/LoRA) selection

Pick the best output model from several candidates. The decision must follow the
user's stated training goal (e.g. "character consistency first" vs "generalization
first") — the user may set the weights.

## Resolving the model/output location

If the user did not state where the candidates live, call the host tool
`training_config_current` FIRST — the current training parameters usually
contain the model/output directory the user already typed (verify it exists on
disk). Only then fall back to searching or asking.

## Protocol

1. List the candidate checkpoints/LoRAs with their epoch, step and metric
   summary (read the artifact/metrics from the workspace with the native `read`
   tool).
2. Compare under **identical test conditions**: fixed seed, fixed prompt set and
   fixed generation settings, so the sample images are comparable. Use the host
   `artifact_compare` to produce the comparison set.
   - **No renderer configured?** `artifact_compare` then honestly reports
     `renderer_unavailable` for every cell (a renderer is an operator-provided
     external generation service). In that case do **not** invent image
     comparisons: fall back to (a) the training run's own fixed-protocol
     preview samples (same prompt + seed every N epochs — read them from the
     output directory) as cross-epoch visual evidence, and (b) the metrics.
     State the limitation explicitly in the report.
3. Judge per task goal: character consistency, style strength, composition
   stability, detail, artifacts, and over-fit signs.
4. Rank with the host `artifact_recommend` (quality, over-fit risk, stability,
   efficiency evidence with visible coverage). Feed per-candidate metrics from
   the real run (e.g. per-epoch loss trend, plateau position) when available.

## Output contract

```text
ArtifactSelectionRecommendation
- candidates
- comparison_protocol: seed / prompt / generation settings used
- ranked_results
- per_candidate_strengths_and_risks
- recommended_artifact
- limitations
```

- Comparison sample images must use the same test conditions.
- The recommendation must match the user's declared training goal.
- Keep the evidence, target weights, counter-examples and confidence visible.
- The agent does **not** delete unselected artifacts.
