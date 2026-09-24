import { UI_CONFIGS_KEY } from "../i18n"

export type PathPickerPreference = "auto" | "native" | "web"

function readUiConfigs(): Record<string, unknown> {
  try {
    const parsed = JSON.parse(localStorage.getItem(UI_CONFIGS_KEY) || "{}")
    return parsed && typeof parsed === "object" ? parsed as Record<string, unknown> : {}
  } catch {
    return {}
  }
}

function isPathPickerPreference(value: unknown): value is PathPickerPreference {
  return value === "auto" || value === "native" || value === "web"
}

export function readPathPickerPreference(): PathPickerPreference {
  const value = readUiConfigs().path_picker
  return isPathPickerPreference(value) ? value : "auto"
}

export function writePathPickerPreference(value: PathPickerPreference): void {
  const configs = readUiConfigs()
  configs.path_picker = value
  localStorage.setItem(UI_CONFIGS_KEY, JSON.stringify(configs))
}
