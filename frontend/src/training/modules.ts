import type { FormModel } from "../schema/adapter"

export type TrainingModel = "anima" | "sd15" | "sdxl" | "flux" | "lumina" | "krea2" | "klein"
export type TrainingEngine = "kohya" | "anima-fast" | "musubi" | "ai-toolkit"
export type TrainingTarget = "lora" | "finetune"

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

export const TRAINING_MODELS: readonly TrainingModel[] = ["anima", "sd15", "sdxl", "flux", "lumina", "krea2", "klein"]
export const TRAINING_ENGINES: readonly TrainingEngine[] = ["kohya", "anima-fast", "musubi", "ai-toolkit"]
export const TRAINING_TARGETS: readonly TrainingTarget[] = ["lora", "finetune"]

export const DEFAULT_SELECTION: { model: TrainingModel; engine: TrainingEngine; target: TrainingTarget } = {
  model: "anima",
  engine: "kohya",
  target: "lora",
}

// NOTE: sdxl entries intentionally precede sd15 ones so moduleForSchema()
// resolves shared schemas (lora-master, dreambooth) to the sdxl module,
// matching the previous single-SD default (schema default was sdxl-lora).
export const TRAINING_MODULES: readonly TrainingModule[] = [
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
  { model: "klein", engine: "ai-toolkit", target: "lora", schemaName: "klein-lora" },
]

export const SCHEMA_META: Record<string, { titleKey: string; areaKey: string }> = {
  "sd3-lora": { titleKey: "training.schemas.sd3-lora.title", areaKey: "training.schemas.sd3-lora.area" },
  "anima-lora-fast": { titleKey: "training.schemas.anima-lora-fast.title", areaKey: "training.schemas.anima-lora-fast.area" },
  "anima-finetune": { titleKey: "training.schemas.anima-finetune.title", areaKey: "training.schemas.anima-finetune.area" },
  "lora-master": { titleKey: "training.schemas.lora-master.title", areaKey: "training.schemas.lora-master.area" },
  dreambooth: { titleKey: "training.schemas.dreambooth.title", areaKey: "training.schemas.dreambooth.area" },
  "flux-lora": { titleKey: "training.schemas.flux-lora.title", areaKey: "training.schemas.flux-lora.area" },
  "lumina2-lora": { titleKey: "training.schemas.lumina2-lora.title", areaKey: "training.schemas.lumina2-lora.area" },
  "krea2-lora": { titleKey: "training.schemas.krea2-lora.title", areaKey: "training.schemas.krea2-lora.area" },
  "klein-lora": { titleKey: "training.schemas.klein-lora.title", areaKey: "training.schemas.klein-lora.area" },
}

export function normalizeModel(value: unknown): TrainingModel | undefined {
  // Legacy "sd" covered both SD 1.5 and SDXL; map it to sdxl, the old default.
  if (value === "sd") return "sdxl"
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
  return TRAINING_MODULES.find((module) => module.defaults?.model_train_type === trainType)
    ?? TRAINING_MODULES.find((module) => module.schemaName === trainType)
}

export function isEngineSupported(model: TrainingModel, engine: TrainingEngine): boolean {
  return TRAINING_MODULES.some((module) => module.model === model && module.engine === engine)
}

export function isTargetSupported(model: TrainingModel, engine: TrainingEngine, target: TrainingTarget): boolean {
  return Boolean(resolveModule(model, engine, target))
}

export function firstSupportedEngine(model: TrainingModel): TrainingEngine | undefined {
  return TRAINING_ENGINES.find((engine) => isEngineSupported(model, engine))
}

export function firstSupportedTarget(model: TrainingModel, engine: TrainingEngine): TrainingTarget | undefined {
  return TRAINING_TARGETS.find((target) => isTargetSupported(model, engine, target))
}
