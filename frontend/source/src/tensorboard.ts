import { defineComponent, h } from "vue";

export const TensorboardPage = defineComponent({
  name: "TensorboardPage",
  setup() {
    return () =>
      h("main", { class: "content tensorboard-page" }, [
        h("header", { class: "tensorboard-header" }, [
          h("div", [
            h("p", { class: "eyebrow" }, "Monitoring"),
            h("h1", "TensorBoard"),
            h(
              "p",
              { class: "summary" },
              "TensorBoard is started by the GUI process and exposed through the local proxy.",
            ),
          ]),
          h("div", { class: "tensorboard-actions" }, [
            h("a", { href: "/proxy/tensorboard/", target: "_blank", rel: "noreferrer" }, "Open TensorBoard"),
            h("a", { href: "/task.html" }, "Open Tasks"),
          ]),
        ]),
        h("section", { class: "tensorboard-panel" }, [
          h("div", { class: "tensorboard-panel__status" }, [
            h("strong", "Proxy route"),
            h("code", "/proxy/tensorboard/"),
            h("span", "If the frame is empty, start a training run or confirm TensorBoard is enabled in gui.py."),
          ]),
          h("iframe", {
            class: "tensorboard-frame",
            src: "/proxy/tensorboard/",
            title: "TensorBoard",
          }),
        ]),
      ]);
  },
});
