# Anima Fast Validation Split GUI Design

## Goal

Expose the upstream Anima Fast `validation_split_num` dataset option in the
Next Trainer GUI so users can explicitly control whether training images are
reserved for validation.

## Scope

- Add `validation_split_num` to the Anima Fast dataset settings schema.
- Render it as an integer input with a minimum of `0`, a step of `1`, and a
  default of `0`.
- Explain that `0` disables the validation split and positive values reserve
  that many images from the training dataset.
- Preserve imported TOML values through the existing schema hydration and
  serialization flow.
- Keep the existing Anima Fast adapter behavior that writes the selected value
  to the generated dataset TOML.

This change is Anima Fast-specific. It does not add a shared Kohya field and
does not implement warnings for validation datasets that produce zero batches.

## Data Flow

The dynamic form reads `mikazuki/schema/anima-lora-fast.ts`, creates a default
model containing `validation_split_num = 0`, and serializes the selected value
with the rest of the Anima Fast payload. The backend adapter writes that value
to the generated Anima Fast dataset TOML.

When a TOML configuration contains `validation_split_num`, the existing import
pipeline hydrates the matching schema field so the value is visible and
editable in the GUI.

## Validation

- A schema adapter test verifies the field is in the Anima Fast dataset
  section with number type, minimum `0`, step `1`, and default `0`.
- A configuration import test verifies an imported non-zero value survives
  hydration and serialization.
- Existing Anima Fast backend tests verify the adapter defaults to `0` and
  preserves explicit values.
- Frontend type checking and focused backend tests remain green.
