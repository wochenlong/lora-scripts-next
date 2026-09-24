// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest"
import { UI_CONFIGS_KEY } from "../i18n"
import {
  readPathPickerPreference,
  writePathPickerPreference,
} from "./pathPickerPreference"

describe("path picker preference", () => {
  beforeEach(() => localStorage.clear())

  it("defaults to auto when no preference is stored", () => {
    expect(readPathPickerPreference()).toBe("auto")
  })

  it.each(["auto", "native", "web"] as const)("reads the stored %s preference", (value) => {
    localStorage.setItem(UI_CONFIGS_KEY, JSON.stringify({ path_picker: value }))

    expect(readPathPickerPreference()).toBe(value)
  })

  it("defaults to auto for malformed or invalid settings", () => {
    localStorage.setItem(UI_CONFIGS_KEY, "{broken")
    expect(readPathPickerPreference()).toBe("auto")

    localStorage.setItem(UI_CONFIGS_KEY, JSON.stringify({ path_picker: "desktop" }))
    expect(readPathPickerPreference()).toBe("auto")
  })

  it("preserves unrelated UI settings when writing", () => {
    localStorage.setItem(UI_CONFIGS_KEY, JSON.stringify({ language: "en-US", tensorboard_url: "http://localhost:6006" }))

    writePathPickerPreference("web")

    expect(JSON.parse(localStorage.getItem(UI_CONFIGS_KEY) || "{}")).toEqual({
      language: "en-US",
      tensorboard_url: "http://localhost:6006",
      path_picker: "web",
    })
  })
})
