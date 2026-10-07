import { apiData } from "./client"
import type { EnginePrefs } from "../engines/prefs"

export interface EngineSettingsPatch {
  engine_prefs?: EnginePrefs
  engine_order?: string[]
}
export interface UserSettings extends EngineSettingsPatch {
  schema_version: 1
  revision: number
}
export const userSettingsApi = {
  get: () => apiData<UserSettings>("/api/user-data/settings", { signal: AbortSignal.timeout(10_000) }),
  patch: (revision: number, patch: EngineSettingsPatch) => apiData<UserSettings>("/api/user-data/settings", {
    method: "PATCH",
    signal: AbortSignal.timeout(10_000),
    body: JSON.stringify({ revision, patch }),
  }),
}
