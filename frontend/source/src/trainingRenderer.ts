import { h, type VNodeChild } from "vue";

export type TrainingFormState = Record<string, unknown>;

interface TrainingFieldBase<TForm extends TrainingFormState> {
  key: keyof TForm & string;
  id: string;
  label: string;
  description?: string;
  hidden?: boolean;
  disabled?: boolean;
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

export function renderTrainingField<TForm extends TrainingFormState>(form: TForm, field: TrainingFieldSpec<TForm>) {
  if (field.hidden) {
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
    h("input", {
      id: field.id,
      disabled: field.disabled,
      value: String(form[field.key] ?? ""),
      placeholder: field.placeholder ?? "",
      onInput: (event: Event) => {
        form[field.key] = (event.target as HTMLInputElement).value as TForm[keyof TForm & string];
      },
    }),
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
