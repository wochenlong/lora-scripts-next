import { defineComponent, h } from "vue";
import type { AppRoute } from "./routes";

interface AnimaRoutePlan {
  path: string;
  heading: string;
  modelTrainType: "anima-lora" | "anima-finetune";
  schemaFile: string;
  backendEntrypoint: string;
  summary: string;
  nextWork: string[];
}

const ANIMA_ROUTES: Record<string, AnimaRoutePlan> = {
  "/lora/sd3.html": {
    path: "/lora/sd3.html",
    heading: "Anima Stable Diffusion LoRA",
    modelTrainType: "anima-lora",
    schemaFile: "mikazuki/schema/sd3-lora.ts",
    backendEntrypoint: "scripts/dev/anima_train_network.py",
    summary: "Preserves the historical sd3 URL while routing to the Anima LoRA backend.",
    nextWork: [
      "Move Anima LoRA form sections from schema-driven runtime into source-owned components.",
      "Keep the sd3-lora route key stable for saved configs and old links.",
      "Add browser smoke before replacing the production dist route.",
    ],
  },
  "/lora/anima-finetune.html": {
    path: "/lora/anima-finetune.html",
    heading: "Anima Finetune",
    modelTrainType: "anima-finetune",
    schemaFile: "mikazuki/schema/anima-finetune.ts",
    backendEntrypoint: "scripts/dev/anima_train.py",
    summary: "Tracks full DiT finetune work without touching SD or Flux training pages.",
    nextWork: [
      "Source-own the high-risk Anima full finetune options first.",
      "Keep full finetune defaults aligned with backend adapter tests.",
      "Add save/load config compatibility checks before production replacement.",
    ],
  },
};

export function isAnimaRoute(path: string): boolean {
  return path in ANIMA_ROUTES;
}

export const AnimaRoutePage = defineComponent({
  name: "AnimaRoutePage",
  props: {
    route: {
      type: Object as () => AppRoute,
      required: true,
    },
  },
  setup(props) {
    const plan = ANIMA_ROUTES[props.route.path];
    return () =>
      h("main", { class: "content anima-page" }, [
        h("p", { class: "eyebrow" }, "Anima source route"),
        h("h1", plan.heading),
        h("p", { class: "summary" }, plan.summary),
        h("section", { class: "anima-grid" }, [
          h("article", { class: "compat-panel" }, [
            h("h2", "Stable Contract"),
            h("dl", { class: "anima-contract" }, [
              h("dt", "Route"),
              h("dd", plan.path),
              h("dt", "model_train_type"),
              h("dd", plan.modelTrainType),
              h("dt", "Schema"),
              h("dd", plan.schemaFile),
              h("dt", "Backend entrypoint"),
              h("dd", plan.backendEntrypoint),
            ]),
          ]),
          h("article", { class: "compat-panel" }, [
            h("h2", "Migration Notes"),
            h(
              "ul",
              plan.nextWork.map((item) => h("li", item)),
            ),
          ]),
        ]),
      ]);
  },
});
