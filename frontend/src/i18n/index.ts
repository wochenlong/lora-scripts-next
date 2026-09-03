import { createI18n } from "vue-i18n"
import epZhCN from "element-plus/es/locale/lang/zh-cn"
import epEnUS from "element-plus/es/locale/lang/en"
import epZhTW from "element-plus/es/locale/lang/zh-tw"
import epZhHK from "element-plus/es/locale/lang/zh-hk"
import epJaJP from "element-plus/es/locale/lang/ja"
import epKoKR from "element-plus/es/locale/lang/ko"
import epEsES from "element-plus/es/locale/lang/es"
import epFrFR from "element-plus/es/locale/lang/fr"
import epDeDE from "element-plus/es/locale/lang/de"
import epRuRU from "element-plus/es/locale/lang/ru"
import epPtPT from "element-plus/es/locale/lang/pt"
import epPtBR from "element-plus/es/locale/lang/pt-br"
import epAr from "element-plus/es/locale/lang/ar"
import zhCN from "./messages/zh-CN"
import enUS from "./messages/en-US"
import zhTW from "./messages/zh-TW"
import zhHK from "./messages/zh-HK"
import jaJP from "./messages/ja-JP"
import koKR from "./messages/ko-KR"
import esES from "./messages/es-ES"
import frFR from "./messages/fr-FR"
import deDE from "./messages/de-DE"
import ruRU from "./messages/ru-RU"
import ptPT from "./messages/pt-PT"
import ptBR from "./messages/pt-BR"
import ar from "./messages/ar"

export type LocaleStatus = "stable" | "beta"
export type LocaleDirection = "ltr" | "rtl"

function defineLocale<L extends string>(meta: { value: L; label: string; status: LocaleStatus; direction: LocaleDirection }) {
  return meta
}

export const SUPPORTED_LOCALES = [
  defineLocale({ value: "zh-CN", label: "简体中文", status: "stable", direction: "ltr" }),
  defineLocale({ value: "en-US", label: "English", status: "stable", direction: "ltr" }),
  defineLocale({ value: "zh-TW", label: "繁體中文（台灣）", status: "beta", direction: "ltr" }),
  defineLocale({ value: "zh-HK", label: "繁體中文（香港）", status: "beta", direction: "ltr" }),
  defineLocale({ value: "ja-JP", label: "日本語", status: "beta", direction: "ltr" }),
  defineLocale({ value: "ko-KR", label: "한국어", status: "beta", direction: "ltr" }),
  defineLocale({ value: "es-ES", label: "Español", status: "beta", direction: "ltr" }),
  defineLocale({ value: "fr-FR", label: "Français", status: "beta", direction: "ltr" }),
  defineLocale({ value: "de-DE", label: "Deutsch", status: "beta", direction: "ltr" }),
  defineLocale({ value: "ru-RU", label: "Русский", status: "beta", direction: "ltr" }),
  defineLocale({ value: "pt-PT", label: "Português (Portugal)", status: "beta", direction: "ltr" }),
  defineLocale({ value: "pt-BR", label: "Português (Brasil)", status: "beta", direction: "ltr" }),
  defineLocale({ value: "ar", label: "العربية", status: "beta", direction: "rtl" }),
]

export type AppLocale = (typeof SUPPORTED_LOCALES)[number]["value"]
export const DEFAULT_LOCALE: AppLocale = "zh-CN"
export const UI_CONFIGS_KEY = "ui-configs"

export type AppMessages = typeof zhCN
type ElementPlusMessages = typeof epZhCN

export const localeMessages: Record<AppLocale, AppMessages> = {
  "zh-CN": zhCN,
  "en-US": enUS,
  "zh-TW": zhTW,
  "zh-HK": zhHK,
  "ja-JP": jaJP,
  "ko-KR": koKR,
  "es-ES": esES,
  "fr-FR": frFR,
  "de-DE": deDE,
  "ru-RU": ruRU,
  "pt-PT": ptPT,
  "pt-BR": ptBR,
  "ar": ar,
}

const elementPlusLocales: Record<AppLocale, ElementPlusMessages> = {
  "zh-CN": epZhCN,
  "en-US": epEnUS,
  "zh-TW": epZhTW,
  "zh-HK": epZhHK,
  "ja-JP": epJaJP,
  "ko-KR": epKoKR,
  "es-ES": epEsES,
  "fr-FR": epFrFR,
  "de-DE": epDeDE,
  "ru-RU": epRuRU,
  "pt-PT": epPtPT,
  "pt-BR": epPtBR,
  "ar": epAr,
}

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

const LOCALE_MATCH_RULES: ReadonlyArray<{ locale: AppLocale; test: (tag: string) => boolean }> = [
  { locale: "zh-TW", test: (t) => t === "zh-tw" || t === "zh-hant-tw" },
  { locale: "zh-HK", test: (t) => t === "zh-hk" || t === "zh-mo" || t === "zh-hant-hk" || t === "zh-hant-mo" },
  { locale: "zh-CN", test: (t) => t === "zh" || t.startsWith("zh-") },
  { locale: "ja-JP", test: (t) => t === "ja" || t.startsWith("ja-") },
  { locale: "ko-KR", test: (t) => t === "ko" || t.startsWith("ko-") },
  { locale: "es-ES", test: (t) => t === "es" || t.startsWith("es-") },
  { locale: "fr-FR", test: (t) => t === "fr" || t.startsWith("fr-") },
  { locale: "de-DE", test: (t) => t === "de" || t.startsWith("de-") },
  { locale: "ru-RU", test: (t) => t === "ru" || t.startsWith("ru-") },
  { locale: "pt-BR", test: (t) => t === "pt-br" },
  { locale: "pt-PT", test: (t) => t === "pt" || t.startsWith("pt-") },
  { locale: "ar", test: (t) => t === "ar" || t.startsWith("ar-") },
  { locale: "en-US", test: (t) => t === "en" || t.startsWith("en-") },
]

export function matchLocaleCandidate(candidate: string): AppLocale | undefined {
  const tag = normalizeLocaleTag(candidate)
  if (!tag) return undefined
  if (isAppLocale(tag)) return tag
  const lower = tag.toLowerCase()
  return LOCALE_MATCH_RULES.find((rule) => rule.test(lower))?.locale
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
  messages: localeMessages,
})

export function setLocale(locale: AppLocale) {
  i18n.global.locale.value = locale
  applyDocumentLocale(locale)
  setStoredLocale(locale)
}

export function getElementPlusLocale(locale: AppLocale) {
  return elementPlusLocales[locale]
}
