// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest"
import {
  DEFAULT_LOCALE,
  SUPPORTED_LOCALES,
  UI_CONFIGS_KEY,
  getElementPlusLocale,
  getStoredLocale,
  i18n,
  localeMessages,
  matchLocaleCandidate,
  normalizeLocaleTag,
  resolveInitialLocale,
  setLocale,
  setStoredLocale,
} from "./index"

function flattenLeafKeys(obj: Record<string, unknown>, prefix = ""): string[] {
  return Object.entries(obj).flatMap(([key, value]) =>
    value && typeof value === "object"
      ? flattenLeafKeys(value as Record<string, unknown>, `${prefix}${key}.`)
      : [`${prefix}${key}`],
  )
}

function leafValues(obj: Record<string, unknown>, prefix = ""): Record<string, string> {
  return Object.entries(obj).reduce<Record<string, string>>((acc, [key, value]) => {
    if (value && typeof value === "object") {
      Object.assign(acc, leafValues(value as Record<string, unknown>, `${prefix}${key}.`))
    } else {
      acc[`${prefix}${key}`] = String(value)
    }
    return acc
  }, {})
}

function interpolationParams(text: string): string[] {
  return [...text.matchAll(/\{([^{}]+)\}/g)].map((match) => match[1]).sort()
}

describe("i18n infrastructure", () => {
  beforeEach(() => {
    localStorage.clear()
    setLocale(DEFAULT_LOCALE)
    localStorage.clear()
  })

  it("has no explicit locale when nothing is stored", () => {
    expect(getStoredLocale()).toBeUndefined()
  })

  it("ignores unknown or corrupted stored values", () => {
    localStorage.setItem(UI_CONFIGS_KEY, JSON.stringify({ language: "fr-FR" }))
    expect(getStoredLocale()).toBeUndefined()
    localStorage.setItem(UI_CONFIGS_KEY, "not-json")
    expect(getStoredLocale()).toBeUndefined()
  })

  it("persists locale without dropping other ui-configs keys", () => {
    localStorage.setItem(UI_CONFIGS_KEY, JSON.stringify({ tensorboard_url: "http://tb:6006" }))
    setStoredLocale("en-US")
    const stored = JSON.parse(localStorage.getItem(UI_CONFIGS_KEY) || "{}")
    expect(stored.language).toBe("en-US")
    expect(stored.tensorboard_url).toBe("http://tb:6006")
    expect(getStoredLocale()).toBe("en-US")
  })

  it("switches the active locale", () => {
    setLocale("en-US")
    expect(i18n.global.locale.value).toBe("en-US")
    expect(i18n.global.t("nav.training")).toBe("Training")
  })

  it("maps app locales to Element Plus locale packs", () => {
    expect(getElementPlusLocale("zh-CN").el.messagebox.confirm).toBe("确定")
    expect(getElementPlusLocale("en-US").el.messagebox.confirm).toBe("OK")
  })
})

describe("locale registry", () => {
  const registeredLocales = SUPPORTED_LOCALES.map((entry) => entry.value)

  it("declares native label, status and direction for every locale", () => {
    for (const entry of SUPPORTED_LOCALES) {
      expect(entry.label.length).toBeGreaterThan(0)
      expect(["stable", "beta"]).toContain(entry.status)
      expect(["ltr", "rtl"]).toContain(entry.direction)
    }
  })

  it("registers app messages and Element Plus packs for every locale", () => {
    for (const locale of registeredLocales) {
      expect(localeMessages[locale], `messages for ${locale}`).toBeDefined()
      expect(getElementPlusLocale(locale).name, `Element Plus locale for ${locale}`).toBeDefined()
    }
  })

  it("keeps leaf keys in parity with zh-CN for every locale", () => {
    const baseline = flattenLeafKeys(localeMessages[DEFAULT_LOCALE] as Record<string, unknown>).sort()
    for (const locale of registeredLocales) {
      const keys = flattenLeafKeys(localeMessages[locale] as Record<string, unknown>).sort()
      expect(keys, `key parity for ${locale}`).toEqual(baseline)
    }
  })

  it("keeps interpolation parameters in parity with zh-CN for every locale", () => {
    const baseline = leafValues(localeMessages[DEFAULT_LOCALE] as Record<string, unknown>)
    for (const locale of registeredLocales) {
      const values = leafValues(localeMessages[locale] as Record<string, unknown>)
      for (const [key, text] of Object.entries(values)) {
        expect(interpolationParams(text), `interpolation parity for ${locale}:${key}`)
          .toEqual(interpolationParams(baseline[key]))
      }
    }
  })

  it("resolves every registered locale to itself", () => {
    for (const locale of registeredLocales) {
      expect(matchLocaleCandidate(locale)).toBe(locale)
    }
  })
})

