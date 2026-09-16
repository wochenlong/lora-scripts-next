// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest"

function mockNavigatorLanguages(languages: string[]) {
  Object.defineProperty(navigator, "language", { value: languages[0] ?? "en-US", configurable: true })
  Object.defineProperty(navigator, "languages", { value: languages, configurable: true })
}

async function importFreshI18n(languages: string[], storedLocale?: string) {
  vi.resetModules()
  localStorage.clear()
  if (storedLocale) localStorage.setItem("ui-configs", JSON.stringify({ language: storedLocale }))
  mockNavigatorLanguages(languages)
  return import("./index")
}

afterEach(() => {
  localStorage.clear()
  document.documentElement.lang = ""
  document.documentElement.dir = ""
})

describe("startup locale detection", () => {
  it("matches later browser candidates and sets document attributes before mount", async () => {
    const module = await importFreshI18n(["xx-XX", "de-DE"])

    expect(module.i18n.global.locale.value).toBe("de-DE")
    expect(document.documentElement.lang).toBe("de-DE")
    expect(document.documentElement.dir).toBe("ltr")
    expect(localStorage.getItem("ui-configs")).toBeNull()
  })

  it("detects Arabic from the browser and applies rtl before mount", async () => {
    const module = await importFreshI18n(["ar-EG"])

    expect(module.i18n.global.locale.value).toBe("ar")
    expect(document.documentElement.lang).toBe("ar")
    expect(document.documentElement.dir).toBe("rtl")
  })

  it("keeps an explicit stored choice ahead of the browser", async () => {
    const module = await importFreshI18n(["en-US"], "pt-PT")

    expect(module.i18n.global.locale.value).toBe("pt-PT")
    expect(document.documentElement.lang).toBe("pt-PT")
    expect(document.documentElement.dir).toBe("ltr")
  })
})
