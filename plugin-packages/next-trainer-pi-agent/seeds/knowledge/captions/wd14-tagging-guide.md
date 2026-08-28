# WD14 auto-tagging guide

- Version: `2026-08-29`
- Scope: host WD14 (`wd14-convnextv2-v2`) batch tagging of image datasets.
- Evidence status: project contract + tagger tool behaviour.

## When to tag

- New datasets without captions, or to enrich thin captions before a LoRA run.
- Character sets: keep the **trigger word / keep tokens** in front of the WD14 tags so the LoRA binds identity to the trigger.

## Settings that matter

- `threshold` (general tags): start ~0.35; lower only to recover missing tags, not to add noise.
- `character_threshold`: start ~0.3 for character sets.
- `add_rating_tag`: leave on for mixed datasets; drop it for a single-rating set to save a slot.
- `escape_tag`: on, when tags contain special characters used by the caption format.
- `batch_output_action_on_conflict`: values are matched **exactly, lowercase**.
  - `ignore` — skip files that already have a caption; **nothing is written**. Use this whenever existing/human captions must be preserved (the only safe value for "do not overwrite").
  - `prepend` — write the file with the NEW tags in front of the existing caption.
  - `append` — write the file with the NEW tags after the existing caption (this is also the behaviour for ANY value that is not exactly `ignore`/`copy`/`prepend` — e.g. a made-up value like `Skip` silently rewrites the file with appended tags).
  - `copy` — replace the existing caption entirely with the new tags.
  - So: "keep existing captions untouched" ⇒ pass exactly `ignore`; anything else rewrites the files.
- First run downloads the ONNX model (~400MB) from Hugging Face; afterwards it is cached.

## After tagging

- Always run `dataset_inventory` (or the dataset-review skill) after a tagging pass: it detects duplicate/empty captions and hash changes deterministically.
- Spot-check 10–20 images before training; WD14 misses character-specific details, so manual refinement of the identity tags is still expected.
