import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"
import { createDefaultModel, executeSchemaSources, serializeModel } from "../schema/adapter"
import { createSample, encodeSamples } from "./sampleContract"
import { buildTrainingConfig } from "./params"

const source = readFileSync(resolve(process.cwd(), "../mikazuki/schema/qwen-image-21-lora.ts"), "utf8")
const schema = executeSchemaSources([{ name: "qwen-image-21-lora", hash: "test", schema: source }], "qwen-image-21-lora")

describe("DiffSynth schema uses shared serialization", () => {
  it("preserves the shared Sample contract through the actual training form", () => {
    const preview_samples = encodeSamples([{ ...createSample(), prompt: "中文", seed: 123 }])
    const model = { ...createDefaultModel(schema), sample_enabled: true, preview_samples }
    const config = buildTrainingConfig(serializeModel(schema, model), "qwen-image-21-lora")
    expect(config.preview_samples).toEqual(preview_samples)
    expect(config.sample_enabled).toBe(true)
    const field = schema.sections.flatMap(section => section.fields).find(field => field.key === "preview_samples")!
    expect(field.extra).toMatchObject({ dimensionStep: 32, minGuidance: 1 })
  })

  it("serializes only selected modes and preserves structured samples", () => {
    const model = { ...createDefaultModel(schema), model_input_mode: "components", dataset_format: "metadata", sample_enabled: true,
      dit_path: "/模型/dit.safetensors", text_encoder_path: "/模型/te.safetensors", vae_path: "/模型/vae.safetensors",
      diffsynth_model_dir: "/unused", train_data_dir: "/unused", dataset_repeat: 99,
      dataset_base_path: "/images", dataset_metadata_path: "/images/data.csv",
      preview_samples: [JSON.stringify({ prompt: "中文", width: 512, height: 768, seed: 8, guidance_scale: 4, sample_steps: 20 })] }
    const config = buildTrainingConfig(serializeModel(schema, model), "qwen-image-21-lora")
    expect(config).toMatchObject({ model_input_mode: "components", dataset_format: "metadata", preview_samples: model.preview_samples })
    expect(config).not.toHaveProperty("dataset_repeat")
    expect(config).not.toHaveProperty("train_data_dir")
    expect(config).not.toHaveProperty("diffsynth_model_dir")
    expect(config).not.toHaveProperty("sample_prompts")
    model.model_input_mode = "directory"
    model.dataset_format = "image_text"
    model.sample_enabled = false
    const switched = buildTrainingConfig(serializeModel(schema, model), "qwen-image-21-lora")
    expect(switched).toHaveProperty("diffsynth_model_dir", "/unused")
    expect(switched).not.toHaveProperty("dit_path")
    expect(switched).not.toHaveProperty("preview_samples")
    expect(switched).not.toHaveProperty("dataset_metadata_path")
  })
})
