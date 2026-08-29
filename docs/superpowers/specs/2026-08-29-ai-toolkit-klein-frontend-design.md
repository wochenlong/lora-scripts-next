# AI Toolkit Klein Frontend Design

## Goal

Make the AI Toolkit Klein training page the first reusable frontend integration
for models that support both text-to-image and image-edit training. The page
must keep the existing dynamic-schema workflow and must not add model download
or environment installation controls.

## Scope

In scope:

- A capability-driven `训练任务` selector with `文生图` and `图像编辑`.
- Stable, shared parameter section ordering aligned with PR #298.
- A reusable paired-directory field for image-edit reference data.
- Klein 4B and 9B support through the same page and schema flow.
- Frontend validation, tests, build, and a local browser check.

Out of scope:

- Model downloads, engine installation, or environment repair.
- A separate Klein-only page.
- Full fine-tuning support.
- Image-edit inference quality validation.
- Creating or merging a PR before the user confirms a real frontend
  training run.

## Data Contract

The schema declares capabilities and the current task. The frontend does not
hard-code a Klein branch in `TrainingPage.vue`.

- `capabilities`: a list such as `text-to-image`, `image-edit`, and `lora`.
- `task`: `text-to-image` or `image-edit`.
- A task selector is rendered only when both task capabilities are present.
- A single-capability model keeps its task fixed and hides the selector.
- `task` is UI state. Serialization omits `control_data_dirs` for
  `text-to-image` and includes it for `image-edit`.
- Reference directories use a reusable field role such as
  `paired-directories`; the field is not Klein-specific.
- Switching tasks preserves inactive values in the form model, but inactive
  fields are excluded from the final configuration.

The default task is `text-to-image` each time the page is opened. The selector
does not persist a task choice independently from the normal form draft.

## Layout and Interaction

The `训练任务` selector is the first control in the `数据集设置` section and
uses the existing segmented-control visual language.

In text-to-image mode, the form shows the training image directory,
resolution, captions, and other shared dataset fields. In image-edit mode it
also shows reference directories with the explanation:

> 参考图按文件名与训练图配对；每个训练图都应有对应参考图。

Reference directories are rendered as addable directory rows with server-side
path browsing. Toggling the task does not reload the schema, clear fields, or
alter unrelated form state.

Sections use this stable order:

1. 训练用模型
2. 训练模型类型
3. 数据集设置
4. 保存设置
5. 训练过程
6. 学习率与优化器
7. 网络设置
8. 训练预览图设置
9. 省显存
10. 日志 / caption / 噪声 / 数据增强
11. 其他
12. 分布式训练

If a model does not expose a section, the section is omitted without leaving
an empty placeholder.

## Data Flow

The loader executes the backend schema and adapts metadata into the existing
frontend AST. `DynamicSchemaForm` renders sections and fields. The selector
updates the form model, `serializeModel()` filters inactive fields, and
`buildTrainingConfig()` produces the single final configuration consumed by
the TOML preview, export, preflight, and run request.

Frontend checks remain fast and user-oriented. AI Toolkit preflight remains the
source of truth for paths, pair matching, model compatibility, and environment
errors.

## Testing

Tests cover:

- Adapter handling of capability, task, and field metadata.
- Selector visibility for dual-capability versus single-capability schemas.
- Omission/inclusion of reference directories during serialization.
- Preservation of reference-directory values while switching tasks.
- Add/remove/browse behavior and serialization for paired directories.
- Klein 4B and 9B default values and schema loading.

Verification includes focused Vitest tests, typecheck, lint, production build,
and a local browser check at desktop and mobile widths. No PR is created until
the user confirms the real frontend training run.
