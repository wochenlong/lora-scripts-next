// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest"
import { DEFAULT_LOCALE, UI_CONFIGS_KEY, getElementPlusLocale, getStoredLocale, i18n, setLocale, setStoredLocale } from "./index"
import zhCN from "./messages/zh-CN"
import enUS from "./messages/en-US"

describe("i18n infrastructure", () => {
  beforeEach(() => {
    localStorage.clear()
    setLocale(DEFAULT_LOCALE)
  })

  it("defaults to zh-CN when nothing is stored", () => {
    expect(getStoredLocale()).toBe("zh-CN")
  })

  it("falls back to default for unknown stored values", () => {
    localStorage.setItem(UI_CONFIGS_KEY, JSON.stringify({ language: "fr-FR" }))
    expect(getStoredLocale()).toBe(DEFAULT_LOCALE)
    localStorage.setItem(UI_CONFIGS_KEY, "not-json")
    expect(getStoredLocale()).toBe(DEFAULT_LOCALE)
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
