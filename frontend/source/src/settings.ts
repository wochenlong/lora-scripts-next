import { defineComponent, h, reactive } from "vue";

const UI_CONFIGS_KEY = "ui-configs";
const ADVANCED_LINKS_KEY = "sd-trainer-ui-advanced-links";

type UiConfigs = Record<string, string>;

interface AdvancedLinks {
  showTensorboard: boolean;
  showLegacyTagEditor: boolean;
}

interface FieldConfig {
  key: keyof typeof DEFAULT_UI_CONFIGS;
  label: string;
  description: string;
  type: "text" | "password" | "textarea";
}

const DEFAULT_UI_CONFIGS = {
  dataset_tagger_api_endpoint: "https://api.openai.com/v1",
  dataset_tagger_api_key: "",
  dataset_tagger_api_model: "",
  dataset_tagger_api_prompt:
    "Describe this image for image model training. Return a concise caption only, without markdown or explanations.",
};

const DEFAULT_ADVANCED_LINKS: AdvancedLinks = {
  showTensorboard: false,
  showLegacyTagEditor: false,
};

const FIELDS: FieldConfig[] = [
  {
    key: "dataset_tagger_api_endpoint",
    label: "标签编辑器 API 地址",
    description: "OpenAI-compatible endpoint used by native tag editor API captioning.",
    type: "text",
  },
  {
    key: "dataset_tagger_api_key",
    label: "标签编辑器 API Key",
    description: "Stored locally in the browser and masked in the UI.",
    type: "password",
  },
  {
    key: "dataset_tagger_api_model",
    label: "标签编辑器 API 模型",
    description: "Model name sent to the API captioning provider.",
    type: "text",
  },
  {
    key: "dataset_tagger_api_prompt",
    label: "标签编辑器 API 提示词",
    description: "Prompt used for natural-language dataset captions.",
    type: "textarea",
  },
];

function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? { ...fallback, ...JSON.parse(raw) } : fallback;
  } catch (_err) {
    return fallback;
  }
}

function writeJson(key: string, value: unknown) {
  localStorage.setItem(key, JSON.stringify(value));
}

export const SettingsPage = defineComponent({
  name: "SettingsPage",
  setup() {
    const uiConfigs = reactive<UiConfigs>({
      ...DEFAULT_UI_CONFIGS,
      ...readJson<UiConfigs>(UI_CONFIGS_KEY, {}),
    });
    const advanced = reactive<AdvancedLinks>(
      readJson<AdvancedLinks>(ADVANCED_LINKS_KEY, DEFAULT_ADVANCED_LINKS),
    );
    const status = reactive({ text: "设置仅保存在当前浏览器。API Key 不会写入项目文件。" });

    function save() {
      writeJson(UI_CONFIGS_KEY, uiConfigs);
      writeJson(ADVANCED_LINKS_KEY, advanced);
      status.text = "设置已保存。";
    }

    function reset() {
      Object.assign(uiConfigs, DEFAULT_UI_CONFIGS);
      Object.assign(advanced, DEFAULT_ADVANCED_LINKS);
      save();
      status.text = "已恢复默认设置。";
    }

    function fieldControl(field: FieldConfig) {
      const common = {
        id: field.key,
        value: uiConfigs[field.key] ?? "",
        "aria-label": field.label,
        onInput: (event: Event) => {
          uiConfigs[field.key] = (event.target as HTMLInputElement | HTMLTextAreaElement).value;
        },
      };
      if (field.type === "textarea") {
        return h("textarea", { ...common, rows: 5 });
      }
      return h("input", {
        ...common,
        type: field.type,
        autocomplete: field.type === "password" ? "off" : "on",
      });
    }

    return () =>
      h("section", { class: "settings-page" }, [
        h("div", { class: "settings-header" }, [
          h("p", { class: "eyebrow" }, "Source-owned settings"),
          h("h1", "UI 设置"),
          h("p", { class: "summary" }, "配置原生标签编辑器 API 打标和旧入口显示策略。"),
        ]),
        h(
          "form",
          {
            class: "settings-form",
            onSubmit: (event: Event) => {
              event.preventDefault();
              save();
            },
          },
          [
            h("section", { class: "settings-card" }, [
              h("h2", "标签编辑器 API"),
              ...FIELDS.map((field) =>
                h("label", { class: "settings-field", for: field.key }, [
                  h("span", { class: "settings-label" }, field.label),
                  fieldControl(field),
                  h("small", field.description),
                ]),
              ),
            ]),
            h("section", { class: "settings-card" }, [
              h("h2", "旧功能入口"),
              h("label", { class: "settings-toggle" }, [
                h("input", {
                  type: "checkbox",
                  checked: advanced.showTensorboard,
                  onChange: (event: Event) => {
                    advanced.showTensorboard = (event.target as HTMLInputElement).checked;
                  },
                }),
                h("span", "显示 TensorBoard 入口"),
              ]),
              h("label", { class: "settings-toggle" }, [
                h("input", {
                  type: "checkbox",
                  checked: advanced.showLegacyTagEditor,
                  onChange: (event: Event) => {
                    advanced.showLegacyTagEditor = (event.target as HTMLInputElement).checked;
                  },
                }),
                h("span", "显示经典标签编辑入口"),
              ]),
            ]),
            h("div", { class: "settings-actions" }, [
              h("button", { class: "primary", type: "submit" }, "保存设置"),
              h("button", { type: "button", onClick: reset }, "恢复默认"),
              h("span", { class: "settings-status" }, status.text),
            ]),
          ],
        ),
      ]);
  },
});
