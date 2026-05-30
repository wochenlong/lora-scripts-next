import { defineComponent, h } from "vue";
import { ANIMA_ROUTES, animaSectionsForPlan } from "./animaSchema";
import type { AnimaForm } from "./animaSchema";
import type { TrainingFieldSpec, TrainingSectionItem } from "./trainingRenderer";

function flattenFields(items: TrainingSectionItem<AnimaForm>[]): TrainingFieldSpec<AnimaForm>[] {
  return items.flatMap((item) => (item.kind === "row" ? item.fields : [item]));
}

function fieldKind(field: TrainingFieldSpec<AnimaForm>) {
  if (field.role === "file" || field.role === "folder") return field.role;
  if (field.role === "slider" || field.role === "table") return field.role;
  return field.kind;
}

export const ParametersPage = defineComponent({
  name: "ParametersPage",
  setup() {
    const loraPlan = ANIMA_ROUTES["/lora/sd3.html"];
    const finetunePlan = ANIMA_ROUTES["/lora/anima-finetune.html"];
    const sections = animaSectionsForPlan(loraPlan);

    return () =>
      h("main", { class: "content params-page" }, [
        h("header", { class: "params-header" }, [
          h("div", [
            h("p", { class: "eyebrow" }, "Reference"),
            h("h1", "Training Parameters"),
            h(
              "p",
              { class: "summary" },
              "Source-owned parameter reference generated from the Anima schema renderer specs.",
            ),
          ]),
          h("div", { class: "params-actions" }, [
            h("a", { href: loraPlan.path }, "Open Anima LoRA"),
            h("a", { href: finetunePlan.path }, "Open Anima Finetune"),
          ]),
        ]),
        h("section", { class: "params-summary-grid" }, [
          h("article", [h("strong", String(sections.length)), h("span", "schema sections")]),
          h("article", [
            h("strong", String(sections.reduce((total, section) => total + flattenFields(section.fields).length, 0))),
            h("span", "documented fields"),
          ]),
          h("article", [h("strong", "source"), h("span", "frontend/source/src/animaSchema.ts")]),
        ]),
        h(
          "section",
          { class: "params-section-list", "aria-label": "Anima parameter sections" },
          sections.map((section) =>
            h("article", { class: "params-section-card" }, [
              h("header", [
                h("h2", section.title),
                h("span", `${flattenFields(section.fields).length} fields`),
              ]),
              h(
                "div",
                { class: "params-field-list" },
                flattenFields(section.fields).map((field) =>
                  h("div", { class: "params-field-row" }, [
                    h("code", field.label),
                    h("span", fieldKind(field)),
                    field.visibleWhen ? h("small", "conditional") : null,
                    field.description ? h("p", field.description) : null,
                  ]),
                ),
              ),
            ]),
          ),
        ),
      ]);
  },
});
