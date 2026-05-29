import { h, type VNodeChild } from "vue";

export type TrainingFormState = Record<string, unknown>;

export type TrainingFieldSpec<TForm extends TrainingFormState = TrainingFormState> =
  | {
      kind: "text";
      key: keyof TForm & string;
      id: string;
      label: string;
      placeholder?: string;
    }
  | {
      kind: "number";
      key: keyof TForm & string;
      id: string;
      label: string;
      min?: number;
      step?: string | number;
    }
  | {
      kind: "checkbox";
      key: keyof TForm & string;
      id: string;
      label: string;
    }
  | {
      kind: "select";
      key: keyof TForm & string;
      id: string;
      label: string;
      options: string[];
    }
  | {
      kind: "textarea";
      key: keyof TForm & string;
      id: string;
      label: string;
      rows?: number;
    };

export interface RunControl {
  label: string;
  onClick: () => void | Promise<void>;
  primary?: boolean;
}

export function renderTrainingField<TForm extends TrainingFormState>(form: TForm, field: TrainingFieldSpec<TForm>) {
  if (field.kind === "checkbox") {
    return h("label", { class: "training-toggle anima-toggle" }, [
      h("input", {
        id: field.id,
        type: "checkbox",
        checked: Boolean(form[field.key]),
        onChange: (event: Event) => {
          form[field.key] = (event.target as HTMLInputElement).checked as TForm[keyof TForm & string];
        },
      }),
      h("span", field.label),
    ]);
  }

  if (field.kind === "select") {
    return h("label", { class: "training-field anima-field" }, [
      h("span", field.label),
      h(
        "select",
        {
          id: field.id,
          value: String(form[field.key] ?? ""),
          onChange: (event: Event) => {
            form[field.key] = (event.target as HTMLSelectElement).value as TForm[keyof TForm & string];
          },
        },
        field.options.map((value) => h("option", { value }, value || "auto")),
      ),
    ]);
  }

  if (field.kind === "textarea") {
    return h("label", { class: "training-field anima-field" }, [
      h("span", field.label),
      h("textarea", {
        id: field.id,
        value: String(form[field.key] ?? ""),
        rows: field.rows ?? 4,
        onInput: (event: Event) => {
          form[field.key] = (event.target as HTMLTextAreaElement).value as TForm[keyof TForm & string];
        },
      }),
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
        value: Number(form[field.key] ?? 0),
        onInput: (event: Event) => {
          form[field.key] = Number((event.target as HTMLInputElement).value) as TForm[keyof TForm & string];
        },
      }),
    ]);
  }

  return h("label", { class: "training-field anima-field" }, [
    h("span", field.label),
    h("input", {
      id: field.id,
      value: String(form[field.key] ?? ""),
      placeholder: field.placeholder ?? "",
      onInput: (event: Event) => {
        form[field.key] = (event.target as HTMLInputElement).value as TForm[keyof TForm & string];
      },
    }),
  ]);
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
