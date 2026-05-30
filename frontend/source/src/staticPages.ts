import { defineComponent, h } from "vue";
import type { AppRoute } from "./routes";

interface StaticInfoPageSpec {
  kicker: string;
  title: string;
  body: string;
  actions: { label: string; href: string }[];
  checks: string[];
}

const staticInfoPages: Record<string, StaticInfoPageSpec> = {
  "/tageditor.html": {
    kicker: "Tools",
    title: "Classic Tag Editor",
    body:
      "Source-owned compatibility entry for the classic tag editor route. It stays separate from the native tag editor while production dist replacement is prepared.",
    actions: [
      { label: "Open Native Tag Editor", href: "/native-tageditor.html" },
      { label: "Open Dataset Debug", href: "/dataset-editor.html" },
    ],
    checks: [
      "Classic tag editor remains a separate compatibility entry.",
      "Native tag editing stays on /native-tageditor.html.",
      "The dataset-editor fallback remains available for debugging.",
    ],
  },
  "/lora/index.html": {
    kicker: "Training",
    title: "LoRA Training",
    body:
      "Source-owned training index for stable links while mature training pages continue to keep their backend contracts.",
    actions: [
      { label: "Open Anima LoRA", href: "/lora/sd3.html" },
      { label: "Open Anima Finetune", href: "/lora/anima-finetune.html" },
    ],
    checks: [
      "Mature training routes remain compatibility entries until their schemas are intentionally migrated.",
      "Anima routes are source-owned and share the local training renderer.",
      "This page replaces the generic compatibility placeholder for /lora/index.html.",
    ],
  },
  "/lora/basic.html": {
    kicker: "Training",
    title: "Basic Training",
    body:
      "Compatibility route for the basic LoRA training page. The source shell keeps the URL stable without changing mature training behavior.",
    actions: [
      { label: "Open LoRA Index", href: "/lora/index.html" },
      { label: "Open Settings", href: "/other/settings.html" },
    ],
    checks: [
      "Mature training routes remain compatibility entries.",
      "No SD/Flux training backend contract is changed by this source page.",
      "Future migration can attach a schema section module to this route.",
    ],
  },
  "/lora/master.html": {
    kicker: "Training",
    title: "Stable Diffusion Training",
    body:
      "Compatibility route for Stable Diffusion training. It is intentionally not rebuilt while the Anima source renderer is being stabilized.",
    actions: [
      { label: "Open LoRA Index", href: "/lora/index.html" },
      { label: "Open Parameter Notes", href: "/lora/params.html" },
    ],
    checks: [
      "Mature training routes remain compatibility entries.",
      "The route is declared and generated from frontend/source.",
      "Schema renderer improvements can be reused here later.",
    ],
  },
  "/lora/flux.html": {
    kicker: "Training",
    title: "Flux LoRA",
    body:
      "Compatibility route for Flux LoRA training. The source shell owns the route while avoiding changes to the mature Flux form.",
    actions: [
      { label: "Open LoRA Index", href: "/lora/index.html" },
      { label: "Open Tools", href: "/lora/tools.html" },
    ],
    checks: [
      "Mature training routes remain compatibility entries.",
      "Flux backend and launch behavior are not changed here.",
      "The route no longer depends on a generic placeholder in the source build.",
    ],
  },
  "/dreambooth/index.html": {
    kicker: "Training",
    title: "Dreambooth",
    body:
      "Source-owned compatibility route for Dreambooth links while training schema migration remains focused on Anima.",
    actions: [
      { label: "Open LoRA Index", href: "/lora/index.html" },
      { label: "Open Settings", href: "/other/settings.html" },
    ],
    checks: [
      "Mature training routes remain compatibility entries.",
      "Dreambooth route generation is now covered by frontend/source.",
      "No Dreambooth training behavior is changed by this page.",
    ],
  },
  "/lora/params.html": {
    kicker: "Reference",
    title: "Training Parameters",
    body:
      "Source-owned parameter reference route reserved for renderer and schema migration notes.",
    actions: [
      { label: "Open Anima LoRA", href: "/lora/sd3.html" },
      { label: "Open Changelog", href: "/other/changelog.html" },
    ],
    checks: [
      "Mature training routes remain compatibility entries.",
      "Parameter documentation can now evolve from source files.",
      "The route keeps historical links stable.",
    ],
  },
  "/tensorboard.html": {
    kicker: "Monitoring",
    title: "TensorBoard",
    body:
      "This source-owned page preserves the TensorBoard route while the backend service remains launched by the trainer process.",
    actions: [
      { label: "Open TensorBoard", href: "/tensorboard/" },
      { label: "Launch tensorboard.py", href: "/api/tensorboard/start" },
    ],
    checks: [
      "Route stays available as /tensorboard.html.",
      "The page does not bundle or start TensorBoard at portable runtime.",
      "Navigation remains source-owned instead of patched into compiled VuePress assets.",
    ],
  },
  "/lora/tools.html": {
    kicker: "Tools",
    title: "LoRA Script Tools",
    body:
      "A source-owned landing page for script utilities, kept separate from the mature SD and Flux training forms.",
    actions: [
      { label: "Open Source Frontend", href: "/lora/tools.html" },
      { label: "Review scripts/run_gui.py", href: "/other/about.html" },
    ],
    checks: [
      "The public tools URL is generated from frontend/source.",
      "Tooling notes stay visible without editing frontend/dist by hand.",
      "Future utility controls can be added here without touching training schemas.",
    ],
  },
  "/task.html": {
    kicker: "Runtime",
    title: "Tasks",
    body:
      "This page reserves the task route for source-owned job status UI while backend task APIs are kept unchanged.",
    actions: [
      { label: "Open Tasks", href: "/task.html" },
      { label: "Open Settings", href: "/other/settings.html" },
    ],
    checks: [
      "The task route has a real source page instead of a generic compatibility placeholder.",
      "Backend execution contracts stay outside this static page.",
      "The page can grow into a task monitor after the source renderer stabilizes.",
    ],
  },
  "/help/guide.html": {
    kicker: "Help",
    title: "Getting Started",
    body:
      "A source-owned guide route for workflow notes and frontend migration status, independent from vendored VuePress page data.",
    actions: [
      { label: "Open Guide", href: "/help/guide.html" },
      { label: "Open Native Tag Editor", href: "/native-tageditor.html" },
    ],
    checks: [
      "Guide content is now editable from frontend/source.",
      "The native tag editor route remains a separate entry.",
      "Classic tag editor fallback stays available through /tageditor.html.",
    ],
  },
  "/other/about.html": {
    kicker: "Project",
    title: "About SD Trainer Next",
    body:
      "This route records the source frontend ownership boundary and keeps project metadata out of minified dist patches.",
    actions: [
      { label: "Open Settings", href: "/other/settings.html" },
      { label: "Open Source Routes", href: "/" },
    ],
    checks: [
      "Source pages live under frontend/source.",
      "Generated output targets build/frontend-source-dist.",
      "Production replacement is guarded by scripts/sync_frontend_source_dist.py.",
    ],
  },
  "/other/changelog.html": {
    kicker: "Release Notes",
    title: "Changelog",
    body:
      "A source-owned changelog route for visible frontend migration checkpoints before production dist replacement.",
    actions: [
      { label: "Open Changelog", href: "/other/changelog.html" },
      { label: "Open About", href: "/other/about.html" },
    ],
    checks: [
      "Native tag editor, tagger, settings, and Anima source routes are tracked in docs/design/frontend-source-of-truth-plan.md.",
      "Manual frontend/dist surgery is being retired in small verified steps.",
      "The current branch keeps frontend/dist unchanged until the sync step is explicitly applied.",
    ],
  },
};

export function isStaticInfoRoute(path: string): boolean {
  return path in staticInfoPages;
}

export const StaticInfoPage = defineComponent({
  name: "StaticInfoPage",
  props: {
    route: {
      type: Object as () => AppRoute,
      required: true,
    },
  },
  setup(props) {
    return () => {
      const spec = staticInfoPages[props.route.path] ?? {
        kicker: "Compatibility",
        title: props.route.title,
        body: props.route.description,
        actions: [{ label: "Open Route", href: props.route.path }],
        checks: ["This route is declared in frontend/source/src/routes.json."],
      };

      return h("main", { class: "content source-static-page" }, [
        h("p", { class: "eyebrow" }, spec.kicker),
        h("h1", spec.title),
        h("p", { class: "summary" }, spec.body),
        h(
          "div",
          { class: "source-static-actions" },
          spec.actions.map((action) =>
            h("a", { class: "source-static-action", href: action.href }, action.label),
          ),
        ),
        h("section", { class: "compat-panel source-static-contract" }, [
          h("h2", "Source Contract"),
          h(
            "ul",
            spec.checks.map((check) => h("li", check)),
          ),
        ]),
      ]);
    };
  },
});
