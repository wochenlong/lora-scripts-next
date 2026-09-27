// GUI storage follows Klein's JSON-string array. Engine adapters decode it.
export interface PreviewSample {
  prompt: string
  controlImages: string[]
  width: number
  height: number
  seed: number
  guidance_scale: number
  sample_steps: number
}

export function createSample(): PreviewSample {
  return { prompt: "", controlImages: [], width: 1024, height: 1024, seed: 42, guidance_scale: 4, sample_steps: 20 }
}

export function decodeSamples(values: string[]): PreviewSample[] {
  return values.map(value => {
    const parsed = JSON.parse(value)
    if (!parsed || typeof parsed.prompt !== "string") throw new Error("Invalid Sample prompt")
    const sample = { ...createSample(), ...parsed } as PreviewSample
    if (!Array.isArray(sample.controlImages) || sample.controlImages.some(path => typeof path !== "string")) throw new Error("Invalid reference images")
    for (const key of ["width", "height", "sample_steps"] as const) {
      if (!Number.isInteger(sample[key]) || sample[key] <= 0) throw new Error(`Invalid Sample ${key}`)
    }
    if (!Number.isSafeInteger(sample.seed) || sample.seed < 0) throw new Error("Invalid Sample seed")
    if (!Number.isFinite(sample.guidance_scale) || sample.guidance_scale < 0) throw new Error("Invalid Sample CFG")
    return sample
  })
}

export function encodeSamples(samples: PreviewSample[]): string[] {
  return samples.map(sample => JSON.stringify(sample))
}

export interface OptionalTrainingInputs {
  training_task: "text-to-image" | "image-edit"
  control_data_dirs: string[]
  enable_preview: boolean
  sample_every_n_steps: number
  preview_samples: string[]
}

export function buildOptionalInputs(value: OptionalTrainingInputs, capabilities: { editing: boolean; preview: boolean }) {
  const output: Partial<OptionalTrainingInputs> = {}
  if (value.training_task === "image-edit") {
    if (!capabilities.editing) throw new Error("Image editing is not supported by this backend")
    if (!value.control_data_dirs.length || value.control_data_dirs.some(path => !path.trim())) throw new Error("Reference directories are required")
    output.training_task = value.training_task
    output.control_data_dirs = [...value.control_data_dirs]
  }
  if (value.enable_preview) {
    if (!capabilities.preview) throw new Error("Training preview is not supported by this backend")
    if (!Number.isInteger(value.sample_every_n_steps) || value.sample_every_n_steps < 1) throw new Error("Invalid preview interval")
    const samples = decodeSamples(value.preview_samples)
    if (!samples.length) throw new Error("At least one Sample is required")
    if (value.training_task === "text-to-image" && samples.some(sample => sample.controlImages.length)) throw new Error("Text-to-image Samples cannot contain reference images")
    output.enable_preview = true
    output.sample_every_n_steps = value.sample_every_n_steps
    output.preview_samples = encodeSamples(samples)
  }
  return output
}
