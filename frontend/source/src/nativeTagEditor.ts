import { defineComponent, h, onMounted } from "vue";
import { nativeDatasetEditorMarkup } from "./nativeDatasetEditorMarkup";
import "./nativeDatasetEditor.css";

export const NativeTagEditorPage = defineComponent({
  name: "NativeTagEditorPage",
  props: {
    standalone: {
      type: Boolean,
      default: false,
    },
  },
  setup(props) {
    onMounted(() => {
      void import("./nativeDatasetEditorRuntime");
    });

    return () =>
      h("main", { class: ["native-editor-page", props.standalone ? "native-editor-page--standalone" : ""] }, [
        h("section", {
          id: "sd-native-editor-entry",
          class: "theme-default-content native-editor-mount",
          "aria-label": "Native Tag Editor",
          innerHTML: nativeDatasetEditorMarkup,
        }),
      ]);
  },
});
