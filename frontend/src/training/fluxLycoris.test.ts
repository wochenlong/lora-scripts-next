import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"
import {
  applyReadonlyDefaults,
  cloneFormModel,
  createDefaultModel,
  executeSchemaSources,
  normalizeModelForSchema,
  serializeModel,
  type FormModel,
} from "../schema/adapter"
import {
  buildTrainingConfig,
  hasExplicitFluxLoraType,
  hydrateImportedConfig,
  migrateFluxLoraType,
} from "./params"

function loadSchema(name: string) {
  const read = (file: string) => readFileSync(resolve(process.cwd(), `../mikazuki/schema/${file}.ts`), "utf8")
  return executeSchemaSources(
    [
      { name: "shared", hash: "test", schema: read("shared") },
      { name, hash: "test", schema: read(name) },
    ],
    name,
  )
}

const schema = loadSchema("flux-lora")

function formModel(patch: FormModel = {}) {
  const defaults = createDefaultModel(schema)
  const model = { ...cloneFormModel(defaults), ...patch }
  applyReadonlyDefaults(schema, model, defaults)
  return model
}

function exportedConfig(model: FormModel) {
  return buildTrainingConfig(serializeModel(schema, model), "flux-lora")
}

function importIntoForm(config: FormModel, hasExplicitLoraType = hasExplicitFluxLoraType(config)) {
  const defaults = createDefaultModel(schema)
  const explicitKeys = new Set(Object.keys(config))
  const imported = hydrateImportedConfig(cloneFormModel(config))
  const migrated = migrateFluxLoraType(imported, hasExplicitLoraType)
  const model = normalizeModelForSchema(schema, { ...cloneFormModel(defaults), ...migrated }, { explicitKeys })
  applyReadonlyDefaults(schema, model, defaults)
  return model
}

