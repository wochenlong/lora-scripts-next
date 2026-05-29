import { defineComponent, h, onMounted, onUnmounted, reactive, ref } from "vue";

type TaggerPhase = "idle" | "downloading" | "tagging" | "done" | "error" | "pending" | "cancelling";

interface TaggerForm {
  path: string;
  interrogator_model: string;
  threshold: number;
  character_threshold: number;
  add_rating_tag: boolean;
  add_model_tag: boolean;
  additional_tags: string;
  exclude_tags: string;
  escape_tag: boolean;
  batch_input_recursive: boolean;
  batch_output_action_on_conflict: "copy" | "prepend" | "ignore";
  replace_underscore: boolean;
  download_endpoint: string;
  replace_underscore_excludes: string;
}

interface TaggerStatus {
  phase: TaggerPhase;
  message: string;
  download?: {
    current?: number;
    total?: number;
    filename?: string;
    bytes_current?: number;
    bytes_total?: number;
    percent?: number;
  };
  tagging?: {
    current?: number;
    total?: number;
    filename?: string;
  };
}

const defaultStatus: TaggerStatus = {
  phase: "idle",
  message: "配置参数后点击启动",
  download: { current: 0, total: 0, percent: 0 },
  tagging: { current: 0, total: 0 },
};

const taggerFormDefaults: TaggerForm = {
  path: "",
  interrogator_model: "wd14-convnextv2-v2",
  threshold: 0.35,
  character_threshold: 0.6,
  add_rating_tag: false,
  add_model_tag: false,
  additional_tags: "",
  exclude_tags: "",
  escape_tag: true,
  batch_input_recursive: false,
  batch_output_action_on_conflict: "copy",
  replace_underscore: true,
  download_endpoint: "",
  replace_underscore_excludes:
    "0_0, (o)_(o), +_+, +_-, ._., <o>_<o>, <|>_<|>, =_=, >_<, 3_3, 6_9, >_o, @_@, ^_^, o_o, u_u, x_x, |_|, ||_||",
};

const modelOptions = [
  "wd14-convnextv2-v2",
  "wd-convnext-v3",
  "wd-swinv2-v3",
  "wd-vit-v3",
  "wd14-swinv2-v2",
  "wd14-vit-v2",
  "wd14-moat-v2",
  "wd-eva02-large-tagger-v3",
  "wd-vit-large-tagger-v3",
  "cl_tagger_1_01",
];

function pct(current = 0, total = 0): number {
  if (total <= 0) return 0;
  return Math.min(100, Math.round((current / total) * 100));
}

function downloadPct(status: TaggerStatus): number {
  const download = status.download ?? {};
  if (typeof download.percent === "number") return Math.min(100, Math.round(download.percent));
  const bytesTotal = download.bytes_total ?? 0;
  const bytesCurrent = download.bytes_current ?? 0;
  const fileTotal = download.total ?? 0;
  const fileIndex = download.current ?? 0;
  if (bytesTotal > 0 && fileTotal > 0) {
    return Math.min(100, Math.round(((fileIndex - 1 + bytesCurrent / bytesTotal) / fileTotal) * 100));
  }
  return pct(fileIndex, fileTotal);
}

async function apiPost(path: string, payload: unknown = {}) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return response.json();
}

function field(label: string, control: ReturnType<typeof h>, description?: string) {
  return h("label", { class: "el-form-item tagger-field" }, [
    h("span", { class: "el-form-item__label" }, label),
    control,
    description ? h("small", { class: "el-form-item__description" }, description) : null,
  ]);
}

