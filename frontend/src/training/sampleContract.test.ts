import { describe, expect, it } from "vitest"
import { createSample, encodeSamples, decodeSamples, buildOptionalInputs } from "./sampleContract"

describe("optional training inputs contract", () => {
  it("round trips independent samples without limiting reference slots", () => {
    const first = createSample()
    first.controlImages = ["a.png", "b.png", "c.png", "d.png"]
    const second = { ...createSample(), prompt: "another", seed: 7 }
    expect(decodeSamples(encodeSamples([first, second]))).toEqual([first, second])
    expect(createSample().controlImages).toEqual([])
  })
  it("rejects malformed saved samples rather than silently dropping them", () => {
    expect(() => decodeSamples(["not json"])).toThrow()
    expect(() => decodeSamples(['{"prompt":3}'])).toThrow()
  })
  it("does not emit unimplemented or inactive capabilities", () => {
    const value = { training_task: "text-to-image" as const, control_data_dirs: ["old"],
      enable_preview: false, sample_every_n_steps: 10, preview_samples: encodeSamples([createSample()]) }
    expect(buildOptionalInputs(value, { editing: false, preview: false })).toEqual({})
    expect(() => buildOptionalInputs({ ...value, training_task: "image-edit" }, { editing: false, preview: false })).toThrow()
    expect(() => buildOptionalInputs({ ...value, enable_preview: true }, { editing: false, preview: false })).toThrow()
  })
  it("uses matching dataset and per-sample reference order", () => {
    const value = { training_task: "image-edit" as const, control_data_dirs: ["left", "right"],
      enable_preview: true, sample_every_n_steps: 10,
      preview_samples: encodeSamples([{ ...createSample(), controlImages: ["left.png", "right.png"] }]) }
    expect(buildOptionalInputs(value, { editing: true, preview: true })).toEqual(value)
  })
})
