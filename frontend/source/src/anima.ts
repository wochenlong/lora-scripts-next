import { defineComponent, h, reactive, ref } from "vue";
import type { AppRoute } from "./routes";

interface AnimaRoutePlan {
  path: string;
  heading: string;
  modelTrainType: "anima-lora" | "anima-finetune";
  schemaFile: string;
  backendEntrypoint: string;
  summary: string;
  nextWork: string[];
}

interface AnimaForm {
  pretrained_model_name_or_path: string;
  vae: string;
  qwen3: string;
  t5_tokenizer_path: string;
  train_data_dir: string;
  output_dir: string;
  output_name: string;
  lora_type: "lora" | "lokr" | "tlora" | "lora_fa" | "vera" | "loha";
  max_train_epochs: number;
  train_batch_size: number;
  gradient_accumulation_steps: number;
  learning_rate: string;
  unet_lr: string;
  network_dim: number;
  network_alpha: number;
  resolution: string;
  mixed_precision: "bf16" | "fp16" | "no";
  optimizer_type: string;
  attn_mode: "" | "torch" | "xformers" | "sageattn" | "flash";
  timestep_sampling: "sigma" | "uniform" | "sigmoid" | "shift" | "flux_shift";
  discrete_flow_shift: number;
  gradient_checkpointing: boolean;
  cache_latents: boolean;
  cache_latents_to_disk: boolean;
  cache_text_encoder_outputs: boolean;
  cache_text_encoder_outputs_to_disk: boolean;
  enable_preview: boolean;
  positive_prompts: string;
  negative_prompts: string;
  sample_width: number;
  sample_height: number;
  sample_cfg: number;
  sample_seed: number;
  sample_steps: number;
  sample_every_n_epochs: number;
  sample_prompts: string;
  caption_extension: string;
  prefer_json_caption: boolean;
}

type TextKey =
  | "pretrained_model_name_or_path"
  | "vae"
  | "qwen3"
  | "t5_tokenizer_path"
  | "train_data_dir"
  | "output_dir"
  | "output_name"
  | "learning_rate"
  | "unet_lr"
  | "resolution"
  | "optimizer_type"
  | "caption_extension";

type NumberKey =
  | "max_train_epochs"
  | "train_batch_size"
  | "gradient_accumulation_steps"
  | "network_dim"
  | "network_alpha"
  | "discrete_flow_shift"
  | "sample_width"
  | "sample_height"
  | "sample_cfg"
  | "sample_seed"
  | "sample_steps"
  | "sample_every_n_epochs";

type BooleanKey =
  | "gradient_checkpointing"
  | "cache_latents"
  | "cache_latents_to_disk"
  | "cache_text_encoder_outputs"
  | "cache_text_encoder_outputs_to_disk"
  | "enable_preview"
  | "prefer_json_caption";

const ANIMA_STORAGE_KEY = "sd-trainer-source-anima-configs";

const ANIMA_ROUTES: Record<string, AnimaRoutePlan> = {
  "/lora/sd3.html": {
    path: "/lora/sd3.html",
    heading: "Anima Stable Diffusion LoRA",
    modelTrainType: "anima-lora",
    schemaFile: "mikazuki/schema/sd3-lora.ts",
    backendEntrypoint: "scripts/dev/anima_train_network.py",
    summary: "Preserves the historical sd3 URL while routing to the Anima LoRA backend.",
    nextWork: [
      "Move Anima LoRA form sections from schema-driven runtime into source-owned components.",
      "Keep the sd3-lora route key stable for saved configs and old links.",
      "Add browser smoke before replacing the production dist route.",
    ],
  },
  "/lora/anima-finetune.html": {
    path: "/lora/anima-finetune.html",
    heading: "Anima Finetune",
    modelTrainType: "anima-finetune",
    schemaFile: "mikazuki/schema/anima-finetune.ts",
    backendEntrypoint: "scripts/dev/anima_train.py",
    summary: "Tracks full DiT finetune work without touching SD or Flux training pages.",
    nextWork: [
      "Source-own the high-risk Anima full finetune options first.",
      "Keep full finetune defaults aligned with backend adapter tests.",
      "Add save/load config compatibility checks before production replacement.",
    ],
  },
};

