// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest"
import {
  DEFAULT_LOCALE,
  UI_CONFIGS_KEY,
  getElementPlusLocale,
  getStoredLocale,
  i18n,
  matchLocaleCandidate,
  normalizeLocaleTag,
  resolveInitialLocale,
  setLocale,
  setStoredLocale,
} from "./index"
import zhCN from "./messages/zh-CN"
import enUS from "./messages/en-US"

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

  it("keeps en-US keys in parity with zh-CN", () => {
    const flatten = (obj: Record<string, unknown>, prefix = ""): string[] =>
      Object.entries(obj).flatMap(([key, value]) =>
        value && typeof value === "object"
          ? flatten(value as Record<string, unknown>, `${prefix}${key}.`)
          : [`${prefix}${key}`],
      )
    const zhKeys = flatten(zhCN).sort()
    const enKeys = flatten(enUS).sort()
    expect(enKeys).toEqual(zhKeys)
  })

  it("maps app locales to Element Plus locale packs", () => {
    expect(getElementPlusLocale("zh-CN").el.messagebox.confirm).toBe("确定")
    expect(getElementPlusLocale("en-US").el.messagebox.confirm).toBe("OK")
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
    expect(matchLocaleCandidate("zh-TW")).toBe("zh-CN")
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
