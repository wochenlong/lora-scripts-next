// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest"
import { rememberSelection, writeEnginePrefs } from "../engines/prefs"
import { DEFAULT_SELECTION } from "./modules"
import { resolveInitialSelection } from "./selection"

const KEY = "nt.training.enginePrefs"

afterEach(() => {
  localStorage.removeItem(KEY)
})

describe("resolveInitialSelection", () => {
  it("falls back to the default selection with no query and no prefs", () => {
    expect(resolveInitialSelection({})).toEqual(DEFAULT_SELECTION)
  })

  it("restores the full last selection on a bare query", () => {
    rememberSelection("sdxl", "kohya", "lora")
    expect(resolveInitialSelection({})).toEqual({ model: "sdxl", engine: "kohya", target: "lora" })
  })

  it("prefers an explicit query over the remembered selection", () => {
    rememberSelection("sdxl", "kohya", "lora")
    expect(resolveInitialSelection({ model: "flux", engine: "kohya", target: "lora" })).toEqual({ model: "flux", engine: "kohya", target: "lora" })
  })

  it("prefers a schema query over everything else", () => {
    rememberSelection("sdxl", "kohya", "lora")
    expect(resolveInitialSelection({ schema: "lumina2-lora", model: "flux" })).toEqual({ model: "lumina", engine: "kohya", target: "lora" })
  })

  it("drops a remembered engine unsupported by the remembered model", () => {
    writeEnginePrefs({ rememberLast: true, last: { model: "flux", engine: "anima-fast", target: "lora" } })
    expect(resolveInitialSelection({})).toEqual({ model: "flux", engine: "kohya", target: "lora" })
  })

  it("ignores an unknown remembered model", () => {
    writeEnginePrefs({ rememberLast: true, last: { model: "nope", engine: "kohya", target: "lora" } })
    expect(resolveInitialSelection({})).toEqual(DEFAULT_SELECTION)
  })

  it("restores per-model engine/target when only legacy lastByModel exists", () => {
    writeEnginePrefs({ rememberLast: true, lastByModel: { anima: { engine: "anima-fast", target: "lora" } } })
    expect(resolveInitialSelection({})).toEqual({ model: "anima", engine: "anima-fast", target: "lora" })
  })

  it("restores nothing when rememberLast is disabled", () => {
    writeEnginePrefs({ rememberLast: false, last: { model: "sdxl", engine: "kohya", target: "lora" } })
    expect(resolveInitialSelection({})).toEqual(DEFAULT_SELECTION)
  })
})
