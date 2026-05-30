import { defineComponent, h } from "vue";
import type { AppRoute } from "./routes";

interface MatureTrainingSpec {
  family: string;
  backend: string;
  posture: string;
  migrateWhen: string;
}

const matureTrainingSpecs: Record<string, MatureTrainingSpec> = {
  "/lora/basic.html": {
    family: "LoRA compatibility",
    backend: "Stable Diffusion LoRA presets",
    posture: "Stable URL, source-owned shell, mature form deferred.",
    migrateWhen: "Only migrate if this page needs active product changes.",
  },
  "/lora/master.html": {
    family: "Stable Diffusion compatibility",
    backend: "Stable Diffusion trainer",
    posture: "Keep mature SD behavior untouched while source renderer work focuses on Anima.",
    migrateWhen: "Reuse the shared schema renderer if SD training becomes active work.",
  },
  "/lora/flux.html": {
    family: "Flux compatibility",
    backend: "Flux LoRA trainer",
    posture: "Keep Flux launch contracts stable and avoid hand-editing production dist.",
    migrateWhen: "Attach Flux schema sections after renderer coverage is broader.",
  },
  "/dreambooth/index.html": {
    family: "Dreambooth compatibility",
    backend: "Dreambooth trainer",
    posture: "Preserve links without rebuilding mature Dreambooth behavior.",
    migrateWhen: "Promote only if Dreambooth needs source-owned UI changes.",
  },
};

export function isMatureTrainingRoute(path: string): boolean {
  return path in matureTrainingSpecs;
}

export const MatureTrainingPage = defineComponent({
  name: "MatureTrainingPage",
  props: {
    route: {
      type: Object as () => AppRoute,
      required: true,
    },
  },
  setup(props) {
    return () => {
      const spec = matureTrainingSpecs[props.route.path];
      return h("main", { class: "content training-compat-page" }, [
        h("header", { class: "training-compat-header" }, [
          h("div", [
            h("p", { class: "eyebrow" }, "Training"),
            h("h1", props.route.title),
            h("p", { class: "summary" }, spec.posture),
          ]),
          h("dl", { class: "training-compat-route" }, [
            h("dt", "Route"),
            h("dd", props.route.path),
            h("dt", "Template"),
            h("dd", "mature training compatibility"),
          ]),
        ]),
        h("section", { class: "training-compat-metrics" }, [
          h("article", [h("span", "Family"), h("strong", spec.family)]),
          h("article", [h("span", "Backend"), h("strong", spec.backend)]),
          h("article", [h("span", "Migration Rule"), h("strong", spec.migrateWhen)]),
        ]),
        h("section", { class: "compat-panel training-compat-contract" }, [
          h("h2", "Source Contract"),
          h("ul", [
            h("li", "This mature training page is generated from one reusable source template."),
            h("li", "Backend launch behavior and portable paths are not changed by this compatibility page."),
            h("li", "Anima remains the active source-owned training form while this route stays stable."),
          ]),
        ]),
        h("div", { class: "source-static-actions" }, [
          h("a", { class: "source-static-action", href: "/lora/index.html" }, "Open Training Index"),
          h("a", { class: "source-static-action", href: "/lora/sd3.html" }, "Open Anima LoRA"),
          h("a", { class: "source-static-action", href: "/lora/params.html" }, "Open Parameters"),
        ]),
      ]);
    };
  },
});
