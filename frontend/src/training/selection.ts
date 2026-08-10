import { lastSelection, lastSelectionFor } from "../engines/prefs"
import {
  DEFAULT_SELECTION,
  TRAINING_ENGINES,
  TRAINING_TARGETS,
  isEngineSupported,
  isTargetSupported,
  moduleForSchema,
  normalizeModel,
  type TrainingEngine,
  type TrainingModel,
  type TrainingTarget,
} from "./modules"

export interface TrainingSelection {
  model: TrainingModel
  engine: TrainingEngine
  target: TrainingTarget
}

const isEngine = (value: unknown): value is TrainingEngine => TRAINING_ENGINES.includes(value as TrainingEngine)
const isTarget = (value: unknown): value is TrainingTarget => TRAINING_TARGETS.includes(value as TrainingTarget)

/**
 * Resolve the initial workbench selection from the route query.
 * Explicit query (or ?schema=) always wins; a bare /training restores the
 * remembered last selection, falling back to per-model engine/target prefs
 * and finally DEFAULT_SELECTION.
 */
export function resolveInitialSelection(query: Record<string, unknown>): TrainingSelection {
  const fromSchema = typeof query.schema === "string" ? moduleForSchema(query.schema) : undefined
  if (fromSchema) return { model: fromSchema.model, engine: fromSchema.engine, target: fromSchema.target }

  const selection: TrainingSelection = { ...DEFAULT_SELECTION }
  const hasExplicit = Boolean(query.model || query.engine || query.target)
  const normalized = normalizeModel(query.model)
  if (normalized) selection.model = normalized
  if (isEngine(query.engine)) selection.engine = query.engine
  if (isTarget(query.target)) selection.target = query.target
  if (hasExplicit) return selection

  const remembered = lastSelection()
  if (remembered) {
    const rememberedModel = normalizeModel(remembered.model)
    if (rememberedModel) {
      selection.model = rememberedModel
      if (isEngine(remembered.engine) && isEngineSupported(selection.model, remembered.engine)) selection.engine = remembered.engine
      if (isTarget(remembered.target) && isTargetSupported(selection.model, selection.engine, remembered.target)) selection.target = remembered.target
    }
    return selection
  }

  const perModel = lastSelectionFor(selection.model)
  if (perModel) {
    if (isEngine(perModel.engine) && isEngineSupported(selection.model, perModel.engine)) selection.engine = perModel.engine
    if (isTarget(perModel.target) && isTargetSupported(selection.model, selection.engine, perModel.target)) selection.target = perModel.target
  }
  return selection
}
