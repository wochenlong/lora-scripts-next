import { defineComponent, h, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import type { AppRoute } from "./routes";
import {
  installTrainingPathBrowseBridge,
  previewToml,
  renderParameterPreview,
  renderRunControls,
  renderTrainingSchemaSections,
  renderTrainingWorkbench,
} from "./trainingRenderer";

import {
  ANIMA_ROUTES,
  ANIMA_STORAGE_KEY,
  animaDefaults,
  animaSectionsForPlan,
  type AnimaRoutePlan,
  type AnimaForm,
} from "./animaSchema";
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
    const importConfigInput = ref<HTMLInputElement | null>(null);
    const status = ref("");
    let removePathBrowseBridge: (() => void) | undefined;

    onMounted(() => {
      removePathBrowseBridge = installTrainingPathBrowseBridge((detail) => {
        status.value = `Browse requested for ${detail.key} (${detail.role})`;
      });
    });

    onBeforeUnmount(() => {
      removePathBrowseBridge?.();
    });

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
        delete base.network_args_custom;
        delete base.network_weights;
        delete base.dim_from_weights;
        delete base.scale_weight_norms;
        delete base.train_norm;
        delete base.network_dropout;
        delete base.pissa_init;
        delete base.pissa_method;
        delete base.pissa_niter;
        delete base.pissa_oversample;
        delete base.lokr_factor;
        delete base.full_matrix;
        delete base.tlora_min_rank;
        delete base.tlora_rank_schedule;
        delete base.tlora_orthogonal_init;
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

    function resetForm() {
      const stored = readStoredForms();
      delete stored[plan.path];
      localStorage.setItem(ANIMA_STORAGE_KEY, JSON.stringify(stored));
      Object.assign(animaForm, defaultFormForPlan(plan));
      status.value = "Reset to defaults";
    }

    function exportConfig() {
      const blob = new Blob([JSON.stringify(payload(), null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${animaForm.output_name || plan.modelTrainType}.json`;
      link.click();
      URL.revokeObjectURL(url);
      status.value = "Exported config";
    }

    async function importConfigFile(event: Event) {
      const input = event.target as HTMLInputElement;
      const file = input.files?.[0];
      if (!file) {
        return;
      }
      try {
        const imported = JSON.parse(await file.text()) as Partial<AnimaForm> & { model_train_type?: string };
        delete imported.model_train_type;
        Object.assign(animaForm, defaultFormForPlan(plan), imported);
        status.value = "Imported config";
      } catch (error) {
        status.value = error instanceof Error ? error.message : "Import failed";
      } finally {
        input.value = "";
      }
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
              renderTrainingSchemaSections(animaForm, animaSectionsForPlan(plan)),
            ]),
          ],
          [
            renderParameterPreview(previewToml(payload()), "anima-preview-code"),
            renderRunControls(
              [
                { label: "Save Config", onClick: saveForm },
                { label: "Load Config", onClick: loadForm },
                { label: "Reset Config", onClick: resetForm },
                { label: "Export Config", onClick: exportConfig },
                { label: "Import Config", onClick: () => importConfigInput.value?.click() },
                { label: "Start Training", onClick: runTraining, primary: true },
              ],
              status.value,
            ),
            h("input", {
              ref: importConfigInput,
              id: "anima-import-config",
              type: "file",
              accept: "application/json,.json",
              style: "display:none",
              onChange: importConfigFile,
            }),
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
    ...defaultFormForPlan(plan),
    ...stored,
  };
}

function defaultFormForPlan(plan: AnimaRoutePlan): AnimaForm {
  return {
    ...animaDefaults,
    output_name: plan.modelTrainType === "anima-finetune" ? "anima-finetune" : "anima-lora",
  };
}


