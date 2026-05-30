import { defineComponent, h } from "vue";
import { routes, type AppRoute } from "./routes";

interface StaticInfoPageSpec {
  kicker: string;
  title: string;
  body: string;
  actions: { label: string; href: string }[];
  checks: string[];
  status?: string;
  nextStep?: string;
}

const staticInfoPages: Record<string, StaticInfoPageSpec> = {
  "/": {
    kicker: "Source Frontend",
    title: "SD Trainer Next",
    body:
      "Source-owned trainer home for the frontend recovery branch. It keeps stable navigation while native editor, tagger, settings, and Anima routes move out of compiled dist patches.",
    actions: [
      { label: "Open Anima LoRA", href: "/lora/sd3.html" },
      { label: "Open Native Tag Editor", href: "/native-tageditor.html" },
      { label: "Open Settings", href: "/other/settings.html" },
    ],
    checks: [
      "Source frontend home is owned by frontend/source.",
      "Production dist replacement remains guarded by dry-run sync.",
      "Mature SD/Flux training routes remain compatibility entries.",
    ],
    status: "Source-owned shell",
    nextStep: "Promote the remaining compatibility routes into reusable source renderers.",
  },
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
    status: "Preserved by legacy island",
    nextStep: "Keep the classic editor available while native editing matures.",
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
    status: "Source-owned index",
    nextStep: "Link migrated Anima pages with mature training compatibility entries.",
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
    status: "Compatibility route",
    nextStep: "Reuse the training schema renderer only if this mature page needs changes.",
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
    status: "Compatibility route",
    nextStep: "Keep this page stable while Anima training is completed first.",
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
    status: "Compatibility route",
    nextStep: "Defer Flux form migration until source renderer coverage is broader.",
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
    status: "Compatibility route",
    nextStep: "Keep Dreambooth links stable while source training pages expand.",
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
    status: "Reference route",
    nextStep: "Move parameter documentation into source-owned structured content.",
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
    status: "Runtime bridge route",
    nextStep: "Add a source-owned launch/status panel after task APIs are stabilized.",
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
    status: "Tools route",
    nextStep: "Add concrete tool actions from source-owned route specs.",
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
    status: "Task route shell",
    nextStep: "Connect backend task status once the frontend replacement path is stable.",
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
    status: "Guide route",
    nextStep: "Move getting-started copy into source-owned documentation blocks.",
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
    status: "Project route",
    nextStep: "Expose source ownership and packaging boundaries from maintained docs.",
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
    status: "Migration route",
    nextStep: "Show frontend-source milestones from maintained release notes.",
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
        status: "Compatibility route",
        nextStep: "Promote this route into a source-owned page when it becomes active work.",
      };
      const cards = [
        {
          title: "Current Coverage",
          body: spec.status ?? "Source-owned compatibility route",
        },
        {
          title: "Next Source Step",
          body: spec.nextStep ?? spec.checks[0],
        },
        {
          title: "Safety Contract",
          body: spec.checks[1] ?? "Keep backend and portable runtime contracts unchanged.",
        },
      ];

      return h("main", { class: "content source-static-page" }, [
        h("header", { class: "source-static-hero" }, [
          h("div", [
            h("p", { class: "eyebrow" }, spec.kicker),
            h("h1", spec.title),
            h("p", { class: "summary" }, spec.body),
          ]),
          h("dl", { class: "source-static-meta" }, [
            h("dt", "Route"),
            h("dd", props.route.path),
            h("dt", "Status"),
            h("dd", spec.status ?? "Compatibility route"),
          ]),
        ]),
        h(
          "div",
          { class: "source-static-actions" },
          spec.actions.map((action) =>
            h("a", { class: "source-static-action", href: action.href }, action.label),
          ),
        ),
        h(
          "section",
          { class: "source-static-grid", "aria-label": "Source page status" },
          cards.map((card) =>
            h("article", { class: "source-static-card" }, [
              h("h2", card.title),
              h("p", card.body),
            ]),
          ),
        ),
        h("p", { class: "source-static-status" }, spec.nextStep ?? spec.checks[0]),
        renderRouteHub(props.route),
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

function renderRouteHub(route: AppRoute) {
  const hub = routeHubFor(route.path);
  if (!hub) {
    return null;
  }

  const trainingRoutes = routes.filter(
    (item) => item.section === hub.section && item.path !== route.path,
  );

  return h("section", { class: "source-route-list", "aria-label": "Training routes" }, [
    h("div", { class: "source-route-list__header" }, [
      h("h2", hub.title),
      h("p", hub.body),
    ]),
    h(
      "div",
      { class: "source-route-list__grid" },
      trainingRoutes.map((item) =>
        h("a", { class: "source-route-card", href: item.path }, [
          h("span", { class: "source-route-card__section" }, routeStatus(item.path)),
          h("strong", item.title),
          h("small", item.description),
        ]),
      ),
    ),
  ]);
}

function routeHubFor(path: string) {
  if (path === "/lora/index.html") {
    return {
      section: "training" as const,
      title: "Training Routes",
      body:
        "Anima routes are source-owned now; mature SD, Flux, and Dreambooth routes stay as compatibility entries.",
    };
  }
  if (path === "/lora/tools.html") {
    return {
      section: "tools" as const,
      title: "Tool Routes",
      body:
        "Tool and debugging routes are declared from source so they can be migrated without editing compiled dist assets.",
    };
  }
  return null;
}

function routeStatus(path: string) {
  if (path === "/lora/sd3.html" || path === "/lora/anima-finetune.html") {
    return "Source renderer";
  }
  if (path === "/native-tageditor.html" || path === "/dataset-editor.html" || path === "/tagger.html") {
    return "Source-owned tool";
  }
  if (path === "/tageditor.html") {
    return "Legacy island";
  }
  return "Compatibility route";
}
