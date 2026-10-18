import type { FormModel } from "../schema/adapter"

export type TrainingModel = "anima" | "sd15" | "sdxl" | "flux" | "lumina" | "krea2" | "ideogram4" | "klein" | "qwen-image-21" | "moss-image"
export type TrainingEngine = "kohya" | "anima-fast" | "musubi" | "ai-toolkit" | "diffsynth" | "moss"
export type TrainingTarget = "lora" | "finetune"
/** Beginner-facing use-case chips that map to a recommended base model. */
export type TrainingScenario = "anime" | "general" | "edit" | "explore"

export interface TrainingModule {
  model: TrainingModel
  engine: TrainingEngine
  target: TrainingTarget
  schemaName: string
  /** Field overrides applied on top of schema defaults, e.g. model_train_type. */
  defaults?: FormModel
  /** localStorage identity for drafts/history; defaults to schemaName when omitted. */
  storageKey?: string
  /** Legacy schemaName whose drafts/history this module inherits on first load. */
  legacyStorageKey?: string
}

export const TRAINING_MODELS: readonly TrainingModel[] = ["anima", "sd15", "sdxl", "flux", "lumina", "krea2", "ideogram4", "klein", "qwen-image-21", "moss-image"]
export const TRAINING_ENGINES: readonly TrainingEngine[] = ["kohya", "anima-fast", "musubi", "ai-toolkit", "diffsynth", "moss"]
export const TRAINING_TARGETS: readonly TrainingTarget[] = ["lora", "finetune"]

/** Scenario → model. Order is the beginner decision path on the training page. */
export const TRAINING_SCENARIOS: readonly { id: TrainingScenario; model: TrainingModel }[] = [
  { id: "anime", model: "anima" },
  { id: "general", model: "krea2" },
  { id: "edit", model: "klein" },
  { id: "explore", model: "qwen-image-21" },
]

/** Model dropdown order: scenario recommendations first, then other families.
 * Lumina is omitted — almost unused; deep links via ?model=lumina still work. */
export const MODEL_PICKER_ORDER: readonly TrainingModel[] = [
  "anima",
  "krea2",
  "klein",
  "qwen-image-21",
  "moss-image",
  "ideogram4",
  "flux",
  "sdxl",
  "sd15",
]

export const DEFAULT_SELECTION: { model: TrainingModel; engine: TrainingEngine; target: TrainingTarget } = {
  model: "anima",
  engine: "kohya",
  target: "lora",
}

export function scenarioForModel(model: TrainingModel): TrainingScenario | undefined {
  return TRAINING_SCENARIOS.find((item) => item.model === model)?.id
}

export function modelForScenario(scenario: TrainingScenario): TrainingModel {
  const match = TRAINING_SCENARIOS.find((item) => item.id === scenario)
  if (!match) throw new Error(`unknown training scenario: ${scenario}`)
  return match.model
}

// NOTE: sdxl entries intentionally precede sd15 ones so moduleForSchema()
// resolves shared schemas (lora-master, dreambooth) to the sdxl module,
// matching the previous single-SD default (schema default was sdxl-lora).
export const TRAINING_MODULES: readonly TrainingModule[] = [
  { model: "moss-image", engine: "kohya", target: "lora", schemaName: "moss-image-lora" },
  { model: "moss-image", engine: "moss", target: "lora", schemaName: "moss-image-anima-lora" },
  { model: "qwen-image-21", engine: "diffsynth", target: "lora", schemaName: "qwen-image-21-lora" },
  { model: "anima", engine: "kohya", target: "lora", schemaName: "sd3-lora" },
  { model: "anima", engine: "anima-fast", target: "lora", schemaName: "anima-lora-fast" },
  { model: "anima", engine: "kohya", target: "finetune", schemaName: "anima-finetune" },
  { model: "sdxl", engine: "kohya", target: "lora", schemaName: "lora-master", defaults: { model_train_type: "sdxl-lora" }, storageKey: "sdxl-lora", legacyStorageKey: "lora-master" },
  { model: "sd15", engine: "kohya", target: "lora", schemaName: "lora-master", defaults: { model_train_type: "sd-lora" }, storageKey: "sd15-lora" },
  { model: "sdxl", engine: "kohya", target: "finetune", schemaName: "dreambooth", defaults: { model_train_type: "sdxl-finetune" }, storageKey: "sdxl-dreambooth", legacyStorageKey: "dreambooth" },
  { model: "sd15", engine: "kohya", target: "finetune", schemaName: "dreambooth", defaults: { model_train_type: "sd-dreambooth" }, storageKey: "sd15-dreambooth" },
  { model: "flux", engine: "kohya", target: "lora", schemaName: "flux-lora" },
  { model: "lumina", engine: "kohya", target: "lora", schemaName: "lumina2-lora" },
  { model: "krea2", engine: "musubi", target: "lora", schemaName: "krea2-lora" },
  { model: "ideogram4", engine: "musubi", target: "lora", schemaName: "ideogram4-lora" },
  { model: "klein", engine: "ai-toolkit", target: "lora", schemaName: "klein-lora" },
  { model: "sdxl", engine: "ai-toolkit", target: "lora", schemaName: "ai-toolkit-sdxl-lora" },
  { model: "sd15", engine: "ai-toolkit", target: "lora", schemaName: "ai-toolkit-sd15-lora" },
  { model: "ideogram4", engine: "ai-toolkit", target: "lora", schemaName: "ai-toolkit-ideogram4-lora" },
  { model: "flux", engine: "ai-toolkit", target: "lora", schemaName: "ai-toolkit-flux-lora" },
  { model: "anima", engine: "ai-toolkit", target: "lora", schemaName: "ai-toolkit-anima-lora" },
  { model: "krea2", engine: "ai-toolkit", target: "lora", schemaName: "ai-toolkit-krea2-lora" },
  { model: "qwen-image-21", engine: "ai-toolkit", target: "lora", schemaName: "ai-toolkit-qwen-image-21-lora" },

]

