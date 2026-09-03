import { createI18n } from "vue-i18n"
import epZhCN from "element-plus/es/locale/lang/zh-cn"
import epEnUS from "element-plus/es/locale/lang/en"
import zhCN from "./messages/zh-CN"
import enUS from "./messages/en-US"

export const SUPPORTED_LOCALES = [
  { value: "zh-CN", label: "简体中文", direction: "ltr" },
  { value: "en-US", label: "English", direction: "ltr" },
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

export function getStoredLocale(): AppLocale | undefined {
  const language = readUiConfigs().language
  return isAppLocale(language) ? language : undefined
}

export function setStoredLocale(locale: AppLocale) {
  const configs = readUiConfigs()
  configs.language = locale
  localStorage.setItem(UI_CONFIGS_KEY, JSON.stringify(configs))
}

export function normalizeLocaleTag(tag: string): string | undefined {
  const candidate = tag.trim().replace(/_/g, "-")
  if (!candidate) return undefined
  try {
    const [canonical] = Intl.getCanonicalLocales(candidate)
    return canonical
  } catch {
    return undefined
  }
}

export function matchLocaleCandidate(candidate: string): AppLocale | undefined {
  const tag = normalizeLocaleTag(candidate)
  if (!tag) return undefined
  if (isAppLocale(tag)) return tag
  const lower = tag.toLowerCase()
  if (lower === "zh" || lower.startsWith("zh-")) return "zh-CN"
  if (lower === "en" || lower.startsWith("en-")) return "en-US"
  return undefined
}

function browserLocaleCandidates(): string[] {
  if (typeof navigator === "undefined") return []
  const candidates = [...(navigator.languages ?? [])]
  if (navigator.language) candidates.push(navigator.language)
  return candidates
}

export function resolveInitialLocale(candidates: readonly string[] = browserLocaleCandidates()): AppLocale {
  const stored = getStoredLocale()
  if (stored) return stored
  for (const candidate of candidates) {
    const matched = matchLocaleCandidate(candidate)
    if (matched) return matched
  }
  return DEFAULT_LOCALE
}

export function applyDocumentLocale(locale: AppLocale) {
  if (typeof document === "undefined") return
  const meta = SUPPORTED_LOCALES.find((entry) => entry.value === locale)
  document.documentElement.lang = locale
  document.documentElement.dir = meta?.direction ?? "ltr"
}

const initialLocale = resolveInitialLocale()
applyDocumentLocale(initialLocale)

export const i18n = createI18n({
  legacy: false,
  locale: initialLocale,
  fallbackLocale: DEFAULT_LOCALE,
  messages: { "zh-CN": zhCN, "en-US": enUS },
})

export function setLocale(locale: AppLocale) {
  i18n.global.locale.value = locale
  applyDocumentLocale(locale)
  setStoredLocale(locale)
}

const elementPlusLocales = { "zh-CN": epZhCN, "en-US": epEnUS } as const

export function getElementPlusLocale(locale: AppLocale) {
  return elementPlusLocales[locale] ?? epZhCN
}