const animaDefaults: AnimaForm = {
  pretrained_model_name_or_path: "./sd-models/anima/anima-base-v1.0.safetensors",
  vae: "./sd-models/anima/qwen_image_vae.safetensors",
  qwen3: "./sd-models/anima/qwen_3_06b_base.safetensors",
  t5_tokenizer_path: "",
  train_data_dir: "",
  output_dir: "output",
  output_name: "anima",
  lora_type: "lora",
  max_train_epochs: 10,
  train_batch_size: 1,
  gradient_accumulation_steps: 1,
  learning_rate: "1e-5",
  unet_lr: "1e-4",
  network_dim: 32,
  network_alpha: 16,
  resolution: "1024,1024",
  mixed_precision: "bf16",
  optimizer_type: "AdamW8bit",
  attn_mode: "",
  timestep_sampling: "shift",
  discrete_flow_shift: 3,
  gradient_checkpointing: true,
  cache_latents: true,
  cache_latents_to_disk: true,
  cache_text_encoder_outputs: true,
  cache_text_encoder_outputs_to_disk: true,
  enable_preview: true,
  positive_prompts:
    "1girl, solo, smile, japanese clothes, kimono, blue eyes, closed mouth, upper body, looking at viewer",
  negative_prompts:
    "nsfw, explicit, sexual content, worst quality, low quality, artist name, jpeg artifacts",
  sample_width: 1024,
  sample_height: 1024,
  sample_cfg: 4.5,
  sample_seed: 42,
  sample_steps: 40,
  sample_every_n_epochs: 2,
  sample_prompts: "",
  caption_extension: ".txt",
  prefer_json_caption: true,
};

export function isAnimaRoute(path: string): boolean {
  return path in ANIMA_ROUTES;
}

