import { reactive, readonly } from "vue"
import { ApiError } from "../api/client"
import { userSettingsApi, type EngineSettingsPatch, type UserSettings } from "../api/userSettings"
import { i18n } from "../i18n"
import { normalizeEnginePrefs } from "./prefs"
import { TRAINING_ENGINES } from "../training/modules"

export const ENGINE_PREFS_CHANGED = "nt-engine-prefs-changed"
const state = reactive({ settings: null as UserSettings | null, ready: false, loading: false, error: "" })
export const engineSettingsState = readonly(state)
let queue: Promise<unknown> = Promise.resolve()
let generation = 0

function enqueue<T>(operation: () => Promise<T>): Promise<T> {
  const result = queue.then(operation)
  queue = result.catch(() => {})
  return result
}
function accept(settings: UserSettings) {
  state.settings = settings
  state.ready = true
  window.dispatchEvent(new Event(ENGINE_PREFS_CHANGED))
}
function message(error: unknown) {
  return error instanceof Error ? error.message : i18n.global.t("engineSettings.saveFailed")
}
function isTimeout(error: unknown) {
  return error instanceof Error && /timeout|timed out|aborted/i.test(error.message)
}
async function fetchSettings() {
  state.loading = true
  try {
    accept(await userSettingsApi.get())
    state.error = ""
  } catch (error) {
    state.ready = false
    state.error = message(error)
    throw error
  } finally {
    state.loading = false
  }
}
export function loadEngineSettings() {
  return enqueue(fetchSettings)
}

// Build patches when they execute, not when the user action was queued.
export function patchEngineSettings(build: () => EngineSettingsPatch) {
  const requestedGeneration = generation
  return enqueue(async () => {
    if (requestedGeneration !== generation) throw new Error(i18n.global.t("engineSettings.retrySave"))
    if (!state.ready || !state.settings) throw new Error(i18n.global.t("engineSettings.unavailable"))
    const patch = build()
    if (!Object.keys(patch).length) return
    try {
      accept(await userSettingsApi.patch(state.settings.revision, patch))
      state.error = ""
    } catch (error) {
      generation++
      let detail = message(error)
      if (error instanceof ApiError && error.httpStatus === 409) {
        try {
          await fetchSettings()
        } catch (refreshError) {
          detail += `: ${message(refreshError)}`
        }
        detail = `${i18n.global.t("engineSettings.conflict")} ${detail}`
      } else if (isTimeout(error)) {
        try {
          await fetchSettings()
          detail = `${detail} ${i18n.global.t("engineSettings.reconciled")}`
        } catch (refreshError) {
          detail += `: ${message(refreshError)}`
        }
      }
      state.error = detail
      throw new Error(detail, { cause: error })
    }
  })
}

export function legacyEngineImport(): EngineSettingsPatch {
  const patch: EngineSettingsPatch = {}
  if (!state.ready || !state.settings) return patch
  try {
    const prefs = JSON.parse(localStorage.getItem("nt.training.enginePrefs") || "null")
    if (state.settings.engine_prefs === undefined && prefs && typeof prefs === "object" && !Array.isArray(prefs)) {
      patch.engine_prefs = normalizeEnginePrefs(prefs)
    }
  } catch { /* Inaccessible or malformed legacy data cannot be imported. */ }
  try {
    const order: unknown = JSON.parse(localStorage.getItem("nt.settings.engineOrder") || "null")
    if (state.settings.engine_order === undefined && Array.isArray(order)) {
      patch.engine_order = [...new Set(order.filter((id): id is string =>
        typeof id === "string" && TRAINING_ENGINES.includes(id as never)))]
    }
  } catch { /* Preserve the original legacy data. */ }
  return patch
}
export function importLegacyEngineSettings() {
  return patchEngineSettings(legacyEngineImport)
}
