const PREFS_KEY = "nt.training.enginePrefs"

export interface EnginePrefs {
  /** Remember last model/engine/target selection across visits. Default true. */
  rememberLast: boolean
  lastByModel?: Partial<Record<string, { engine: string; target: string }>>
  /** Full last selection, restored when landing on /training without a query. */
  last?: { model: string; engine: string; target: string }
}

export function readEnginePrefs(): EnginePrefs {
  try {
    const parsed = JSON.parse(localStorage.getItem(PREFS_KEY) || "{}")
    if (!parsed || typeof parsed !== "object") return { rememberLast: true }
    return {
      rememberLast: parsed.rememberLast !== false,
      lastByModel: parsed.lastByModel && typeof parsed.lastByModel === "object" ? parsed.lastByModel : {},
      last: parsed.last && typeof parsed.last === "object" ? parsed.last : undefined,
    }
  } catch {
    return { rememberLast: true }
  }
}

export function writeEnginePrefs(prefs: EnginePrefs) {
  localStorage.setItem(PREFS_KEY, JSON.stringify(prefs))
}

export function rememberSelection(model: string, engine: string, target: string) {
  const prefs = readEnginePrefs()
  if (!prefs.rememberLast) return
  prefs.lastByModel = { ...(prefs.lastByModel || {}), [model]: { engine, target } }
  prefs.last = { model, engine, target }
  writeEnginePrefs(prefs)
}

export function lastSelectionFor(model: string): { engine: string; target: string } | undefined {
  const prefs = readEnginePrefs()
  if (!prefs.rememberLast) return undefined
  return prefs.lastByModel?.[model]
}

export function lastSelection(): { model: string; engine: string; target: string } | undefined {
  const prefs = readEnginePrefs()
  if (!prefs.rememberLast) return undefined
  return prefs.last
}
