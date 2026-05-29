import { defineComponent, h, onMounted } from "vue";
import { nativeDatasetEditorMarkup } from "./nativeDatasetEditorMarkup";
import "./nativeDatasetEditor.css";

export const NativeTagEditorPage = defineComponent({
  name: "NativeTagEditorPage",
  setup() {
    onMounted(() => {
      void import("./nativeDatasetEditorRuntime");
    });

    return () =>
      h("main", { class: "native-editor-page" }, [
        h("section", {
          id: "sd-native-editor-entry",
          class: "theme-default-content native-editor-mount",
          "aria-label": "Native Tag Editor",
          innerHTML: nativeDatasetEditorMarkup,
        }),
      ]);
  },
});
