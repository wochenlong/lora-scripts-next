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

export const SCHEMA_META: Record<string, { title: string; area: string }> = {
  "sd3-lora": { title: "Anima LoRA", area: "Anima DiT · Kohya-ss · LoRA" },
  "anima-lora-fast": { title: "Anima LoRA Fast", area: "Anima DiT · Anima Fast · LoRA" },
  "anima-finetune": { title: "Anima 全量微调", area: "Anima DiT · Kohya-ss · 全量微调" },
  "lora-master": { title: "SD / SDXL LoRA", area: "SD / SDXL · Kohya-ss · LoRA" },
  dreambooth: { title: "SD / SDXL 全量微调", area: "SD / SDXL · Kohya-ss · 全量微调" },
  "flux-lora": { title: "Flux LoRA", area: "Flux · Kohya-ss · LoRA" },
  "lumina2-lora": { title: "Lumina 2 LoRA", area: "Lumina 2 · Kohya-ss · LoRA" },
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
