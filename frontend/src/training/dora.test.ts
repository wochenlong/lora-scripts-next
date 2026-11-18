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
import { buildTrainingConfig, hydrateImportedConfig } from "./params"

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

const schema = loadSchema("sd3-lora")

function exportedConfig(model: FormModel) {
  return buildTrainingConfig(serializeModel(schema, model), "sd3-lora")
}

function importIntoForm(config: FormModel) {
  const defaults = createDefaultModel(schema)
  const explicitKeys = new Set(Object.keys(config))
  const imported = hydrateImportedConfig(cloneFormModel(config))
  const model = normalizeModelForSchema(schema, { ...cloneFormModel(defaults), ...imported }, { explicitKeys })
  applyReadonlyDefaults(schema, model, defaults)
  return model
}

function doraModel(): FormModel {
  return {
    ...createDefaultModel(schema),
    lora_type: "dora",
    dropout: 0.1,
    rank_dropout: 0.05,
    network_dim: 16,
    network_alpha: 16,
  }
}

describe("DoRA adapter type (#30)", () => {
  it("serializes the dora branch with hidden lycoris companions", () => {
    const serialized = serializeModel(schema, doraModel())

    expect(serialized.lora_type).toBe("dora")
    expect(serialized.network_module).toBe("lycoris.kohya")
    expect(serialized.lycoris_algo).toBe("lora")
    expect(serialized.dora_wd).toBe(true)
    expect(serialized.dropout).toBe(0.1)
  })

  it("builds a training config without LoKr leftovers", () => {
    const config = exportedConfig(doraModel())

    expect(config.lora_type).toBe("dora")
    expect(config.network_module).toBe("lycoris.kohya")
    expect(config.network_args).toEqual(expect.arrayContaining(["algo=lora"]))
    expect(config.network_args).not.toEqual(expect.arrayContaining(["algo=lokr"]))
    expect((config.network_args as string[]).some((item) => item.startsWith("factor="))).toBe(false)
    expect((config.network_args as string[]).some((item) => item.startsWith("full_matrix="))).toBe(false)
    // dora_wd stays top-level; the backend adapter folds it into network_args.
    expect(config.dora_wd).toBe(true)
    expect(config).not.toHaveProperty("lokr_factor")
  })

  it("keeps the dora identity when the exported config is imported back", () => {
    const model = importIntoForm(exportedConfig(doraModel()))

    expect(model.lora_type).toBe("dora")
    expect(model.network_module).toBe("lycoris.kohya")
    expect(model.lycoris_algo).toBe("lora")
    expect(model.dora_wd).toBe(true)
    expect(model.dropout).toBe(0.1)
    expect(model.rank_dropout).toBe(0.05)
  })

  it("switching from lokr to dora drops LoKr-only fields", () => {
    const model = importIntoForm(exportedConfig({
      ...createDefaultModel(schema),
      lora_type: "lokr",
      lokr_factor: 16,
      full_matrix: true,
      use_cp: true,
    }))
    const switched = normalizeModelForSchema(schema, { ...model, lora_type: "dora" })
    applyReadonlyDefaults(schema, switched, createDefaultModel(schema))
    const config = exportedConfig(switched)

    expect(config.lora_type).toBe("dora")
    expect(config).not.toHaveProperty("lokr_factor")
    expect((config.network_args as string[]).some((item) => item.startsWith("factor="))).toBe(false)
  })
})
