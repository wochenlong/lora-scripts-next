---
name: next-trainer-dataset-review
description: 审查训练数据集的图片与 caption 文本——先做确定性预检，再做多模态语义审查——并产出文件级报告与建议。当用户要求"检查 / 审计 / 审查这个数据集、它的图片或 caption"时使用。Review a training dataset's images and caption text — deterministic pre-checks plus multimodal semantic review — and produce a file-level report with suggestions. Use when the user asks to "check / audit / review this dataset, its images, or its captions".
---

# Dataset and caption review

Review in two layers. Do **not** send a whole large dataset unfiltered to a
multimodal model.

## Resolving the dataset root

If the user did not state an explicit path, call the host tool
`training_config_current` FIRST — the training parameters the user is currently
filling in the Next Trainer frontend usually contain the dataset directory they
already typed. Paths there may be **relative** — resolve them against the
project root (your working directory) and verify the result exists on disk
before using it. Only if it is missing or invalid there may you look for
candidate dataset directories yourself or ask the user (saying what you already
checked and that the current training parameters point to X).

## Layer 1 — deterministic pre-check (code facts)

Run the host `dataset_inventory` for file-level statistics: file count,
corrupt/undecodable files, size and aspect-ratio distribution, caption
missingness, near/exact duplicates, label frequencies, trigger-word coverage,
and image↔caption filename correspondence. These are facts, not opinions —
report them as such and point every file-level issue at the specific file.

## Layer 2 — multimodal semantic review (model judgement)

Use the host `dataset_review_images` (controlled sampling: anomaly items,
duplicate-cluster representatives, stratified samples; default limit 12, max 100).
The host's active remote vision reviewer does the judgement — the `model`
argument is optional and only used when no host reviewer is configured.
Each reviewed item returns structured findings:
- `captionMatch`: ok / partial / mismatch (caption vs depicted subject);
- `visualIssues`: subset of blurry, overexposed, underexposed, occluded,
  bad_crop, watermark, compression_artifact, low_detail, incomplete_subject,
  mixed_subjects, unusable;
- `identityNotes`, `captionSuggestion`, `severity` (ok / minor / major).

Judge, across the sample: caption subject/style/attribute coverage, severe
blur/occlusion/crop/watermark, identity stability for the training target, and
over-concentration on one angle/background/expression.

Interpret the report honestly:
- items with `status: "unavailable"` (reason `REMOTE_REVIEW_FAILED` /
  `MODEL_CAPABILITY_UNAVAILABLE`) are **not** reviewed — say so, never count
  them as reviewed, and keep the run in Layer-1-only conclusions if all fail;
- `reviewedImages` / `unreviewedImages` tell the true coverage;
- findings are one model's judgement, not file facts — label them as such.

Let the user choose "sampled review" vs "full semantic review"; for full mode
state the expected image count, token/cost and privacy notice.

## Initial tagging (optional)

If the dataset has no captions yet, you may start the host WD14 tagger to
generate initial captions: `tagger_start` (a data write — it requires the
confirmation ticket and only one job runs at a time), then poll `tagger_status`
and use `tagger_cancel` to stop it. Only after tagging, run the review.

## Report contract

```text
DatasetReviewReport
- inventory: file and annotation statistics
- distribution: size, ratio, label, composition
- issues: file-level issues, severity, evidence, suggested action
- duplicate_groups: duplicate clusters and representative files
- caption_alignment: image/text consistency results
- coverage_gaps: angle, attribute, background gaps
- reviewed_scope: deterministic coverage + multimodal sampling method
- limitations: model and sampling boundaries
```

Separate "code-detected facts" from "model judgement". Never describe an
unreviewed image as reviewed. In the first version only **suggest** changes:
to modify a caption, stage it with the host `dataset_caption_stage` and apply
only after the user confirms with `dataset_caption_commit` (confirmation
ticket). Do not auto-rewrite captions, and do not move or delete images.