export const SCHEMA_META: Record<string, { titleKey: string; areaKey: string }> = {
  "moss-image-lora": { titleKey: "training.schemas.moss-image-lora.title", areaKey: "training.schemas.moss-image-lora.area" },
  "moss-image-anima-lora": { titleKey: "training.schemas.moss-image-anima-lora.title", areaKey: "training.schemas.moss-image-anima-lora.area" },
  "ai-toolkit-sdxl-lora": { titleKey: "training.schemas.ai-toolkit-sdxl-lora.title", areaKey: "training.schemas.ai-toolkit-sdxl-lora.area" },
  "ai-toolkit-sd15-lora": { titleKey: "training.schemas.ai-toolkit-sd15-lora.title", areaKey: "training.schemas.ai-toolkit-sd15-lora.area" },
  "ai-toolkit-ideogram4-lora": { titleKey: "training.schemas.ai-toolkit-ideogram4-lora.title", areaKey: "training.schemas.ai-toolkit-ideogram4-lora.area" },
  "ai-toolkit-flux-lora": { titleKey: "training.schemas.ai-toolkit-flux-lora.title", areaKey: "training.schemas.ai-toolkit-flux-lora.area" },
  "ai-toolkit-anima-lora": { titleKey: "training.schemas.ai-toolkit-anima-lora.title", areaKey: "training.schemas.ai-toolkit-anima-lora.area" },
  "ai-toolkit-krea2-lora": { titleKey: "training.schemas.ai-toolkit-krea2-lora.title", areaKey: "training.schemas.ai-toolkit-krea2-lora.area" },
  "ai-toolkit-qwen-image-21-lora": { titleKey: "training.schemas.ai-toolkit-qwen-image-21-lora.title", areaKey: "training.schemas.ai-toolkit-qwen-image-21-lora.area" },

  "qwen-image-21-lora": { titleKey: "training.schemas.qwen-image-21-lora.title", areaKey: "training.schemas.qwen-image-21-lora.area" },
  "sd3-lora": { titleKey: "training.schemas.sd3-lora.title", areaKey: "training.schemas.sd3-lora.area" },
  "anima-lora-fast": { titleKey: "training.schemas.anima-lora-fast.title", areaKey: "training.schemas.anima-lora-fast.area" },
  "anima-finetune": { titleKey: "training.schemas.anima-finetune.title", areaKey: "training.schemas.anima-finetune.area" },
  "lora-master": { titleKey: "training.schemas.lora-master.title", areaKey: "training.schemas.lora-master.area" },
  dreambooth: { titleKey: "training.schemas.dreambooth.title", areaKey: "training.schemas.dreambooth.area" },
  "flux-lora": { titleKey: "training.schemas.flux-lora.title", areaKey: "training.schemas.flux-lora.area" },
  "lumina2-lora": { titleKey: "training.schemas.lumina2-lora.title", areaKey: "training.schemas.lumina2-lora.area" },
  "krea2-lora": { titleKey: "training.schemas.krea2-lora.title", areaKey: "training.schemas.krea2-lora.area" },
  "ideogram4-lora": { titleKey: "training.schemas.ideogram4-lora.title", areaKey: "training.schemas.ideogram4-lora.area" },
  "klein-lora": { titleKey: "training.schemas.klein-lora.title", areaKey: "training.schemas.klein-lora.area" },
}

export function normalizeModel(value: unknown): TrainingModel | undefined {
  // Legacy "sd" covered both SD 1.5 and SDXL; map it to sdxl, the old default.
  if (value === "sd") return "sdxl"
  // Accept the versioned spelling used by older links and saved browser tabs.
  if (value === "qwen-image-2.1") return "qwen-image-21"
  return TRAINING_MODELS.includes(value as TrainingModel) ? (value as TrainingModel) : undefined
}

