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
              "Classic tag editing stays on this route while the native editor remains separate.",
            ),
          ]),
          h("a", { class: "classic-tag-editor-open", href: "/proxy/tageditor/", target: "_blank" }, "Open Classic Editor"),
        ]),
        h("section", { class: "classic-tag-editor-frame-wrap" }, [
          h("iframe", {
            title: "Classic Tag Editor",
            src: "/proxy/tageditor/",
            class: "classic-tag-editor-frame",
          }),
        ]),
      ]);
  },
});
