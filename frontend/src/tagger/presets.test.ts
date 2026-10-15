import { expect, it } from "vitest"
import { presetForTask, taskForModel, TAGGER_PRESETS } from "./presets"

it("keeps distinct recommended models per tagging task", () => {
  const models = Object.values(TAGGER_PRESETS).map((preset) => preset.model)
  expect(new Set(models).size).toBe(models.length)
  expect(presetForTask("character").characterThreshold).toBeLessThan(presetForTask("style").characterThreshold)
})

it("maps a recommended model back to its task", () => {
  expect(taskForModel(TAGGER_PRESETS.general.model)).toBe("general")
  expect(taskForModel("not-a-model")).toBeUndefined()
})
