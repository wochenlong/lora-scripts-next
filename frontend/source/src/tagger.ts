import { defineComponent, h, onMounted } from "vue";

const TAGGER_PROGRESS_SCRIPT = "/assets/tagger-progress.js?v=2.6.0";

function loadTaggerProgress(): HTMLScriptElement {
  const existing = document.querySelector<HTMLScriptElement>(
    'script[data-source-tagger="progress"]',
  );
  if (existing) return existing;

  const script = document.createElement("script");
  script.src = TAGGER_PROGRESS_SCRIPT;
  script.defer = true;
  script.dataset.sourceTagger = "progress";
  document.body.appendChild(script);
  return script;
}

function field(label: string, control: ReturnType<typeof h>, description?: string) {
  return h("label", { class: "el-form-item tagger-field" }, [
    h("span", { class: "el-form-item__label" }, label),
    control,
    description ? h("small", { class: "el-form-item__description" }, description) : null,
  ]);
}

function textInput(id: string, value = "", placeholder = "") {
  return h("input", {
    id,
    class: "el-input__inner",
    value,
    placeholder,
  });
}

function numberInput(id: string, value: number, min = 0, max = 1, step = 0.01) {
  return h("input", {
    id,
    type: "number",
    min,
    max,
    step,
    value,
  });
}

function switchControl(id: string, checked = false) {
  return h("span", { class: checked ? "el-switch is-checked" : "el-switch" }, [
    h("input", { id, type: "checkbox", checked }),
  ]);
}

export const TaggerPage = defineComponent({
  name: "TaggerPage",
  setup() {
    onMounted(() => {
      loadTaggerProgress();
    });

    return () =>
      h("main", { class: "tagger-page content" }, [
        h("p", { class: "eyebrow" }, "Source-owned tagger"),
        h("h1", "Tagger 标注工具"),
        h("p", { class: "summary" }, "使用本地 WD/CL tagger 模型为数据集批量生成 tag。"),
        h("section", { class: "example-container tagger-workbench" }, [
          h("section", { class: "schema-container tagger-schema" }, [
            h("form", [
              field(
                "path",
                textInput("tagger-path", "", "D:/datasets/my-lora/10_character"),
                "图片文件夹路径。",
              ),
              field(
                "interrogator_model",
                textInput("tagger-model", "wd14-convnextv2-v2"),
                "默认使用 portable 预置模型；可填写其他可用模型 key。",
              ),
              field("threshold", numberInput("tagger-threshold", 0.35)),
              field("character_threshold", numberInput("tagger-character-threshold", 0.6)),
              field("additional_tags", textInput("tagger-additional-tags")),
              field("download_endpoint", textInput("tagger-download-endpoint")),
              field("add_rating_tag", switchControl("tagger-rating")),
              field("add_model_tag", switchControl("tagger-model-tag")),
              field("replace_underscore", switchControl("tagger-replace-underscore", true)),
              field("escape_tag", switchControl("tagger-escape-tag", true)),
              field("batch_input_recursive", switchControl("tagger-recursive")),
              field(
                "batch_output_action_on_conflict",
                h("select", { id: "tagger-conflict", value: "copy" }, [
                  h("option", { value: "copy" }, "copy"),
                  h("option", { value: "prepend" }, "prepend"),
                  h("option", { value: "ignore" }, "ignore"),
                ]),
              ),
            ]),
          ]),
          h("div", { class: "right-container tagger-output" }, [
            h("section", { class: "theme-default-content" }, [
              h("main", [
                h("div", [
                  h("h2", "推荐参数"),
                  h("p", "阈值建议从 0.35 开始，角色阈值建议从 0.6 开始。"),
                  h("p", "启动、预下载、取消和进度轮询由 source-owned tagger progress asset 处理。"),
                ]),
              ]),
            ]),
            h("button", { class: "el-button", type: "button" }, "启动"),
            h("button", { class: "el-button", type: "button" }, "全部重置"),
            h("section", { id: "test-output" }),
          ]),
        ]),
      ]);
  },
});
