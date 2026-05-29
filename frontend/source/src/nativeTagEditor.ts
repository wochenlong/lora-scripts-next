import { defineComponent, h, onMounted } from "vue";
import { nativeDatasetEditorMarkup } from "./nativeDatasetEditorMarkup";
import "./nativeDatasetEditor.css";

const EDITOR_RUNTIME = "/assets/dataset-editor.js?v=2.6.0";

function ensureDatasetEditorMeta(): HTMLMetaElement {
  const existing = document.querySelector<HTMLMetaElement>(
    'meta[name="sd-dataset-editor-script"]',
  );
  if (existing) {
    existing.content = EDITOR_RUNTIME;
    return existing;
  }

  const meta = document.createElement("meta");
  meta.name = "sd-dataset-editor-script";
  meta.content = EDITOR_RUNTIME;
  document.head.appendChild(meta);
  return meta;
}

function loadEditorRuntime(): HTMLScriptElement {
  const existing = document.querySelector<HTMLScriptElement>(
    'script[data-source-native-editor="runtime"]',
  );
  if (existing) return existing;

  const script = document.createElement("script");
  script.src = EDITOR_RUNTIME;
  script.defer = true;
  script.dataset.sourceNativeEditor = "runtime";
  document.body.appendChild(script);
  return script;
}

export const NativeTagEditorPage = defineComponent({
  name: "NativeTagEditorPage",
  setup() {
    onMounted(() => {
      ensureDatasetEditorMeta();
      loadEditorRuntime();
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
