import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"
import { createDefaultModel, executeSchemaSources, serializeModel, validateModel } from "../schema/adapter"
import { buildTrainingConfig, checkTrainingConfig, pickCarryOverFields, sanitizePersistedDraft } from "./params"
import { collectDatasetCheckTargets } from "./datasetCheck"
import { TRAINING_ENGINES, TRAINING_MODELS, isEngineSupported, moduleForTrainType, recommendedEngineFor, resolveModule } from "./modules"
import { engineDefinition } from "../engines/catalog"

const source = readFileSync(resolve(process.cwd(), "../mikazuki/schema/moss-image-lora.ts"), "utf8")
const schema = executeSchemaSources([{ name: "moss-image-lora", hash: "test", schema: source }], "moss-image-lora")
const defaults = createDefaultModel(schema)

function output(overrides = {}) {
  return buildTrainingConfig(serializeModel(schema, { ...defaults, ...overrides }), schema.name)
}

describe("MOSS native training schema", () => {
  it("matches the shared real-form submission fixture consumed by backend API tests", () => {
    const fixture = JSON.parse(readFileSync(resolve(process.cwd(), "../tests/fixtures/moss/form-submission.json"), "utf8"))
    const submitted = output({
      model_dir: "models/moss_image", src: "images", cache_dir: "output/moss/cache",
      output_dir: "output/moss/lora", output_name: "moss-fixture",
      epochs: 3, max_steps: 12, rank: 8, alpha: 8, lr: 0.0002, save_every_epochs: 1,
      caption_dropout: 0.1, blocks_to_swap: 2, seed: 123, max_text_tokens: 512, save_crops: true,
    })
    expect(submitted).toEqual(fixture)
  })

  it("uses native MOSS fields and conservative defaults through the actual serializer", () => {
    expect(output()).toMatchObject({
      model_train_type: "moss-image-lora", model_dir: "./sd-models/moss-image", model: "base",
      src: "./train/moss-image", resolution: 1024, run_preprocess: true, overwrite_cache: false,
      output_dir: "./output/moss", output_name: "moss-image-lora", epochs: 8, max_steps: 0,
      rank: 16, lr: 1e-4, warmup_ratio: 0.05, save_every_epochs: 0, caption_dropout: 0,
      lora_dtype: "bf16", grad_checkpointing: true, blocks_to_swap: 0, compile: false,
      log_every: 10, seed: 0, sigma_mu: -1.09, sigma_s: 0.95, sigma_cutoff: 0.95,
      sigma_uniform: 0.01, max_grad_norm: 1, vae_dtype: "fp32", max_text_tokens: 4096, save_crops: false,
      targets: "layers\\.\\d+\\.proj\\.(q|k|v|o|ffn_up_gate|ffn_down)",
    })
    expect(output()).not.toHaveProperty("alpha")
    expect(output()).not.toHaveProperty("cache_dir")
    expect(validateModel(schema, defaults)).toEqual({})
    expect(schema.sections).toHaveLength(7)
    expect(schema.sections.every(section => section.title.includes("/"))).toBe(true)
  })

  it("preserves native overrides without Kohya network, optimizer or sample conversions", () => {
    const config = output({ model: "sft", src: "/数据/图片", cache_dir: "/缓存", rank: 32, alpha: 16,
      lr: 0.0002, compile: true, blocks_to_swap: -1, caption_dropout: 0.1,
      targets: "layers\\.0\\.proj\\.q", save_crops: true, overwrite_cache: true,
      network_module: "lycoris.kohya", network_dim: 99, optimizer_type: "Prodigy", sample_prompts: "unsupported" })
    expect(config).toMatchObject({ model: "sft", src: "/数据/图片", cache_dir: "/缓存", rank: 32, alpha: 16,
      lr: 0.0002, compile: true, blocks_to_swap: -1, caption_dropout: 0.1,
      targets: "layers\\.0\\.proj\\.q", save_crops: true, overwrite_cache: true })
    for (const key of ["network_module", "network_dim", "network_args", "optimizer_type", "learning_rate", "sample_prompts", "enable_preview", "train_batch_size", "dataset_repeats", "dit_path", "model_input_mode"]) {
      expect(config).not.toHaveProperty(key)
    }
    expect(collectDatasetCheckTargets(config)).toEqual(["/数据/图片"])
    expect(buildTrainingConfig({ model_train_type: "anima-lora-fast", rank: 8 }, schema.name).model_train_type).toBe("moss-image-lora")
  })

  it("switches between preprocessing and existing-cache mode without leaking the source", () => {
    expect(validateModel(schema, { ...defaults, src: "" })).toHaveProperty("src")
    expect(validateModel(schema, { ...defaults, run_preprocess: false, cache_dir: "" })).toHaveProperty("cache_dir")
    const config = output({ run_preprocess: false, cache_dir: "/existing/moss-cache" })
    expect(config).toMatchObject({ run_preprocess: false, cache_dir: "/existing/moss-cache" })
    expect(config).not.toHaveProperty("src")
    expect(collectDatasetCheckTargets(config)).toEqual([])
    expect(output({ run_preprocess: true, src: "/source" })).toHaveProperty("src", "/source")
  })

  it("checks block-swap range and epoch/step termination", () => {
    expect(validateModel(schema, { ...defaults, rank: 3073 })).toHaveProperty("rank")
    expect(validateModel(schema, { ...defaults, resolution: 4097 })).toHaveProperty("resolution")
    expect(validateModel(schema, { ...defaults, resolution: 1000 })).not.toHaveProperty("resolution")
    expect(validateModel(schema, { ...defaults, max_grad_norm: 0 })).toHaveProperty("max_grad_norm")
    expect(validateModel(schema, { ...defaults, blocks_to_swap: 41 })).toHaveProperty("blocks_to_swap")
    expect(validateModel(schema, { ...defaults, blocks_to_swap: -2 })).toHaveProperty("blocks_to_swap")
    expect(validateModel(schema, { ...defaults, blocks_to_swap: -1 })).not.toHaveProperty("blocks_to_swap")
    expect(checkTrainingConfig(output({ epochs: 0, max_steps: 0 })).errors).toHaveLength(1)
    expect(checkTrainingConfig(output({ epochs: 0, max_steps: 100 })).errors).toEqual([])
    const singleGpu = buildTrainingConfig({ ...defaults, gpu_ids: ["GPU 2: Test card"] }, schema.name)
    expect(singleGpu.gpu_ids).toEqual(["2"])
    expect(checkTrainingConfig(singleGpu).errors).toEqual([])
    expect(checkTrainingConfig({ ...singleGpu, gpu_ids: ["0", "1"] }).errors).toHaveLength(1)
    expect(schema.sections.flatMap(section => section.fields).find(field => field.key === "resolution")?.type).toBe("number")
  })

  it("keeps MOSS assets and cache switches isolated from cross-schema drafts", () => {
    const carry = { ...defaults, resolution: "1024,1024", model_dir: "/wrong", cache_dir: "/wrong-cache", model: "sft", run_preprocess: false }
    expect(pickCarryOverFields(carry, defaults)).not.toHaveProperty("model_dir")
    expect(pickCarryOverFields(carry, defaults)).not.toHaveProperty("resolution")
    expect(pickCarryOverFields(defaults, { model_train_type: "anima-lora-fast", resolution: "1024,1024" })).not.toHaveProperty("resolution")
    const saved = sanitizePersistedDraft({ ...carry, model_train_type: "anima-lora-fast" }, defaults)
    for (const key of ["model_train_type", "model_dir", "model", "cache_dir", "run_preprocess", "overwrite_cache"]) expect(saved).not.toHaveProperty(key)
  })
})

describe("MOSS module and runtime catalog", () => {
  it("supports only MOSS-Image LoRA, separate from Anima and all other engines", () => {
    expect(resolveModule("moss-image", "moss", "lora")?.schemaName).toBe("moss-image-lora")
    expect(resolveModule("moss-image", "moss", "finetune")).toBeUndefined()
    expect(moduleForTrainType("moss-image-lora")?.engine).toBe("moss")
    for (const model of TRAINING_MODELS) expect(isEngineSupported(model, "moss")).toBe(model === "moss-image")
    for (const engine of TRAINING_ENGINES) expect(isEngineSupported("moss-image", engine)).toBe(engine === "moss")
    expect(recommendedEngineFor("moss-image")).toBe("moss")
    expect(engineDefinition("moss")).toMatchObject({ kind: "optional", managesRuntime: true, requiresGpu: true })
  })
})
