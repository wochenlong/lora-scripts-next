// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest"
import { DEFAULT_LOCALE, UI_CONFIGS_KEY, getStoredLocale, i18n, setLocale, setStoredLocale } from "./index"

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

  it("falls back to zh-CN for keys missing in en-US", () => {
    setLocale("en-US")
    expect(i18n.global.t("training.startHint")).toBe("配置完成后点击开始训练，右侧将显示运行状态与训练日志。")
  })
})
