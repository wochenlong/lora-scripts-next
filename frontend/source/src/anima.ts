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
  train_data_dir: string;
  output_dir: string;
  output_name: string;
  max_train_epochs: number;
  learning_rate: string;
  unet_lr: string;
  network_dim: number;
  network_alpha: number;
  resolution: string;
  mixed_precision: "bf16" | "fp16" | "no";
  optimizer_type: string;
  enable_preview: boolean;
  sample_prompts: string;
}

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
  pretrained_model_name_or_path: "",
  train_data_dir: "",
  output_dir: "output",
  output_name: "anima",
  max_train_epochs: 10,
  learning_rate: "1e-5",
  unet_lr: "1e-4",
  network_dim: 32,
  network_alpha: 16,
  resolution: "1024,1024",
  mixed_precision: "bf16",
  optimizer_type: "adamw8bit",
  enable_preview: true,
  sample_prompts: "",
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
      const base = {
        ...animaForm,
        model_train_type: plan.modelTrainType,
        train_data_dir: animaForm.train_data_dir.replaceAll("\\", "/"),
        pretrained_model_name_or_path: animaForm.pretrained_model_name_or_path.replaceAll("\\", "/"),
        output_dir: animaForm.output_dir.replaceAll("\\", "/"),
      };
      if (plan.modelTrainType === "anima-finetune") {
        delete (base as Partial<AnimaForm>).unet_lr;
        delete (base as Partial<AnimaForm>).network_dim;
        delete (base as Partial<AnimaForm>).network_alpha;
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

    const textField = (key: keyof Pick<AnimaForm, "pretrained_model_name_or_path" | "train_data_dir" | "output_dir" | "output_name" | "learning_rate" | "unet_lr" | "resolution" | "optimizer_type">, id: string, label: string, placeholder = "") =>
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

    const numberField = (key: keyof Pick<AnimaForm, "max_train_epochs" | "network_dim" | "network_alpha">, id: string, label: string) =>
      h("label", { class: "anima-field" }, [
        h("span", label),
        h("input", {
          id,
          type: "number",
          min: 1,
          value: animaForm[key],
          onInput: (event: Event) => {
            animaForm[key] = Number((event.target as HTMLInputElement).value);
          },
        }),
      ]);

    return () =>
      h("main", { class: "content anima-page" }, [
        h("p", { class: "eyebrow" }, "Anima source route"),
        h("h1", plan.heading),
        h("p", { class: "summary" }, plan.summary),
        h("section", { class: "anima-grid" }, [
          h("article", { class: "compat-panel" }, [
            h("h2", "Stable Contract"),
            h("dl", { class: "anima-contract" }, [
              h("dt", "Route"),
              h("dd", plan.path),
              h("dt", "model_train_type"),
              h("dd", plan.modelTrainType),
              h("dt", "Schema"),
              h("dd", plan.schemaFile),
              h("dt", "Backend entrypoint"),
              h("dd", plan.backendEntrypoint),
            ]),
          ]),
          h("article", { class: "compat-panel" }, [
            h("h2", "Migration Notes"),
            h(
              "ul",
              plan.nextWork.map((item) => h("li", item)),
            ),
          ]),
        ]),
        h("form", { id: "anima-train-form", class: "anima-form" }, [
          h("h2", "Training Config"),
          textField(
            "pretrained_model_name_or_path",
            "anima-pretrained-model",
            "pretrained_model_name_or_path",
            "D:/models/anima.safetensors",
          ),
          textField("train_data_dir", "anima-train-data-dir", "train_data_dir", "D:/datasets/anima"),
          textField("output_dir", "anima-output-dir", "output_dir"),
          textField("output_name", "anima-output-name", "output_name"),
          numberField("max_train_epochs", "anima-epochs", "max_train_epochs"),
          textField("learning_rate", "anima-learning-rate", "learning_rate"),
          plan.modelTrainType === "anima-lora"
            ? h("div", { class: "anima-field-row" }, [
                textField("unet_lr", "anima-unet-lr", "unet_lr"),
                numberField("network_dim", "anima-network-dim", "network_dim"),
                numberField("network_alpha", "anima-network-alpha", "network_alpha"),
              ])
            : null,
          textField("resolution", "anima-resolution", "resolution"),
          textField("optimizer_type", "anima-optimizer", "optimizer_type"),
          h("label", { class: "anima-field" }, [
            h("span", "mixed_precision"),
            h(
              "select",
              {
                id: "anima-mixed-precision",
                value: animaForm.mixed_precision,
                onChange: (event: Event) => {
                  animaForm.mixed_precision = (event.target as HTMLSelectElement).value as AnimaForm["mixed_precision"];
                },
              },
              ["bf16", "fp16", "no"].map((value) => h("option", { value }, value)),
            ),
          ]),
          h("label", { class: "anima-toggle" }, [
            h("input", {
              id: "anima-enable-preview",
              type: "checkbox",
              checked: animaForm.enable_preview,
              onChange: (event: Event) => {
                animaForm.enable_preview = (event.target as HTMLInputElement).checked;
              },
            }),
            h("span", "enable_preview"),
          ]),
          h("label", { class: "anima-field" }, [
            h("span", "sample_prompts"),
            h("textarea", {
              id: "anima-sample-prompts",
              value: animaForm.sample_prompts,
              rows: 4,
              onInput: (event: Event) => {
                animaForm.sample_prompts = (event.target as HTMLTextAreaElement).value;
              },
            }),
          ]),
          h("div", { class: "anima-actions" }, [
            h("button", { type: "button", onClick: saveForm }, "Save"),
            h("button", { type: "button", onClick: loadForm }, "Load"),
            h("button", { type: "button", class: "primary", onClick: runTraining }, "Start Training"),
            status.value ? h("span", { class: "anima-status" }, status.value) : null,
          ]),
        ]),
      ]);
  },
});

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
