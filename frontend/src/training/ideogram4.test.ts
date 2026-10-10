import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"
import { createDefaultModel, executeSchemaSources } from "../schema/adapter"
import { buildTrainingConfig, pickCarryOverFields } from "./params"

const source = readFileSync(resolve(process.cwd(), "../mikazuki/schema/ideogram4-lora.ts"), "utf8")
const schema = executeSchemaSources([{ name: "ideogram4-lora", hash: "test", schema: source }], "ideogram4-lora")

describe("Ideogram 4 schema defaults", () => {
  it("points at the FP8 quantized components", () => {
    expect(createDefaultModel(schema)).toMatchObject({
      model_train_type: "ideogram4-lora",
      dit: "./sd-models/ideogram4/ideogram4_fp8_scaled.safetensors",
      text_encoder: "./sd-models/ideogram4/qwen3vl_8b_fp8_scaled.safetensors",
      vae: "./sd-models/ideogram4/flux2-vae.safetensors",
      output_name: "next-ideogram4-lora",
      resolution: "1024,1024",
    })
  })

  it("uses the official sampler and precision defaults", () => {
    expect(createDefaultModel(schema)).toMatchObject({
      timestep_sampling: "ideogram4_shift",
      sampler_preset: "V4_DEFAULT_20",
      initial_sigma: 1.004,
      sample_cfg: 7,
      mixed_precision: "bf16",
      dit_dtype: "bfloat16",
      text_cache_dtype: "bf16",
      blocks_to_swap: 0,
      network_dim: 32,
      network_alpha: 32,
      use_unconditional_dit_for_lora_sampling: false,
    })
  })

  it("keeps Krea 2 only switches out of the form", () => {
    const model = createDefaultModel(schema)
    for (const key of ["turbo_dit", "turbo_dit_cache", "fp8_base", "fp8_scaled", "weighting_scheme"]) {
      expect(model).not.toHaveProperty(key)
    }
  })
})

describe("Ideogram 4 config serialization", () => {
  it("locks the train type and carries the sampler defaults", () => {
    const model = { ...createDefaultModel(schema), model_train_type: "krea2-lora" }
    const config = buildTrainingConfig(model, "ideogram4-lora")

    expect(config.model_train_type).toBe("ideogram4-lora")
    expect(config.sampler_preset).toBe("V4_DEFAULT_20")
    expect(config.sample_cfg).toBe(7)
    expect(config).not.toHaveProperty("fp8_base")
  })

  it("does not inherit Krea 2 model paths when switching pages", () => {
    const defaults = createDefaultModel(schema)
    const carried = pickCarryOverFields(
      {
        dit: "./sd-models/krea2/krea2.safetensors",
        vae: "./sd-models/krea2/qwen_image_vae.safetensors",
        text_encoder: "./sd-models/krea2/qwen3_vl_4b.safetensors",
        fp8_base: true,
        fp8_scaled: true,
        learning_rate: "2e-4",
      },
      defaults,
    )

    expect(carried.learning_rate).toBe("2e-4")
    for (const key of ["dit", "vae", "text_encoder", "fp8_base", "fp8_scaled"]) {
      expect(carried).not.toHaveProperty(key)
    }
  })

  it("still carries an external VAE between kohya pages", () => {
    const kohyaDefaults = { model_train_type: "sdxl-lora", vae: "", fp8_base: false }
    const carried = pickCarryOverFields(
      { vae: "./models/vae.safetensors", fp8_base: true, learning_rate: "2e-4" },
      kohyaDefaults,
    )

    expect(carried.vae).toBe("./models/vae.safetensors")
    expect(carried.fp8_base).toBe(true)
  })
})
