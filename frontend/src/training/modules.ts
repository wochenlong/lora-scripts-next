export type TrainingModel = "anima" | "sd" | "flux" | "lumina"
export type TrainingEngine = "kohya" | "anima-fast" | "musubi"
export type TrainingTarget = "lora" | "lokr" | "finetune"

export interface TrainingModule {
  model: TrainingModel
  engine: TrainingEngine
  target: TrainingTarget
  schemaName: string
}

export const TRAINING_MODELS: readonly TrainingModel[] = ["anima", "sd", "flux", "lumina"]
export const TRAINING_ENGINES: readonly TrainingEngine[] = ["kohya", "anima-fast", "musubi"]
export const TRAINING_TARGETS: readonly TrainingTarget[] = ["lora", "lokr", "finetune"]

export const DEFAULT_SELECTION: { model: TrainingModel; engine: TrainingEngine; target: TrainingTarget } = {
  model: "anima",
  engine: "kohya",
  target: "lora",
}

export const TRAINING_MODULES: readonly TrainingModule[] = [
  { model: "anima", engine: "kohya", target: "lora", schemaName: "sd3-lora" },
  { model: "anima", engine: "anima-fast", target: "lora", schemaName: "anima-lora-fast" },
  { model: "anima", engine: "kohya", target: "finetune", schemaName: "anima-finetune" },
  { model: "sd", engine: "kohya", target: "lora", schemaName: "lora-master" },
  { model: "sd", engine: "kohya", target: "finetune", schemaName: "dreambooth" },
  { model: "flux", engine: "kohya", target: "lora", schemaName: "flux-lora" },
  { model: "lumina", engine: "kohya", target: "lora", schemaName: "lumina2-lora" },
]

export const SCHEMA_META: Record<string, { titleKey: string; areaKey: string }> = {
  "sd3-lora": { titleKey: "training.schemas.sd3-lora.title", areaKey: "training.schemas.sd3-lora.area" },
  "anima-lora-fast": { titleKey: "training.schemas.anima-lora-fast.title", areaKey: "training.schemas.anima-lora-fast.area" },
  "anima-finetune": { titleKey: "training.schemas.anima-finetune.title", areaKey: "training.schemas.anima-finetune.area" },
  "lora-master": { titleKey: "training.schemas.lora-master.title", areaKey: "training.schemas.lora-master.area" },
  dreambooth: { titleKey: "training.schemas.dreambooth.title", areaKey: "training.schemas.dreambooth.area" },
  "flux-lora": { titleKey: "training.schemas.flux-lora.title", areaKey: "training.schemas.flux-lora.area" },
  "lumina2-lora": { titleKey: "training.schemas.lumina2-lora.title", areaKey: "training.schemas.lumina2-lora.area" },
}

export function resolveModule(model: TrainingModel, engine: TrainingEngine, target: TrainingTarget): TrainingModule | undefined {
  return TRAINING_MODULES.find((module) => module.model === model && module.engine === engine && module.target === target)
}

export function moduleForSchema(schemaName: string): TrainingModule | undefined {
  return TRAINING_MODULES.find((module) => module.schemaName === schemaName)
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
