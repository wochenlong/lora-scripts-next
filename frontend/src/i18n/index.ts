import { createI18n } from "vue-i18n"
import zhCN from "./messages/zh-CN"
import enUS from "./messages/en-US"

export const SUPPORTED_LOCALES = [
  { value: "zh-CN", label: "简体中文" },
  { value: "en-US", label: "English" },
] as const

export type AppLocale = (typeof SUPPORTED_LOCALES)[number]["value"]
export const DEFAULT_LOCALE: AppLocale = "zh-CN"
export const UI_CONFIGS_KEY = "ui-configs"

function readUiConfigs(): Record<string, unknown> {
  try {
    const raw = localStorage.getItem(UI_CONFIGS_KEY)
    const parsed = raw ? JSON.parse(raw) : {}
    return parsed && typeof parsed === "object" ? parsed as Record<string, unknown> : {}
  } catch {
    return {}
  }
}

function isAppLocale(value: unknown): value is AppLocale {
  return SUPPORTED_LOCALES.some((locale) => locale.value === value)
}

export function getStoredLocale(): AppLocale {
  const language = readUiConfigs().language
  return isAppLocale(language) ? language : DEFAULT_LOCALE
}

export function setStoredLocale(locale: AppLocale) {
  const configs = readUiConfigs()
  configs.language = locale
  localStorage.setItem(UI_CONFIGS_KEY, JSON.stringify(configs))
}

export const i18n = createI18n({
  legacy: false,
  locale: getStoredLocale(),
  fallbackLocale: DEFAULT_LOCALE,
  messages: { "zh-CN": zhCN, "en-US": enUS },
})

export function setLocale(locale: AppLocale) {
  i18n.global.locale.value = locale
  setStoredLocale(locale)
}
