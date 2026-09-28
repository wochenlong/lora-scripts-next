// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest"
import { LAST_TRAINING_SELECTION_KEY, readRecentTrainingSelection, writeRecentTrainingSelection } from "./recent"
import { writeEnginePrefs } from "../engines/prefs"

describe("recent training selection", () => {
  beforeEach(() => localStorage.clear())

  it("round-trips the last model, engine, and target", () => {
    const selection = { model: "qwen-image-21", engine: "diffsynth", target: "lora" } as const
    writeRecentTrainingSelection(selection)
    expect(readRecentTrainingSelection()).toEqual(selection)
    expect(localStorage.getItem(LAST_TRAINING_SELECTION_KEY)).toContain("qwen-image-21")
  })

  it("ignores malformed persisted values", () => {
    localStorage.setItem(LAST_TRAINING_SELECTION_KEY, JSON.stringify({ model: "qwen-image-21" }))
    expect(readRecentTrainingSelection()).toBeUndefined()
  })

  it("does not read or write the recent selection when remembering is disabled", () => {
    const selection = { model: "qwen-image-21", engine: "diffsynth", target: "lora" } as const
    localStorage.setItem(LAST_TRAINING_SELECTION_KEY, JSON.stringify(selection))
    writeEnginePrefs({ rememberLast: false, lastByModel: {} })

    expect(readRecentTrainingSelection()).toBeUndefined()
    writeRecentTrainingSelection({ model: "anima", engine: "anima-fast", target: "lora" })
    expect(JSON.parse(localStorage.getItem(LAST_TRAINING_SELECTION_KEY) || "null")).toEqual(selection)
  })
})
