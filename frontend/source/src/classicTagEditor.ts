import { defineComponent, h } from "vue";

export const ClassicTagEditorPage = defineComponent({
  name: "ClassicTagEditorPage",
  setup() {
    return () =>
      h("main", { class: "content classic-tag-editor-page" }, [
        h("header", { class: "classic-tag-editor-header" }, [
          h("div", [
            h("p", { class: "eyebrow" }, "Tools"),
            h("h1", "Classic Tag Editor"),
            h(
              "p",
              { class: "summary" },
              "The classic URL is kept for compatibility, but editing now uses the source-owned native tag editor.",
            ),
          ]),
          h("div", { class: "classic-tag-editor-actions" }, [
            h("a", { class: "classic-tag-editor-open", href: "/native-tageditor.html" }, "Open Native Editor"),
            h(
              "a",
              { class: "classic-tag-editor-open secondary", href: "/native-tageditor-standalone.html" },
              "Open Standalone Editor",
            ),
          ]),
        ]),
        h("section", { class: "classic-tag-editor-panel" }, [
          h("h2", "Source-Owned Replacement"),
          h(
            "p",
            "The legacy Gradio proxy dependency has been removed from this route. Old bookmarks still land here, then continue into the maintained native editor.",
          ),
          h("ul", [
            h("li", "No legacy proxy iframe is required for production dist replacement."),
            h("li", "Native editing remains available at /native-tageditor.html."),
            h("li", "Focused demos can use /native-tageditor-standalone.html."),
          ]),
        ]),
      ]);
  },
});