describe("locale normalization", () => {
  it("canonicalizes separators and casing", () => {
    expect(normalizeLocaleTag("en_US")).toBe("en-US")
    expect(normalizeLocaleTag("EN-us")).toBe("en-US")
    expect(normalizeLocaleTag(" zh_cn ")).toBe("zh-CN")
  })

  it("rejects invalid tags without throwing", () => {
    expect(normalizeLocaleTag("")).toBeUndefined()
    expect(normalizeLocaleTag("!!!")).toBeUndefined()
    expect(normalizeLocaleTag("not a locale")).toBeUndefined()
  })
})

describe("matchLocaleCandidate", () => {
  it("matches exact supported locales", () => {
    expect(matchLocaleCandidate("zh-CN")).toBe("zh-CN")
    expect(matchLocaleCandidate("en-US")).toBe("en-US")
  })

  it("maps regional variants of supported languages", () => {
    expect(matchLocaleCandidate("en-GB")).toBe("en-US")
    expect(matchLocaleCandidate("zh-Hans-CN")).toBe("zh-CN")
    expect(matchLocaleCandidate("zh-SG")).toBe("zh-CN")
    expect(matchLocaleCandidate("zh")).toBe("zh-CN")
  })

  it("maps Traditional Chinese and CJK variants to their locales", () => {
    expect(matchLocaleCandidate("zh-TW")).toBe("zh-TW")
    expect(matchLocaleCandidate("zh-Hant-TW")).toBe("zh-TW")
    expect(matchLocaleCandidate("zh-HK")).toBe("zh-HK")
    expect(matchLocaleCandidate("zh-MO")).toBe("zh-HK")
    expect(matchLocaleCandidate("zh-Hant-MO")).toBe("zh-HK")
    expect(matchLocaleCandidate("ja")).toBe("ja-JP")
    expect(matchLocaleCandidate("ko-KP")).toBe("ko-KR")
  })

  it("returns undefined for unknown languages", () => {
    expect(matchLocaleCandidate("fr-FR")).toBeUndefined()
    expect(matchLocaleCandidate("!!!")).toBeUndefined()
  })
})

describe("resolveInitialLocale", () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it("prefers the stored explicit choice over browser candidates", () => {
    setStoredLocale("en-US")
    expect(resolveInitialLocale(["zh-CN", "en-US"])).toBe("en-US")
  })

  it("uses the browser preferred language when nothing is stored", () => {
    expect(resolveInitialLocale(["en-US"])).toBe("en-US")
  })

  it("keeps matching later candidates when the first is unknown", () => {
    expect(resolveInitialLocale(["fr-FR", "en-US"])).toBe("en-US")
  })

  it("skips invalid candidates and falls back to zh-CN", () => {
    expect(resolveInitialLocale(["!!!", "fr-FR"])).toBe("zh-CN")
    expect(resolveInitialLocale([])).toBe("zh-CN")
  })

  it("does not persist the auto-detected locale", () => {
    expect(resolveInitialLocale(["en-US"])).toBe("en-US")
    expect(localStorage.getItem(UI_CONFIGS_KEY)).toBeNull()
  })
})

describe("document locale sync", () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it("sets document lang and dir on initialization", () => {
    expect(document.documentElement.lang).toBe(i18n.global.locale.value)
    expect(document.documentElement.dir).toBe("ltr")
  })

  it("updates document lang and dir when switching locale", () => {
    setLocale("en-US")
    expect(document.documentElement.lang).toBe("en-US")
    expect(document.documentElement.dir).toBe("ltr")
    setLocale("zh-CN")
    expect(document.documentElement.lang).toBe("zh-CN")
    expect(document.documentElement.dir).toBe("ltr")
  })
})
