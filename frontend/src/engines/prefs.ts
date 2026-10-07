import { TRAINING_ENGINES, type TrainingEngine } from "../training/modules"
import { engineSettingsState, patchEngineSettings } from "./settings"
export { ENGINE_PREFS_CHANGED } from "./settings"

export interface EnginePrefs {
  defaultEngine?: TrainingEngine
  /** Remember last model/engine/target selection across visits. Default true. */
  rememberLast: boolean
  lastByModel?: Partial<Record<string, { engine: string; target: string }>>
}

export function normalizeEnginePrefs(value: unknown): EnginePrefs {
  const parsed = (value && typeof value === "object" ? value : {}) as Partial<EnginePrefs>
  const lastByModel: EnginePrefs["lastByModel"] = {}
  if (parsed.lastByModel && typeof parsed.lastByModel === "object") {
    for (const [model, selection] of Object.entries(parsed.lastByModel)) {
      if (selection && typeof selection.engine === "string" && typeof selection.target === "string") {
        lastByModel[model] = { engine: selection.engine, target: selection.target }
      }
    }
  }
  const validSelections = Object.entries(lastByModel).filter((entry): entry is [string, { engine: string; target: string }] => {
    const selection = entry[1]
    if (!selection) return false
    return TRAINING_ENGINES.includes(selection.engine as TrainingEngine)
      && (selection.target === "lora" || selection.target === "finetune")
  })
  return {
    defaultEngine: TRAINING_ENGINES.includes(parsed.defaultEngine as TrainingEngine) ? parsed.defaultEngine : "kohya",
    rememberLast: parsed.rememberLast !== false,
    lastByModel: Object.fromEntries(validSelections),
  }
}

export function readEnginePrefs(): EnginePrefs {
  return normalizeEnginePrefs(engineSettingsState.settings?.engine_prefs)
}

export function writeEnginePrefs(prefs: Partial<Pick<EnginePrefs, "defaultEngine" | "rememberLast">>) {
  const changes = { ...prefs }
  return patchEngineSettings(() => ({ engine_prefs: { ...readEnginePrefs(), ...changes } }))
}

export function rememberSelection(model: string, engine: string, target: string) {
  return patchEngineSettings(() => {
    const prefs = readEnginePrefs()
    if (!prefs.rememberLast) return {}
    return { engine_prefs: { ...prefs, lastByModel: { ...prefs.lastByModel, [model]: { engine, target } } } }
  })
}

export function lastSelectionFor(model: string): { engine: string; target: string } | undefined {
  const prefs = readEnginePrefs()
  if (!prefs.rememberLast) return undefined
  return prefs.lastByModel?.[model]
}
