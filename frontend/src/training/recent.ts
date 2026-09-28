import type { TrainingEngine, TrainingModel, TrainingTarget } from "./modules"
import { readEnginePrefs } from "../engines/prefs"

export const LAST_TRAINING_SELECTION_KEY = "nt.training.lastSelection"

export interface RecentTrainingSelection {
  model: TrainingModel
  engine: TrainingEngine
  target: TrainingTarget
}

export function readRecentTrainingSelection(): RecentTrainingSelection | undefined {
  if (!readEnginePrefs().rememberLast) return undefined
  try {
    const parsed = JSON.parse(localStorage.getItem(LAST_TRAINING_SELECTION_KEY) || "null")
    if (!parsed || typeof parsed !== "object") return undefined
    if (typeof parsed.model !== "string" || typeof parsed.engine !== "string" || typeof parsed.target !== "string") return undefined
    return parsed as RecentTrainingSelection
  } catch {
    return undefined
  }
}

export function writeRecentTrainingSelection(selection: RecentTrainingSelection) {
  if (!readEnginePrefs().rememberLast) return
  localStorage.setItem(LAST_TRAINING_SELECTION_KEY, JSON.stringify(selection))
}
