// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest"
import { lastSelectionFor, readEnginePrefs, rememberSelection, writeEnginePrefs } from "./prefs"

const KEY = "nt.training.enginePrefs"

afterEach(() => {
  localStorage.removeItem(KEY)
})

describe("engine prefs", () => {
  it("defaults rememberLast to true", () => {
    expect(readEnginePrefs().rememberLast).toBe(true)
  })

  it("remembers last engine per model when enabled", () => {
    rememberSelection("anima", "anima-fast", "lora")
    expect(lastSelectionFor("anima")).toEqual({ engine: "anima-fast", target: "lora" })
  })

  it("does not remember when disabled", () => {
    writeEnginePrefs({ rememberLast: false, lastByModel: {} })
    rememberSelection("anima", "anima-fast", "lora")
    expect(lastSelectionFor("anima")).toBeUndefined()
  })
})
