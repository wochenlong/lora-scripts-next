import { h, type VNodeChild } from "vue";

export type TrainingFormState = Record<string, unknown>;

interface TrainingFieldBase<TForm extends TrainingFormState> {
  key: keyof TForm & string;
  id: string;
  label: string;
  description?: string;
  hidden?: boolean;
  disabled?: boolean;
  visibleWhen?: (form: TForm) => boolean;
  role?: "file" | "folder" | "table" | "slider" | "switch";
}

export type TrainingFieldSpec<TForm extends TrainingFormState = TrainingFormState> =
  | (TrainingFieldBase<TForm> & {
      kind: "text";
      placeholder?: string;
    })
  | (TrainingFieldBase<TForm> & {
      kind: "number";
      min?: number;
      step?: string | number;
    })
  | (TrainingFieldBase<TForm> & {
      kind: "checkbox";
    })
  | (TrainingFieldBase<TForm> & {
      kind: "select";
      options: string[];
    })
  | (TrainingFieldBase<TForm> & {
      kind: "textarea";
      rows?: number;
    });

export interface RunControl {
  label: string;
  onClick: () => void | Promise<void>;
  primary?: boolean;
}

export interface TrainingSectionSpec<TForm extends TrainingFormState = TrainingFormState> {
  title: string;
  fields: TrainingFieldSpec<TForm>[];
  hidden?: boolean;
  visibleWhen?: (form: TForm) => boolean;
}

export function renderTrainingField<TForm extends TrainingFormState>(form: TForm, field: TrainingFieldSpec<TForm>) {
  if (field.hidden || field.visibleWhen?.(form) === false) {
    return null;
  }

  if (field.kind === "checkbox") {
    return h("label", { class: "training-toggle anima-toggle" }, [
      h("input", {
        id: field.id,
        type: "checkbox",
        disabled: field.disabled,
        checked: Boolean(form[field.key]),
        onChange: (event: Event) => {
          form[field.key] = (event.target as HTMLInputElement).checked as TForm[keyof TForm & string];
        },
      }),
      h("span", field.label),
      renderFieldDescription(field.description),
    ]);
  }

  if (field.kind === "select") {
    return h("label", { class: "training-field anima-field" }, [
      h("span", field.label),
      h(
        "select",
        {
          id: field.id,
          disabled: field.disabled,
          value: String(form[field.key] ?? ""),
          onChange: (event: Event) => {
            form[field.key] = (event.target as HTMLSelectElement).value as TForm[keyof TForm & string];
          },
        },
        field.options.map((value) => h("option", { value }, value || "auto")),
      ),
      renderFieldDescription(field.description),
    ]);
  }

  if (field.kind === "textarea") {
    return h("label", { class: "training-field anima-field" }, [
      h("span", field.label),
      h("textarea", {
        id: field.id,
        disabled: field.disabled,
        value: String(form[field.key] ?? ""),
        rows: field.rows ?? 4,
        onInput: (event: Event) => {
          form[field.key] = (event.target as HTMLTextAreaElement).value as TForm[keyof TForm & string];
        },
      }),
      renderFieldDescription(field.description),
    ]);
  }

  if (field.kind === "number") {
    return h("label", { class: "training-field anima-field" }, [
      h("span", field.label),
      h("input", {
        id: field.id,
        type: "number",
        min: field.min ?? 0,
        step: field.step ?? 1,
        disabled: field.disabled,
        value: Number(form[field.key] ?? 0),
        onInput: (event: Event) => {
          form[field.key] = Number((event.target as HTMLInputElement).value) as TForm[keyof TForm & string];
        },
      }),
      renderFieldDescription(field.description),
    ]);
  }

  return h("label", { class: "training-field anima-field" }, [
    h("span", field.label),
    renderTextInput(form, field),
    renderFieldDescription(field.description),
  ]);
}

export function renderTrainingFields<TForm extends TrainingFormState>(
  form: TForm,
  fields: TrainingFieldSpec<TForm>[],
) {
  return fields.map((field) => renderTrainingField(form, field));
}

export function renderTrainingFieldRow(children: VNodeChild[]) {
  return h("div", { class: "training-field-row anima-field-row" }, children);
}

export function renderTrainingSection(title: string, children: VNodeChild[]) {
  return h("fieldset", { class: "training-section anima-section" }, [h("legend", title), ...children]);
}

export function renderTrainingSectionSpec<TForm extends TrainingFormState>(form: TForm, section: TrainingSectionSpec<TForm>) {
  if (section.hidden || section.visibleWhen?.(form) === false) {
    return null;
  }
  return renderTrainingSection(section.title, renderTrainingFields(form, section.fields));
}

export function renderTrainingWorkbench(formPanel: VNodeChild[], previewPanel: VNodeChild[]) {
  return h("section", { class: "training-workbench anima-workbench" }, [
    h("div", { class: "training-form-panel anima-form-panel" }, formPanel),
    h("aside", { class: "training-preview-panel anima-preview-panel" }, previewPanel),
  ]);
}

export function renderParameterPreview(code: string, id = "training-preview-code") {
  return h("div", { class: "training-preview-card anima-preview-card" }, [
    h("h2", "Parameter Preview"),
    h("pre", { id, class: "training-preview-code anima-preview-code" }, code),
  ]);
}

export function renderRunControls(actions: RunControl[], status = "") {
  return h("div", { class: "training-preview-card anima-preview-card" }, [
    h("h2", "Run Controls"),
    h(
      "div",
      { class: "training-actions anima-actions" },
      actions.map((action) =>
        h(
          "button",
          {
            type: "button",
            class: action.primary ? "primary" : "",
            onClick: action.onClick,
          },
          action.label,
        ),
      ),
    ),
    status ? h("p", { class: "training-status anima-status" }, status) : null,
  ]);
}

export function previewToml(values: Record<string, unknown>): string {
  return Object.entries(values)
    .filter(([, value]) => value !== "")
    .map(([key, value]) => `${key} = ${tomlValue(value)}`)
    .join("\n");
}

export function tomlValue(value: unknown): string {
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (typeof value === "number") {
    return String(value);
  }
  return `"${String(value).replaceAll("\\", "\\\\").replaceAll('"', '\\"').replaceAll("\n", "\\n")}"`;
}

function renderFieldDescription(description?: string) {
  return description ? h("small", { class: "training-field-description" }, description) : null;
}

function renderTextInput<TForm extends TrainingFormState>(
  form: TForm,
  field: Extract<TrainingFieldSpec<TForm>, { kind: "text" }>,
) {
  const input = h("input", {
    id: field.id,
    disabled: field.disabled,
    value: String(form[field.key] ?? ""),
    placeholder: field.placeholder ?? "",
    "data-training-role": field.role,
    onInput: (event: Event) => {
      form[field.key] = (event.target as HTMLInputElement).value as TForm[keyof TForm & string];
    },
  });

  if (field.role !== "file" && field.role !== "folder") {
    return input;
  }

  return h("div", { class: "training-path-field" }, [
    input,
    h(
      "button",
      {
        type: "button",
        class: "training-path-field__browse",
        disabled: field.disabled,
        title: `${field.role === "folder" ? "Folder" : "File"} picker integration is pending`,
        onClick: () => {
          window.dispatchEvent(
            new CustomEvent("sd-training-path-browse", {
              detail: { key: field.key, role: field.role, id: field.id },
            }),
          );
        },
      },
      "Browse",
    ),
  ]);
}
