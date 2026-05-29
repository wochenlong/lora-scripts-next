import { defineComponent, h, onMounted } from "vue";
import "./nativeDatasetEditor.css";

const EDITOR_ENTRY = "/assets/dataset-editor-entry.js?v=2.6.0";
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

function loadEntryScript(): HTMLScriptElement {
  const existing = document.querySelector<HTMLScriptElement>(
    'script[data-source-native-editor="entry"]',
  );
  if (existing) return existing;

  const script = document.createElement("script");
  script.src = EDITOR_ENTRY;
  script.defer = true;
  script.dataset.sourceNativeEditor = "entry";
  document.body.appendChild(script);
  return script;
}

export const NativeTagEditorPage = defineComponent({
  name: "NativeTagEditorPage",
  setup() {
    onMounted(() => {
      ensureDatasetEditorMeta();
      loadEntryScript();
    });

    return () =>
      h("main", { class: "native-editor-page" }, [
        h("section", {
          class: "theme-default-content native-editor-mount",
          "aria-label": "Native Tag Editor",
        }),
      ]);
  },
});