describe("Flux LyCORIS adapter types", () => {
  it("keeps plain Flux LoRA as the default", () => {
    const config = exportedConfig(formModel())

    expect(config.model_train_type).toBe("flux-lora")
    expect(config.network_module).toBe("networks.lora_flux")
    expect(config.fp8_base).toBe(true)
    expect(config).not.toHaveProperty("lora_type")
    expect(config).not.toHaveProperty("network_args")
  })

  it("maps LoKr to LyCORIS without submitting the UI discriminator", () => {
    const config = exportedConfig(formModel({ lora_type: "lokr", lokr_factor: 16, network_dim: 8, network_alpha: 4 }))

    expect(config.network_module).toBe("lycoris.kohya")
    expect(config.fp8_base).toBe(false)
    expect(config.network_args).toEqual(["conv_dim=4", "conv_alpha=1", "dropout=0", "algo=lokr", "factor=16"])
    expect(config).not.toHaveProperty("lora_type")
    expect(config).not.toHaveProperty("lycoris_algo")
    expect(config).not.toHaveProperty("lokr_factor")
  })

  it("maps LoHa without LoKr-only arguments", () => {
    const config = exportedConfig(formModel({ lora_type: "loha", lokr_factor: 16 }))

    expect(config.network_module).toBe("lycoris.kohya")
    expect(config.fp8_base).toBe(false)
    expect(config.network_args).toEqual(["conv_dim=4", "conv_alpha=1", "dropout=0", "algo=loha"])
    expect(config).not.toHaveProperty("lora_type")
  })

  it("clears managed LyCORIS arguments when switching first-class types", () => {
    const loha = formModel({ lora_type: "lokr", lokr_factor: 16 })
    loha.lora_type = "loha"
    applyReadonlyDefaults(schema, loha, createDefaultModel(schema))
    const lohaConfig = exportedConfig(loha)
    expect(lohaConfig.network_args).toEqual(expect.arrayContaining(["algo=loha"]))
    expect(lohaConfig.network_args).not.toEqual(expect.arrayContaining(["factor=16"]))

    const lora = formModel({ lora_type: "lokr", lokr_factor: 16 })
    lora.lora_type = "lora"
    applyReadonlyDefaults(schema, lora, createDefaultModel(schema))
    const loraConfig = exportedConfig(lora)
    expect(loraConfig.network_module).toBe("networks.lora_flux")
    expect(loraConfig).not.toHaveProperty("network_args")
  })

  it("preserves advanced LyCORIS algorithms through custom", () => {
    const config = exportedConfig(formModel({
      lora_type: "custom",
      network_module: "lycoris.kohya",
      lycoris_algo: "locon",
      conv_dim: 8,
      conv_alpha: 4,
      dropout: 0.1,
      train_norm: true,
    }))

    expect(config.network_module).toBe("lycoris.kohya")
    expect(config.fp8_base).toBe(false)
    expect(config.network_args).toEqual(expect.arrayContaining(["algo=locon", "conv_dim=8", "conv_alpha=4", "dropout=0.1", "train_norm=True"]))
  })

  it("preserves the existing OFT path through custom", () => {
    const config = exportedConfig(formModel({ lora_type: "custom", network_module: "networks.oft_flux" }))

    expect(config.network_module).toBe("networks.oft_flux")
    expect(config).not.toHaveProperty("network_args")
  })

  it("round-trips new LoKr and LoHa exports", () => {
    for (const loraType of ["lokr", "loha"]) {
      const exported = {
        ...exportedConfig(formModel({ lora_type: loraType, lokr_factor: 16 })),
        lora_type: loraType,
      }
      const imported = importIntoForm(exported)

      expect(imported.lora_type).toBe(loraType)
      expect(imported.network_module).toBe("lycoris.kohya")
      expect(imported.lycoris_algo).toBe(loraType)
      if (loraType === "lokr") expect(imported.lokr_factor).toBe(16)
    }
  })

  it("migrates legacy LyCORIS drafts to custom with their advanced fields", () => {
    const imported = importIntoForm({
      model_train_type: "flux-lora",
      network_module: "lycoris.kohya",
      network_args: ["algo=lokr", "factor=16", "conv_dim=8", "conv_alpha=4", "dropout=0.1", "train_norm=True"],
    })

    expect(imported.lora_type).toBe("custom")
    expect(imported.network_module).toBe("lycoris.kohya")
    expect(imported.lycoris_algo).toBe("lokr")
    expect(imported.lokr_factor).toBe(16)
    expect(imported.conv_dim).toBe(8)
    expect(imported.train_norm).toBe(true)
  })

  it("uses original import keys when backend hydration added a type", () => {
    const imported = importIntoForm({
      model_train_type: "flux-lora",
      lora_type: "lokr",
      network_module: "lycoris.kohya",
      network_args: ["algo=lokr", "factor=16", "train_norm=True"],
    }, false)

    expect(imported.lora_type).toBe("custom")
    expect(imported.train_norm).toBe(true)
  })

  it("maps explicitly imported non-first-class algorithms to custom", () => {
    const imported = importIntoForm({
      model_train_type: "flux-lora",
      lora_type: "boft",
      network_module: "lycoris.kohya",
      network_args: ["algo=boft", "conv_dim=4", "conv_alpha=1", "dropout=0"],
    })

    expect(imported.lora_type).toBe("custom")
    expect(imported.lycoris_algo).toBe("boft")
  })

  it("keeps legacy plain LoRA and OFT drafts on their original network modules", () => {
    expect(importIntoForm({ model_train_type: "flux-lora", network_module: "networks.lora_flux" }).lora_type).toBe("lora")

    const oft = importIntoForm({ model_train_type: "flux-lora", network_module: "networks.oft_flux" })
    expect(oft.lora_type).toBe("custom")
    expect(oft.network_module).toBe("networks.oft_flux")
  })

  it("detects explicit types inside imported history rows", () => {
    const history = { value: { model_train_type: "flux-lora", lora_type: "lokr" } } as unknown as FormModel
    expect(hasExplicitFluxLoraType(history)).toBe(true)
    expect(hasExplicitFluxLoraType({ value: [] })).toBe(false)
  })
})
