import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"
import { createDefaultModel, executeSchemaSources, serializeModel, validateModel } from "../schema/adapter"
import { buildTrainingConfig, checkTrainingConfig, pickCarryOverFields, sanitizePersistedDraft } from "./params"
import { collectDatasetCheckTargets } from "./datasetCheck"
import { TRAINING_ENGINES, TRAINING_MODELS, isEngineSupported, moduleForTrainType, recommendedEngineFor, resolveModule } from "./modules"
import { engineDefinition } from "../engines/catalog"

const source = readFileSync(resolve(process.cwd(), "../mikazuki/schema/moss-image-anima-lora.ts"), "utf8")
const schema = executeSchemaSources([{ name: "moss-image-anima-lora", hash: "test", schema: source }], "moss-image-anima-lora")
const defaults = createDefaultModel(schema)
const kohyaSource = readFileSync(resolve(process.cwd(), "../mikazuki/schema/moss-image-lora.ts"), "utf8")
const sharedSource = readFileSync(resolve(process.cwd(), "../mikazuki/schema/shared.ts"), "utf8")
const kohyaSchema = executeSchemaSources([
  { name: "shared", hash: "test-shared", schema: sharedSource },
  { name: "moss-image-lora", hash: "test-kohya", schema: kohyaSource },
], "moss-image-lora")
const kohyaDefaults = createDefaultModel(kohyaSchema)

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
      model_train_type: "moss-image-anima-lora", model_input_mode: "native_directory",
      model_dir: "./sd-models/moss-image", model: "base",
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
    expect(output()).not.toHaveProperty("dit_path")
    expect(validateModel(schema, defaults)).toEqual({})
    expect(schema.sections).toHaveLength(7)
    expect(schema.sections.every(section => section.title.includes("/"))).toBe(true)
  })

  it("exposes Comfy single-file fields when model_input_mode is comfyui_files", () => {
    const model = {
      ...defaults, model_input_mode: "comfyui_files",
      dit_path: "/models/moss/dit.safetensors",
      text_encoder_path: "/models/moss/te.safetensors",
      vae_path: "/models/moss/vae.safetensors",
      tokenizer_path: "/models/moss/tokenizer",
      sft_dit_path: "/models/moss/sft.safetensors",
    }
    expect(validateModel(schema, model)).toEqual({})
    expect(output(model)).toMatchObject({
      model_input_mode: "comfyui_files",
      dit_path: "/models/moss/dit.safetensors",
      text_encoder_path: "/models/moss/te.safetensors",
      vae_path: "/models/moss/vae.safetensors",
      tokenizer_path: "/models/moss/tokenizer",
      sft_dit_path: "/models/moss/sft.safetensors",
    })
    expect(output(model)).not.toHaveProperty("model_dir")
    expect(validateModel(schema, { ...model, dit_path: "" })).toHaveProperty("dit_path")
  })

  it("preserves native overrides without Kohya network, optimizer or sample conversions", () => {
    const config = output({ model: "sft", src: "/数据/图片", cache_dir: "/缓存", rank: 32, alpha: 16,
      lr: 0.0002, compile: true, blocks_to_swap: -1, caption_dropout: 0.1,
      targets: "layers\\.0\\.proj\\.q", save_crops: true, overwrite_cache: true,
      network_module: "lycoris.kohya", network_dim: 99, optimizer_type: "Prodigy", sample_prompts: "unsupported" })
    expect(config).toMatchObject({ model: "sft", model_input_mode: "native_directory", src: "/数据/图片", cache_dir: "/缓存", rank: 32, alpha: 16,
      lr: 0.0002, compile: true, blocks_to_swap: -1, caption_dropout: 0.1,
      targets: "layers\\.0\\.proj\\.q", save_crops: true, overwrite_cache: true })
    for (const key of ["network_module", "network_dim", "network_args", "optimizer_type", "learning_rate", "sample_prompts", "enable_preview", "train_batch_size", "dataset_repeats", "dit_path"]) {
      expect(config).not.toHaveProperty(key)
    }
    expect(collectDatasetCheckTargets(config)).toEqual(["/数据/图片"])
    expect(buildTrainingConfig({ model_train_type: "anima-lora-fast", rank: 8 }, schema.name).model_train_type).toBe("moss-image-anima-lora")
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

  it("places dataset fields before resolution and exposes inline preview prompt", () => {
    const dataset = schema.sections.find((section) => section.title.includes("数据集"))
    expect(dataset).toBeTruthy()
    const keys = dataset!.fields.map((field) => field.key)
    expect(keys.indexOf("src")).toBeGreaterThanOrEqual(0)
    expect(keys.indexOf("resolution")).toBeGreaterThanOrEqual(0)
    expect(keys.indexOf("src")).toBeLessThan(keys.indexOf("resolution"))
    const preview = schema.sections.find((section) => section.title.includes("逐轮预览"))
    expect(preview?.fields.map((field) => field.key)).toEqual(expect.arrayContaining(["preview_prompt", "preview_prompt_file"]))
    expect(preview?.fields.find((field) => field.key === "preview_prompt")?.role).toBe("textarea")
    expect(output({ preview_prompt: "a moss preview caption", preview_every_epochs: 1 })).toMatchObject({
      preview_prompt: "a moss preview caption",
      preview_every_epochs: 1,
    })
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

describe("MOSS Kohya training schema", () => {
  it("keeps dataset early, .txt captions, cached outputs and textarea previews", () => {
    expect(kohyaDefaults).toMatchObject({
      model_train_type: "moss-image-lora",
      train_data_dir: "./train/moss-image",
      network_module: "networks.lora_generic",
      network_train_unet_only: true,
      caption_extension: ".txt",
      cache_latents: true,
      cache_latents_to_disk: true,
      cache_text_encoder_outputs: true,
      cache_text_encoder_outputs_to_disk: true,
    })
    const datasetIndex = kohyaSchema.sections.findIndex(section => section.title === "数据集设置")
    const saveIndex = kohyaSchema.sections.findIndex(section => section.title === "保存设置")
    expect(datasetIndex).toBeGreaterThanOrEqual(0)
    expect(datasetIndex).toBeLessThan(saveIndex)
    expect(kohyaSchema.sections.flatMap(section => section.fields).find(field => field.key === "positive_prompts")?.role).toBe("textarea")
    expect(kohyaSchema.sections.flatMap(section => section.fields).some(field => field.key === "fp8_base")).toBe(false)
  })
})

describe("MOSS module and runtime catalog", () => {
  it("prefers Kohya while retaining the anima_lora engine", () => {
    expect(resolveModule("moss-image", "kohya", "lora")?.schemaName).toBe("moss-image-lora")
    expect(resolveModule("moss-image", "moss", "lora")?.schemaName).toBe("moss-image-anima-lora")
    expect(resolveModule("moss-image", "moss", "finetune")).toBeUndefined()
    expect(moduleForTrainType("moss-image-lora")?.engine).toBe("kohya")
    expect(moduleForTrainType("moss-image-anima-lora")?.engine).toBe("moss")
    for (const model of TRAINING_MODELS) expect(isEngineSupported(model, "moss")).toBe(model === "moss-image")
    for (const engine of TRAINING_ENGINES) expect(isEngineSupported("moss-image", engine)).toBe(["kohya", "moss"].includes(engine))
    expect(recommendedEngineFor("moss-image")).toBe("kohya")
    expect(engineDefinition("moss")).toMatchObject({ kind: "optional", managesRuntime: true, requiresGpu: true })
  })
})