export const TaggerPage = defineComponent({
  name: "TaggerPage",
  setup() {
    const taggerForm = reactive<TaggerForm>({ ...taggerFormDefaults });
    const taggerStatus = reactive<TaggerStatus>({ ...defaultStatus });
    const statusText = ref("");
    let pollTimer = 0;

    async function refreshStatus() {
      try {
        const result = await fetch("/api/tagger/status").then((response) => response.json());
        Object.assign(taggerStatus, result.data ?? defaultStatus);
      } catch {
        taggerStatus.phase = "error";
        taggerStatus.message = "无法读取 tagger 状态";
      }
    }

    function startPolling() {
      window.clearInterval(pollTimer);
      void refreshStatus();
      pollTimer = window.setInterval(refreshStatus, 1200);
    }

    async function prefetchModel() {
      statusText.value = "正在请求预下载...";
      const result = await apiPost("/api/tagger/prefetch", {
        interrogator_model: taggerForm.interrogator_model,
        download_endpoint: taggerForm.download_endpoint,
      });
      statusText.value = result.message ?? "";
      await refreshStatus();
    }

    async function runTagger() {
      if (!taggerForm.path.trim()) {
        statusText.value = "请先填写图片文件夹路径";
        return;
      }
      statusText.value = "正在提交打标任务...";
      const result = await apiPost("/api/interrogate", {
        ...taggerForm,
        path: taggerForm.path.replaceAll("\\", "/"),
      });
      statusText.value = result.message ?? "";
      await refreshStatus();
    }

    async function cancelTagger() {
      const result = await apiPost("/api/tagger/cancel");
      statusText.value = result.message ?? "";
      await refreshStatus();
    }

    async function resetTagger() {
      const result = await apiPost("/api/tagger/reset");
      statusText.value = result.message ?? "";
      Object.assign(taggerStatus, defaultStatus);
      await refreshStatus();
    }

    onMounted(startPolling);
    onUnmounted(() => window.clearInterval(pollTimer));

    const textInput = (
      id: string,
      key: keyof Pick<
        TaggerForm,
        "path" | "additional_tags" | "exclude_tags" | "download_endpoint" | "replace_underscore_excludes"
      >,
      placeholder = "",
    ) =>
      h("input", {
        id,
        class: "el-input__inner",
        value: taggerForm[key],
        placeholder,
        onInput: (event: Event) => {
          taggerForm[key] = (event.target as HTMLInputElement).value;
        },
      });

    const numberInput = (id: string, key: "threshold" | "character_threshold") =>
      h("input", {
        id,
        type: "number",
        min: 0,
        max: 1,
        step: 0.01,
        value: taggerForm[key],
        onInput: (event: Event) => {
          taggerForm[key] = Number((event.target as HTMLInputElement).value);
        },
      });

    const checkbox = (id: string, key: keyof Pick<TaggerForm, "add_rating_tag" | "add_model_tag" | "escape_tag" | "batch_input_recursive" | "replace_underscore">) =>
      h("label", { class: "tagger-check" }, [
        h("input", {
          id,
          type: "checkbox",
          checked: taggerForm[key],
          onChange: (event: Event) => {
            taggerForm[key] = (event.target as HTMLInputElement).checked;
          },
        }),
        h("span", key),
      ]);

    return () => {
      const dPct = downloadPct(taggerStatus);
      const tPct = pct(taggerStatus.tagging?.current, taggerStatus.tagging?.total);
      const busy = ["downloading", "tagging", "pending", "cancelling"].includes(taggerStatus.phase);

      return h("main", { class: "tagger-page content" }, [
        h("p", { class: "eyebrow" }, "Source-owned tagger"),
        h("h1", "Tagger 标注工具"),
        h("p", { class: "summary" }, "使用本地 WD/CL tagger 模型为数据集批量生成 tag。"),
        h("section", { class: "example-container tagger-workbench" }, [
          h("section", { class: "schema-container tagger-schema" }, [
            h("form", [
              field("path", textInput("tagger-path", "path", "D:/datasets/my-lora/10_character")),
              field(
                "interrogator_model",
                h(
                  "select",
                  {
                    id: "tagger-model",
                    value: taggerForm.interrogator_model,
                    onChange: (event: Event) => {
                      taggerForm.interrogator_model = (event.target as HTMLSelectElement).value;
                    },
                  },
                  modelOptions.map((model) => h("option", { value: model }, model)),
                ),
              ),
              field("threshold", numberInput("tagger-threshold", "threshold")),
              field("character_threshold", numberInput("tagger-character-threshold", "character_threshold")),
              field("additional_tags", textInput("tagger-additional-tags", "additional_tags")),
              field("exclude_tags", textInput("tagger-exclude-tags", "exclude_tags")),
              field("download_endpoint", textInput("tagger-download-endpoint", "download_endpoint")),
              field(
                "batch_output_action_on_conflict",
                h(
                  "select",
                  {
                    id: "tagger-conflict",
                    value: taggerForm.batch_output_action_on_conflict,
                    onChange: (event: Event) => {
                      taggerForm.batch_output_action_on_conflict = (event.target as HTMLSelectElement)
                        .value as TaggerForm["batch_output_action_on_conflict"];
                    },
                  },
                  ["copy", "prepend", "ignore"].map((value) => h("option", { value }, value)),
                ),
              ),
              h("div", { class: "tagger-flags" }, [
                checkbox("tagger-rating", "add_rating_tag"),
                checkbox("tagger-model-tag", "add_model_tag"),
                checkbox("tagger-escape-tag", "escape_tag"),
                checkbox("tagger-recursive", "batch_input_recursive"),
                checkbox("tagger-replace-underscore", "replace_underscore"),
              ]),
            ]),
          ]),
          h("div", { class: "right-container tagger-output" }, [
            h("section", { class: "theme-default-content" }, [
              h("main", [
                h("div", [
                  h("h2", "推荐参数"),
                  h("p", "阈值建议从 0.35 开始，角色阈值建议从 0.6 开始。"),
                  h("p", "启动、预下载、取消、重置和进度轮询现在由 frontend/source/src/tagger.ts 直接处理。"),
                ]),
              ]),
            ]),
            h("section", { id: "sd-tagger-dock", class: `sd-tagger-dock sd-tagger-dock--${taggerStatus.phase}` }, [
              h("div", { class: "sd-tagger-dock__status-line" }, [
                h("span", { class: "sd-tagger-dock__phase", "data-phase": taggerStatus.phase }, taggerStatus.phase),
                h("span", { class: "sd-tagger-dock__message", "data-status-message": "" }, taggerStatus.message),
                h("button", { type: "button", class: "sd-tagger-dock__link", onClick: prefetchModel }, "预下载"),
              ]),
              h("div", { class: "sd-tagger-dock__meters is-visible", "data-meters": "" }, [
                h("div", { class: "sd-tagger-dock__meter", "data-block": "download" }, [
                  h("div", { class: "sd-tagger-dock__meter-head" }, [
                    h("span", "模型下载"),
                    h("span", { "data-download-meta": "" }, `${dPct}%`),
                  ]),
                  h("div", { class: "sd-tagger-dock__track" }, [
                    h("div", {
                      class: "sd-tagger-dock__fill sd-tagger-dock__fill--download",
                      "data-download-bar": "",
                      style: { width: `${dPct}%` },
                    }),
                  ]),
                ]),
                h("div", { class: "sd-tagger-dock__meter", "data-block": "tagging" }, [
                  h("div", { class: "sd-tagger-dock__meter-head" }, [
                    h("span", "打标"),
                    h("span", { "data-tagging-meta": "" }, `${tPct}%`),
                  ]),
                  h("div", { class: "sd-tagger-dock__track" }, [
                    h("div", {
                      class: "sd-tagger-dock__fill sd-tagger-dock__fill--tagging",
                      "data-tagging-bar": "",
                      style: { width: `${tPct}%` },
                    }),
                  ]),
                ]),
              ]),
              h("div", { class: "sd-tagger-dock__buttons" }, [
                h(
                  "button",
                  {
                    type: "button",
                    class: "sd-tagger-dock__start",
                    "data-start-btn": "",
                    onClick: busy ? cancelTagger : runTagger,
                  },
                  busy ? "取消" : "启动",
                ),
                h("button", { type: "button", class: "sd-tagger-dock__reset", onClick: resetTagger }, "重置"),
              ]),
              statusText.value ? h("p", { class: "tagger-local-status" }, statusText.value) : null,
            ]),
            h("section", { id: "test-output" }),
          ]),
        ]),
      ]);
    };
  },
});
