import { createApp, defineComponent, h } from "vue";
import { AnimaRoutePage, isAnimaRoute } from "./anima";
import { NativeTagEditorPage } from "./nativeTagEditor";
import { currentRoute, navGroups, routes } from "./routes";
import { SettingsPage } from "./settings";
import { isStaticInfoRoute, StaticInfoPage } from "./staticPages";
import { TaggerPage } from "./tagger";
import "./styles.css";

const App = defineComponent({
  name: "SourceTrainerShell",
  setup() {
    const route = currentRoute();
    const routeContent =
      route.path === "/other/settings.html"
        ? h(SettingsPage)
        : route.path === "/tagger.html"
          ? h(TaggerPage)
        : route.path === "/native-tageditor.html" || route.path === "/dataset-editor.html"
          ? h(NativeTagEditorPage)
        : isAnimaRoute(route.path)
          ? h(AnimaRoutePage, { route })
        : isStaticInfoRoute(route.path)
          ? h(StaticInfoPage, { route })
        : h("main", { class: "content" }, [
            h("p", { class: "eyebrow" }, "Source-owned frontend shell"),
            h("h1", route.title),
            h("p", { class: "summary" }, route.description),
            h("section", { class: "compat-panel" }, [
              h("h2", "Compatibility Contract"),
              h("ul", [
                h("li", "Public routes are declared in frontend/source/src/routes.json."),
                h(
                  "li",
                  "The production output is static HTML/CSS/JS and can be served by FastAPI StaticFiles.",
                ),
                h("li", "Build tooling stays in frontend/source and is not required at portable runtime."),
              ]),
            ]),
          ]);
    return () =>
      h("div", { class: "shell" }, [
        h("aside", { class: "sidebar", "aria-label": "Trainer navigation" }, [
          h("a", { class: "brand", href: "/" }, "SD Trainer Next"),
          ...navGroups.map((group) =>
            h("section", { class: "nav-group" }, [
              h("h2", group.label),
              h(
                "nav",
                routes
                  .filter((item) => item.section === group.section)
                  .map((item) =>
                    h(
                      "a",
                      {
                        href: item.path,
                        class: item.path === route.path ? "active" : "",
                      },
                      item.title,
                    ),
                  ),
              ),
            ]),
          ),
        ]),
        routeContent,
      ]);
  },
});

createApp(App).mount("#app");
