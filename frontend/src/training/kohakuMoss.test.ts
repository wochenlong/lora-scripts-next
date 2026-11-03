import { describe, expect, it } from "vitest"
import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { createDefaultModel, executeSchemaSources, serializeModel, validateModel } from "../schema/adapter"
import { buildTrainingConfig, hydrateImportedConfig, pickCarryOverFields } from "./params"
import type { FormModel } from "../schema/adapter"
import { DEFAULT_SELECTION, idealEngineFor, resolveModule } from "./modules"

const name = "kohaku-moss-image-lora"
const schema = executeSchemaSources([{ name, hash: "test", schema: readFileSync(resolve(process.cwd(), `../mikazuki/schema/${name}.ts`), "utf8") }], name)
const defaults = createDefaultModel(schema)

describe("Kohaku parameter contract", () => {
  it("preserves existing defaults and provides an explicit optional engine", () => {
    expect(DEFAULT_SELECTION).toEqual({ model: "anima", engine: "kohya", target: "lora" })
    expect(idealEngineFor("moss-image")).toBe("kohya")
    expect(resolveModule("moss-image", "kohaku-moss", "lora")?.schemaName).toBe(name)
  })
  it("serializes defaults through the real schema without Kohya conversion", () => {
    expect(validateModel(schema, defaults)).toEqual({})
    const config = buildTrainingConfig(serializeModel(schema, defaults), name)
    expect(config).toMatchObject({ model_train_type: name, network_algorithm: "lokr", network_dim: 32, learning_rate: 0.0001, mixed_precision: "bf16", parallel_mode: "none" })
    expect(config).not.toHaveProperty("fp8_recipe")
    expect(config).not.toHaveProperty("network_module")
    expect(config).not.toHaveProperty("ia3_train_on_input")
  })
  it("selects only active algorithm and model path fields", () => {
    const config = buildTrainingConfig(serializeModel(schema, { ...defaults, network_algorithm: "ia3", model_input_mode: "native_directory", base_precision: "fp8", fp8_recipe: "tensor" }), name)
    expect(config).toMatchObject({ ia3_train_on_input: false, fp8_recipe: "tensor", pretrained_model_name_or_path: "./sd-models/moss-image" })
    for (const key of ["network_dim", "network_alpha", "lokr_factor", "dit_path", "text_encoder_path", "vae_path", "tokenizer_path"]) expect(config).not.toHaveProperty(key)
  })
  it("preserves numeric learning rate across import and GPU list serialization", () => {
    const config = buildTrainingConfig({ ...hydrateImportedConfig({ model_train_type: name, learning_rate: 0.00002 }), gpu_ids: ["GPU 0: NVIDIA", "2"] }, name)
    expect(config).toMatchObject({ learning_rate: 0.00002, gpu_ids: ["0", "2"] })
  })
  it("does not leak Kohya defaults into Kohaku", () => {
    expect(pickCarryOverFields({ model_train_type: "moss-image-lora", optimizer_type: "AdamW8bit", network_dim: 16, learning_rate: "1e-4", train_data_dir: "./custom" }, defaults)).toEqual({ train_data_dir: "./custom" })
  })
})

describe("Kohaku precision and pipeline fields", () => {
  it("serializes only the active companion parameters", () => {
    const serialize = (values: FormModel) => buildTrainingConfig(serializeModel(schema, { ...defaults, ...values }), name)
    expect(serialize({ mixed_precision: "fp16" })).toMatchObject({ fp16_fix: "online" })
    expect(serialize({ mixed_precision: "auto", fp16_fix: "none" })).toMatchObject({ fp16_fix: "none" })
    expect(serialize({ parallel_mode: "pipeline" })).toMatchObject({ pipeline_schedule: "auto", microbatches: 4 })
    expect(serialize({ parallel_mode: "threaded", pipeline_schedule: "async" })).toMatchObject({ pipeline_schedule: "async", microbatches: 4 })
    const ordinary = serialize({ mixed_precision: "bf16", fp16_fix: "online", parallel_mode: "none", pipeline_schedule: "async", microbatches: 8 })
    for (const field of ["fp16_fix", "pipeline_schedule", "microbatches"]) expect(ordinary).not.toHaveProperty(field)
  })
})