export function resolveModule(model: TrainingModel, engine: TrainingEngine, target: TrainingTarget): TrainingModule | undefined {
  return TRAINING_MODULES.find((module) => module.model === model && module.engine === engine && module.target === target)
}

export function moduleForSchema(schemaName: string): TrainingModule | undefined {
  return TRAINING_MODULES.find((module) => module.schemaName === schemaName)
}

/**
 * Resolve a module from a config's model_train_type. Unambiguous for modules
 * carrying defaults (sd15/sdxl lora and finetune); falls back to schemaName
 * for train types that are schema names themselves (e.g. sd3-lora).
 */
export function moduleForTrainType(trainType: unknown): TrainingModule | undefined {
  if (typeof trainType !== "string" || !trainType) return undefined
  if (["klein-4b-lora", "klein-9b-lora"].includes(trainType)) return moduleForSchema("klein-lora")
  return TRAINING_MODULES.find((module) => module.defaults?.model_train_type === trainType)
    ?? TRAINING_MODULES.find((module) => module.schemaName === trainType)
}

export function isEngineSupported(model: TrainingModel, engine: TrainingEngine): boolean {
  return TRAINING_MODULES.some((module) => module.model === model && module.engine === engine)
}

export function isTargetSupported(model: TrainingModel, engine: TrainingEngine, target: TrainingTarget): boolean {
  return Boolean(resolveModule(model, engine, target))
}

/**
 * Preferred engines per model, best-first. Auto-select walks this list and
 * skips engines that are not installed yet (see recommendedEngineFor).
 *
 * Anima: Fast first, Kohya fallback so users without Fast never land on an
 * install gate by default.
 */
export const ENGINE_PREFERENCE: Readonly<Record<TrainingModel, readonly TrainingEngine[]>> = {
  anima: ["anima-fast", "kohya"],
  sd15: ["kohya", "ai-toolkit"],
  sdxl: ["kohya", "ai-toolkit"],
  flux: ["kohya", "ai-toolkit"],
  lumina: ["kohya"],
  krea2: ["musubi", "ai-toolkit"],
  ideogram4: ["musubi", "ai-toolkit"],
  klein: ["ai-toolkit"],
  "qwen-image-21": ["diffsynth", "ai-toolkit"],
  "moss-image": ["kohya", "moss"],
}

/** Ideal (first-choice) engine for a model, ignoring install state. */
export function idealEngineFor(model: TrainingModel): TrainingEngine | undefined {
  return enginePreferenceOrder(model)[0]
}

export function enginePreferenceOrder(model: TrainingModel): TrainingEngine[] {
  const preferred = ENGINE_PREFERENCE[model] ?? []
  const supported = preferred.filter((engine) => isEngineSupported(model, engine))
  if (supported.length) return supported
  const fromModules = TRAINING_MODULES.filter((module) => module.model === model)
  const fallback = (fromModules.find((module) => module.target === "lora") ?? fromModules[0])?.engine
  return fallback ? [fallback] : []
}

/** Runtime states safe to auto-enter without forcing an install flow. */
export function isEngineReadyForAutoSelect(state: string | undefined): boolean {
  return state === "ready" || state === "installed_unverified"
}

/**
 * Product-recommended engine for a model.
 *
 * - With availability: first preferred engine that is ready; if none are ready,
 *   fall back through the preference list (Anima → Kohya when Fast is missing).
 * - Without availability (cold start / status unknown): use a safe entry —
 *   Anima uses Kohya so users do not open an uninstalled Fast gate; others use
 *   the ideal first preference.
 */
export function recommendedEngineFor(
  model: TrainingModel,
  isAvailable?: (engine: TrainingEngine) => boolean,
): TrainingEngine | undefined {
  const order = enginePreferenceOrder(model)
  if (!order.length) return undefined
  if (isAvailable) {
    return order.find((engine) => isAvailable(engine)) ?? order[order.length - 1]
  }
  // Cold start: Anima must not enter Fast before we know it is installed.
  if (model === "anima") return order.includes("kohya") ? "kohya" : order[0]
  return order[0]
}

export function firstSupportedEngine(model: TrainingModel): TrainingEngine | undefined {
  return recommendedEngineFor(model)
    ?? TRAINING_ENGINES.find((engine) => isEngineSupported(model, engine))
}

export function firstSupportedTarget(model: TrainingModel, engine: TrainingEngine): TrainingTarget | undefined {
  return TRAINING_TARGETS.find((target) => isTargetSupported(model, engine, target))
}

export function isAiToolkitSchema(name: string): boolean {
  return TRAINING_MODULES.some(module => module.engine === "ai-toolkit" && module.schemaName === name)
}

export function isMusubiSchema(name: string): boolean {
  return TRAINING_MODULES.some(module => module.engine === "musubi" && module.schemaName === name)
}
