import { defineComponent, h, reactive, ref, type VNodeChild } from "vue";
import type { AppRoute } from "./routes";
import {
  previewToml,
  renderParameterPreview,
  renderRunControls,
  renderTrainingField,
  renderTrainingFieldRow,
  renderTrainingSection,
  renderTrainingWorkbench,
  type TrainingFormState,
} from "./trainingRenderer";

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
  llm_adapter_path: string;
  resume: string;
  train_data_dir: string;
  output_dir: string;
  output_name: string;
  lora_type: "lora" | "lokr" | "tlora" | "lora_fa" | "vera" | "loha";
  max_train_epochs: number;
  train_batch_size: number;
  gradient_accumulation_steps: number;
  qwen3_max_token_length: number;
  t5_max_token_length: number;
  learning_rate: string;
  unet_lr: string;
  lr_scheduler: "linear" | "cosine" | "cosine_with_restarts" | "polynomial" | "constant" | "constant_with_warmup";
  lr_warmup_steps: number;
  network_dim: number;
  network_alpha: number;
  resolution: string;
  enable_bucket: boolean;
  min_bucket_reso: number;
  max_bucket_reso: number;
  bucket_reso_steps: number;
  mixed_precision: "bf16" | "fp16" | "no";
  optimizer_type: string;
  attn_mode: "" | "torch" | "xformers" | "sageattn" | "flash";
  timestep_sampling: "sigma" | "uniform" | "sigmoid" | "shift" | "flux_shift";
  sigmoid_scale: number;
  discrete_flow_shift: number;
  weighting_scheme: "sigma_sqrt" | "logit_normal" | "mode" | "cosmap" | "none" | "uniform";
  gradient_checkpointing: boolean;
  network_train_unet_only: boolean;
  network_train_text_encoder_only: boolean;
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
  | "llm_adapter_path"
  | "resume"
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
  | "qwen3_max_token_length"
  | "t5_max_token_length"
  | "lr_warmup_steps"
  | "network_dim"
  | "network_alpha"
  | "min_bucket_reso"
  | "max_bucket_reso"
  | "bucket_reso_steps"
  | "sigmoid_scale"
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
  | "enable_bucket"
  | "network_train_unet_only"
  | "network_train_text_encoder_only"
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
  llm_adapter_path: "",
  resume: "",
  train_data_dir: "",
  output_dir: "output",
  output_name: "anima",
  lora_type: "lora",
  max_train_epochs: 10,
  train_batch_size: 1,
  gradient_accumulation_steps: 1,
  qwen3_max_token_length: 512,
  t5_max_token_length: 512,
  learning_rate: "1e-5",
  unet_lr: "1e-4",
  lr_scheduler: "cosine_with_restarts",
  lr_warmup_steps: 0,
  network_dim: 32,
  network_alpha: 16,
  resolution: "1024,1024",
  enable_bucket: true,
  min_bucket_reso: 256,
  max_bucket_reso: 2048,
  bucket_reso_steps: 64,
  mixed_precision: "bf16",
  optimizer_type: "AdamW8bit",
  attn_mode: "",
  timestep_sampling: "shift",
  sigmoid_scale: 1,
  discrete_flow_shift: 3,
  weighting_scheme: "uniform",
  gradient_checkpointing: true,
  network_train_unet_only: true,
  network_train_text_encoder_only: false,
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
        llm_adapter_path: normalizePath(animaForm.llm_adapter_path),
        resume: normalizePath(animaForm.resume),
        train_data_dir: normalizePath(animaForm.train_data_dir),
        output_dir: normalizePath(animaForm.output_dir),
      };
      if (plan.modelTrainType === "anima-finetune") {
        delete base.lora_type;
        delete base.unet_lr;
        delete base.network_dim;
        delete base.network_alpha;
        delete base.network_train_unet_only;
        delete base.network_train_text_encoder_only;
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

    const formState = animaForm as unknown as TrainingFormState;

    const textField = (key: TextKey, id: string, label: string, placeholder = "", description = "") =>
      renderTrainingField(formState, {
        kind: "text",
        key,
        id,
        label,
        placeholder,
        description,
      });

    const numberField = (
      key: NumberKey,
      id: string,
      label: string,
      min = 0,
      step: string | number = 1,
      description = "",
    ) =>
      renderTrainingField(formState, {
        kind: "number",
        key,
        id,
        label,
        min,
        step,
        description,
      });

    const checkboxField = (key: BooleanKey, id: string, label: string, description = "") =>
      renderTrainingField(formState, {
        kind: "checkbox",
        key,
        id,
        label,
        description,
      });

    const textareaField = (
      key: "positive_prompts" | "negative_prompts" | "sample_prompts",
      id: string,
      label: string,
      description = "",
    ) =>
      renderTrainingField(formState, {
        kind: "textarea",
        key,
        id,
        label,
        rows: 4,
        description,
      });

    const selectField = <
      K extends "mixed_precision" | "attn_mode" | "timestep_sampling" | "lora_type" | "weighting_scheme" | "lr_scheduler",
    >(
      key: K,
      id: string,
      label: string,
      options: AnimaForm[K][],
    ) =>
      renderTrainingField(formState, {
        kind: "select",
        key,
        id,
        label,
        options,
      });

    const section = (title: string, children: VNodeChild[]) => renderTrainingSection(title, children);

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
        renderTrainingWorkbench(
          [
            h("form", { id: "anima-train-form", class: "anima-form" }, [
              h("h2", "Training Config"),
              section("Model Assets", [
                textField(
                  "pretrained_model_name_or_path",
                  "anima-pretrained-model",
                  "pretrained_model_name_or_path",
                  "D:/models/anima-base-v1.0.safetensors",
                  "Anima DiT / transformer checkpoint path.",
                ),
                textField("vae", "anima-vae", "vae", "D:/models/qwen_image_vae.safetensors", "Qwen Image VAE path."),
                textField("qwen3", "anima-qwen3", "qwen3", "D:/models/qwen_3_06b_base.safetensors", "Qwen3 text model path."),
                textField(
                  "t5_tokenizer_path",
                  "anima-t5-tokenizer-path",
                  "t5_tokenizer_path",
                  "",
                  "Optional T5 tokenizer folder. Empty uses the bundled config.",
                ),
                textField("llm_adapter_path", "anima-llm-adapter-path", "llm_adapter_path"),
                textField("resume", "anima-resume", "resume"),
              ]),
              section("Dataset And Output", [
                textField("train_data_dir", "anima-train-data-dir", "train_data_dir", "D:/datasets/anima"),
                textField("output_dir", "anima-output-dir", "output_dir"),
                textField("output_name", "anima-output-name", "output_name"),
                renderTrainingFieldRow([
                  textField("resolution", "anima-resolution", "resolution"),
                  textField("caption_extension", "anima-caption-extension", "caption_extension"),
                  checkboxField("prefer_json_caption", "anima-prefer-json-caption", "prefer_json_caption"),
                ]),
                renderTrainingFieldRow([
                  checkboxField("enable_bucket", "anima-enable-bucket", "enable_bucket"),
                  numberField("min_bucket_reso", "anima-min-bucket-reso", "min_bucket_reso", 64),
                  numberField("max_bucket_reso", "anima-max-bucket-reso", "max_bucket_reso", 64),
                ]),
                numberField("bucket_reso_steps", "anima-bucket-reso-steps", "bucket_reso_steps", 1),
              ]),
              section("Training", [
                renderTrainingFieldRow([
                  numberField("max_train_epochs", "anima-epochs", "max_train_epochs", 1),
                  numberField("train_batch_size", "anima-train-batch-size", "train_batch_size", 1),
                  numberField(
                    "gradient_accumulation_steps",
                    "anima-gradient-accumulation-steps",
                    "gradient_accumulation_steps",
                    1,
                  ),
                ]),
                renderTrainingFieldRow([
                  textField("learning_rate", "anima-learning-rate", "learning_rate"),
                  textField("optimizer_type", "anima-optimizer", "optimizer_type"),
                  selectField("mixed_precision", "anima-mixed-precision", "mixed_precision", ["bf16", "fp16", "no"]),
                ]),
                renderTrainingFieldRow([
                  selectField("lr_scheduler", "anima-lr-scheduler", "lr_scheduler", [
                    "linear",
                    "cosine",
                    "cosine_with_restarts",
                    "polynomial",
                    "constant",
                    "constant_with_warmup",
                  ]),
                  numberField("lr_warmup_steps", "anima-lr-warmup-steps", "lr_warmup_steps", 0),
                  numberField("qwen3_max_token_length", "anima-qwen3-max-token-length", "qwen3_max_token_length", 1),
                ]),
                numberField("t5_max_token_length", "anima-t5-max-token-length", "t5_max_token_length", 1),
                checkboxField("gradient_checkpointing", "anima-gradient-checkpointing", "gradient_checkpointing"),
              ]),
              plan.modelTrainType === "anima-lora"
                ? section("LoRA Adapter", [
                    renderTrainingFieldRow([
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
                    renderTrainingFieldRow([
                      checkboxField("network_train_unet_only", "anima-network-train-unet-only", "network_train_unet_only"),
                      checkboxField(
                        "network_train_text_encoder_only",
                        "anima-network-train-text-encoder-only",
                        "network_train_text_encoder_only",
                      ),
                    ]),
                  ])
                : null,
              section("Anima Parameters", [
                renderTrainingFieldRow([
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
                  numberField("sigmoid_scale", "anima-sigmoid-scale", "sigmoid_scale", 0, 0.001),
                ]),
                renderTrainingFieldRow([
                  numberField("discrete_flow_shift", "anima-discrete-flow-shift", "discrete_flow_shift", 0, 0.001),
                  selectField("weighting_scheme", "anima-weighting-scheme", "weighting_scheme", [
                    "sigma_sqrt",
                    "logit_normal",
                    "mode",
                    "cosmap",
                    "none",
                    "uniform",
                  ]),
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
                renderTrainingFieldRow([
                  numberField("sample_width", "anima-sample-width", "sample_width", 64),
                  numberField("sample_height", "anima-sample-height", "sample_height", 64),
                  numberField("sample_every_n_epochs", "anima-sample-every-n-epochs", "sample_every_n_epochs", 1),
                ]),
                renderTrainingFieldRow([
                  numberField("sample_cfg", "anima-sample-cfg", "sample_cfg", 1, 0.1),
                  numberField("sample_seed", "anima-sample-seed", "sample_seed", 0),
                  numberField("sample_steps", "anima-sample-steps", "sample_steps", 1),
                ]),
              ]),
            ]),
          ],
          [
            renderParameterPreview(previewToml(payload()), "anima-preview-code"),
            renderRunControls(
              [
                { label: "Save Config", onClick: saveForm },
                { label: "Load Config", onClick: loadForm },
                { label: "Start Training", onClick: runTraining, primary: true },
              ],
              status.value,
            ),
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
          ],
        ),
      ]);
  },
});

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