export const AnimaRoutePage = defineComponent({
  name: "AnimaRoutePage",
  props: {
    route: {
      type: Object as () => AppRoute,
      required: true,
    },
  },
  setup(props) {
    const plan = ANIMA_ROUTES[props.route.path];
    const animaForm = reactive<AnimaForm>(loadStoredForm(plan));
    const status = ref("");

    function payload() {
      const base: Partial<AnimaForm> & { model_train_type: AnimaRoutePlan["modelTrainType"] } = {
        ...animaForm,
        model_train_type: plan.modelTrainType,
        pretrained_model_name_or_path: normalizePath(animaForm.pretrained_model_name_or_path),
        vae: normalizePath(animaForm.vae),
        qwen3: normalizePath(animaForm.qwen3),
        t5_tokenizer_path: normalizePath(animaForm.t5_tokenizer_path),
        train_data_dir: normalizePath(animaForm.train_data_dir),
        output_dir: normalizePath(animaForm.output_dir),
      };
      if (plan.modelTrainType === "anima-finetune") {
        delete base.lora_type;
        delete base.unet_lr;
        delete base.network_dim;
        delete base.network_alpha;
      }
      return base;
    }

    function saveForm() {
      const stored = readStoredForms();
      stored[plan.path] = { ...animaForm };
      localStorage.setItem(ANIMA_STORAGE_KEY, JSON.stringify(stored));
      status.value = "Saved locally";
    }

    function loadForm() {
      Object.assign(animaForm, loadStoredForm(plan));
      status.value = "Loaded local config";
    }

    async function runTraining() {
      status.value = "Submitting training config...";
      const response = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload()),
      });
      const result = await response.json();
      status.value = result.message || result.status || "Submitted";
    }

    function previewToml() {
      return Object.entries(payload())
        .filter(([, value]) => value !== "")
        .map(([key, value]) => `${key} = ${tomlValue(value)}`)
        .join("\n");
    }

    const textField = (key: TextKey, id: string, label: string, placeholder = "") =>
      h("label", { class: "anima-field" }, [
        h("span", label),
        h("input", {
          id,
          value: animaForm[key],
          placeholder,
          onInput: (event: Event) => {
            animaForm[key] = (event.target as HTMLInputElement).value;
          },
        }),
      ]);

    const numberField = (key: NumberKey, id: string, label: string, min = 0, step: string | number = 1) =>
      h("label", { class: "anima-field" }, [
        h("span", label),
        h("input", {
          id,
          type: "number",
          min,
          step,
          value: animaForm[key],
          onInput: (event: Event) => {
            animaForm[key] = Number((event.target as HTMLInputElement).value);
          },
        }),
      ]);

    const checkboxField = (key: BooleanKey, id: string, label: string) =>
      h("label", { class: "anima-toggle" }, [
        h("input", {
          id,
          type: "checkbox",
          checked: animaForm[key],
          onChange: (event: Event) => {
            animaForm[key] = (event.target as HTMLInputElement).checked;
          },
        }),
        h("span", label),
      ]);

    const textareaField = (key: "positive_prompts" | "negative_prompts" | "sample_prompts", id: string, label: string) =>
      h("label", { class: "anima-field" }, [
        h("span", label),
        h("textarea", {
          id,
          value: animaForm[key],
          rows: 4,
          onInput: (event: Event) => {
            animaForm[key] = (event.target as HTMLTextAreaElement).value;
          },
        }),
      ]);

    const selectField = <K extends "mixed_precision" | "attn_mode" | "timestep_sampling" | "lora_type">(
      key: K,
      id: string,
      label: string,
      options: AnimaForm[K][],
    ) =>
      h("label", { class: "anima-field" }, [
        h("span", label),
        h(
          "select",
          {
            id,
            value: animaForm[key],
            onChange: (event: Event) => {
              animaForm[key] = (event.target as HTMLSelectElement).value as AnimaForm[K];
            },
          },
          options.map((value) => h("option", { value }, value || "auto")),
        ),
      ]);

    const section = (title: string, children: ReturnType<typeof h>[]) =>
      h("fieldset", { class: "anima-section" }, [h("legend", title), ...children]);

    return () =>
      h("main", { class: "content anima-page" }, [
        h("header", { class: "anima-header" }, [
          h("div", [
            h("p", { class: "eyebrow" }, "Training"),
            h("h1", plan.heading),
            h("p", { class: "summary" }, plan.summary),
          ]),
          h("dl", { class: "anima-route-strip" }, [
            h("dt", "Route"),
            h("dd", plan.path),
            h("dt", "Schema"),
            h("dd", plan.schemaFile),
          ]),
        ]),
        h("section", { class: "anima-workbench" }, [
          h("div", { class: "anima-form-panel" }, [
            h("form", { id: "anima-train-form", class: "anima-form" }, [
              h("h2", "Training Config"),
              section("Model Assets", [
                textField(
                  "pretrained_model_name_or_path",
                  "anima-pretrained-model",
                  "pretrained_model_name_or_path",
                  "D:/models/anima-base-v1.0.safetensors",
                ),
                textField("vae", "anima-vae", "vae", "D:/models/qwen_image_vae.safetensors"),
                textField("qwen3", "anima-qwen3", "qwen3", "D:/models/qwen_3_06b_base.safetensors"),
                textField("t5_tokenizer_path", "anima-t5-tokenizer-path", "t5_tokenizer_path"),
              ]),
              section("Dataset And Output", [
                textField("train_data_dir", "anima-train-data-dir", "train_data_dir", "D:/datasets/anima"),
                textField("output_dir", "anima-output-dir", "output_dir"),
                textField("output_name", "anima-output-name", "output_name"),
                h("div", { class: "anima-field-row" }, [
                  textField("resolution", "anima-resolution", "resolution"),
                  textField("caption_extension", "anima-caption-extension", "caption_extension"),
                  checkboxField("prefer_json_caption", "anima-prefer-json-caption", "prefer_json_caption"),
                ]),
              ]),
              section("Training", [
                h("div", { class: "anima-field-row" }, [
                  numberField("max_train_epochs", "anima-epochs", "max_train_epochs", 1),
                  numberField("train_batch_size", "anima-train-batch-size", "train_batch_size", 1),
                  numberField(
                    "gradient_accumulation_steps",
                    "anima-gradient-accumulation-steps",
                    "gradient_accumulation_steps",
                    1,
                  ),
                ]),
                h("div", { class: "anima-field-row" }, [
                  textField("learning_rate", "anima-learning-rate", "learning_rate"),
                  textField("optimizer_type", "anima-optimizer", "optimizer_type"),
                  selectField("mixed_precision", "anima-mixed-precision", "mixed_precision", ["bf16", "fp16", "no"]),
                ]),
                checkboxField("gradient_checkpointing", "anima-gradient-checkpointing", "gradient_checkpointing"),
              ]),
              plan.modelTrainType === "anima-lora"
                ? section("LoRA Adapter", [
                    h("div", { class: "anima-field-row" }, [
                      selectField("lora_type", "anima-lora-type", "lora_type", [
                        "lora",
                        "lokr",
                        "tlora",
                        "lora_fa",
                        "vera",
                        "loha",
                      ]),
                      textField("unet_lr", "anima-unet-lr", "unet_lr"),
                      numberField("network_dim", "anima-network-dim", "network_dim", 1),
                    ]),
                    numberField("network_alpha", "anima-network-alpha", "network_alpha", 1),
                  ])
                : null,
              section("Anima Parameters", [
                h("div", { class: "anima-field-row" }, [
                  selectField("attn_mode", "anima-attn-mode", "attn_mode", [
                    "",
                    "torch",
                    "xformers",
                    "sageattn",
                    "flash",
                  ]),
                  selectField("timestep_sampling", "anima-timestep-sampling", "timestep_sampling", [
                    "sigma",
                    "uniform",
                    "sigmoid",
                    "shift",
                    "flux_shift",
                  ]),
                  numberField("discrete_flow_shift", "anima-discrete-flow-shift", "discrete_flow_shift", 0, 0.001),
                ]),
              ]),
              section("Cache", [
                h("div", { class: "anima-toggle-grid" }, [
                  checkboxField("cache_latents", "anima-cache-latents", "cache_latents"),
                  checkboxField("cache_latents_to_disk", "anima-cache-latents-to-disk", "cache_latents_to_disk"),
                  checkboxField(
                    "cache_text_encoder_outputs",
                    "anima-cache-text-encoder-outputs",
                    "cache_text_encoder_outputs",
                  ),
                  checkboxField(
                    "cache_text_encoder_outputs_to_disk",
                    "anima-cache-text-encoder-outputs-to-disk",
                    "cache_text_encoder_outputs_to_disk",
                  ),
                ]),
              ]),
              section("Preview", [
                checkboxField("enable_preview", "anima-enable-preview", "enable_preview"),
                textareaField("positive_prompts", "anima-positive-prompts", "positive_prompts"),
                textareaField("negative_prompts", "anima-negative-prompts", "negative_prompts"),
                textareaField("sample_prompts", "anima-sample-prompts", "sample_prompts"),
                h("div", { class: "anima-field-row" }, [
                  numberField("sample_width", "anima-sample-width", "sample_width", 64),
                  numberField("sample_height", "anima-sample-height", "sample_height", 64),
                  numberField("sample_every_n_epochs", "anima-sample-every-n-epochs", "sample_every_n_epochs", 1),
                ]),
                h("div", { class: "anima-field-row" }, [
                  numberField("sample_cfg", "anima-sample-cfg", "sample_cfg", 1, 0.1),
                  numberField("sample_seed", "anima-sample-seed", "sample_seed", 0),
                  numberField("sample_steps", "anima-sample-steps", "sample_steps", 1),
                ]),
              ]),
            ]),
          ]),
          h("aside", { class: "anima-preview-panel" }, [
            h("div", { class: "anima-preview-card" }, [
              h("h2", "Parameter Preview"),
              h("pre", { id: "anima-preview-code", class: "anima-preview-code" }, previewToml()),
            ]),
            h("div", { class: "anima-preview-card" }, [
              h("h2", "Run Controls"),
              h("div", { class: "anima-actions" }, [
                h("button", { type: "button", onClick: saveForm }, "Save Config"),
                h("button", { type: "button", onClick: loadForm }, "Load Config"),
                h("button", { type: "button", class: "primary", onClick: runTraining }, "Start Training"),
              ]),
              status.value ? h("p", { class: "anima-status" }, status.value) : null,
            ]),
            h("details", { class: "anima-preview-card" }, [
              h("summary", "Migration Notes"),
              h(
                "ul",
                plan.nextWork.map((item) => h("li", item)),
              ),
              h("dl", { class: "anima-contract" }, [
                h("dt", "model_train_type"),
                h("dd", plan.modelTrainType),
                h("dt", "Backend entrypoint"),
                h("dd", plan.backendEntrypoint),
              ]),
            ]),
          ]),
        ]),
      ]);
  },
});

function tomlValue(value: unknown): string {
  if (typeof value === "boolean") {
    return value ? "true" : "false";
  }
  if (typeof value === "number") {
    return String(value);
  }
  return `"${String(value).replaceAll("\\", "\\\\").replaceAll('"', '\\"').replaceAll("\n", "\\n")}"`;
}

function normalizePath(value: string): string {
  return value.replaceAll("\\", "/");
}

function readStoredForms(): Record<string, Partial<AnimaForm>> {
  try {
    return JSON.parse(localStorage.getItem(ANIMA_STORAGE_KEY) || "{}");
  } catch {
    return {};
  }
}

function loadStoredForm(plan: AnimaRoutePlan): AnimaForm {
  const stored = readStoredForms()[plan.path] || {};
  return {
    ...animaDefaults,
    output_name: plan.modelTrainType === "anima-finetune" ? "anima-finetune" : "anima-lora",
    ...stored,
  };
}
