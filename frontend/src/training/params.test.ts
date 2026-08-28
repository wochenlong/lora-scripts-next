import { describe, expect, it } from "vitest"
import { reactive } from "vue"
import {
  buildTrainingConfig,
  checkTrainingConfig,
  hydrateImportedConfig,
  pickCarryOverFields,
  sanitizePersistedDraft,
} from "./params"

describe("training parameter conversion", () => {
  it("fills basic defaults and normalizes paths and GPU ids", () => {
    const result = buildTrainingConfig({
      pretrained_model_name_or_path: "D:\\models\\base.safetensors",
      train_data_dir: "D:\\train",
      gpu_ids: ["GPU 1: RTX", 2],
    }, "lora-basic")
    expect(result).toMatchObject({
      model_train_type: "sd-lora",
      network_module: "networks.lora",
      pretrained_model_name_or_path: "D:/models/base.safetensors",
      train_data_dir: "D:/train",
      gpu_ids: ["1", "2"],
    })
  })

  it("preserves expert and Flux page identity fields", () => {
    expect(buildTrainingConfig({
      model_train_type: "sdxl-lora",
      network_module: "networks.lora",
    }, "lora-master")).toMatchObject({
      model_train_type: "sdxl-lora",
      network_module: "networks.lora",
    })

    expect(buildTrainingConfig({
      model_train_type: "flux-lora",
      model_type: "flux",
      network_module: "networks.lora_flux",
    }, "flux-lora")).toMatchObject({
      model_train_type: "flux-lora",
      model_type: "flux",
      network_module: "networks.lora_flux",
    })
  })

  it("forces anima-lora-fast train type even when form still has Kohya anima-lora (#271)", () => {
    expect(buildTrainingConfig({
      model_train_type: "anima-lora",
      cache_latents: true,
      pretrained_model_name_or_path: "./sd-models/anima/anima-base-v1.0.safetensors",
    }, "anima-lora-fast")).toMatchObject({
      model_train_type: "anima-lora-fast",
    })
  })

  it("converts Vue reactive form models", () => {
    const result = buildTrainingConfig(reactive({
      model_train_type: "sdxl-lora",
      gpu_ids: ["GPU 0: RTX"],
    }), "lora-master")
    expect(result.gpu_ids).toEqual(["0"])
  })

  it("converts LyCORIS fields and custom arguments", () => {
    const result = buildTrainingConfig({
      model_train_type: "sdxl-lora",
      network_module: "lycoris.kohya",
      lycoris_algo: "lokr",
      conv_dim: 4,
      conv_alpha: 1,
      dropout: 0,
      lokr_factor: 8,
      train_norm: true,
      network_args_custom: ["custom=1"],
    }, "lora-master")
    expect(result.network_args).toEqual(["conv_dim=4", "conv_alpha=1", "dropout=0", "algo=lokr", "factor=8", "train_norm=True", "custom=1"])
    expect(result).not.toHaveProperty("lycoris_algo")
  })

  it("detects conflicting training options", () => {
    expect(checkTrainingConfig({ cache_latents: true, color_aug: true }).errors).toContain("参数 cache_latents 与 color_aug 冲突，请只启用其中一个")
  })

  it("hydrates canonical argument lists for the GUI", () => {
    expect(hydrateImportedConfig({ network_args: ["algo=loha", "factor=4"], optimizer_args: ["weight_decay=0.1"] })).toMatchObject({
      lycoris_algo: "loha",
      factor: "4",
      optimizer_args_custom: ["weight_decay=0.1"],
    })
  })
})

describe("cross-schema carry-over (#271)", () => {
  it("keeps paths but drops train type and cache flags from Kohya when entering Fast defaults", () => {
    const defaults = {
      model_train_type: "anima-lora-fast",
      pretrained_model_name_or_path: "./sd-models/anima/anima-base-v1.0.safetensors",
      train_data_dir: "./data",
      cache_latents: false,
      cache_text_encoder_outputs: false,
      learning_rate: 1e-4,
    }
    const carry = {
      model_train_type: "anima-lora",
      pretrained_model_name_or_path: "./sd-models/anima/custom.safetensors",
      train_data_dir: "./data/oc",
      cache_latents: true,
      cache_latents_to_disk: true,
      cache_text_encoder_outputs: true,
      cache_text_encoder_outputs_to_disk: true,
      network_module: "networks.lora_anima",
      learning_rate: 2e-4,
    }
    expect(pickCarryOverFields(carry, defaults)).toEqual({
      pretrained_model_name_or_path: "./sd-models/anima/custom.safetensors",
      train_data_dir: "./data/oc",
      learning_rate: 2e-4,
    })
  })

  it("denies engine-specific DiT paths from crossing schema boundaries", () => {
    const defaults = { dit: "./sd-models/klein/flux2-klein-base-4b", train_data_dir: "./train/aki" }
    const carry = { dit: "./sd-models/krea2/krea2.safetensors", train_data_dir: "./data/oc" }
    expect(pickCarryOverFields(carry, defaults)).toEqual({ train_data_dir: "./data/oc" })
  })

  it("strips denied keys from poisoned autosave when train type mismatches schema defaults", () => {
    const defaults = { model_train_type: "anima-lora-fast", cache_latents: false }
    const saved = {
      model_train_type: "anima-lora",
      cache_latents: true,
      train_data_dir: "./data/oc",
    }
    expect(sanitizePersistedDraft(saved, defaults)).toEqual({
      train_data_dir: "./data/oc",
    })
  })

  it("keeps matching autosave drafts intact", () => {
    const defaults = { model_train_type: "anima-lora-fast", cache_latents: false }
    const saved = {
      model_train_type: "anima-lora-fast",
      cache_latents: true,
      train_data_dir: "./data/oc",
    }
    expect(sanitizePersistedDraft(saved, defaults)).toEqual(saved)
  })
})
