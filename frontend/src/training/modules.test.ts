import { describe, expect, it } from "vitest"
import {
  DEFAULT_SELECTION,
  SCHEMA_META,
  TRAINING_MODELS,
  TRAINING_MODULES,
  TRAINING_TARGETS,
  firstSupportedEngine,  firstSupportedTarget,
  isEngineSupported,
  moduleForSchema,
  moduleForTrainType,
  normalizeModel,
  resolveModule,
} from "./modules"

describe("training module mapping", () => {
  it("resolves every v1 minimal mapping", () => {
    expect(resolveModule("anima", "kohya", "lora")?.schemaName).toBe("sd3-lora")
    expect(resolveModule("anima", "anima-fast", "lora")?.schemaName).toBe("anima-lora-fast")
    expect(resolveModule("anima", "kohya", "finetune")?.schemaName).toBe("anima-finetune")
    expect(resolveModule("sd15", "kohya", "lora")?.schemaName).toBe("lora-master")
    expect(resolveModule("sdxl", "kohya", "lora")?.schemaName).toBe("lora-master")
    expect(resolveModule("flux", "kohya", "lora")?.schemaName).toBe("flux-lora")
  })

  it("splits the shared lora-master schema into SD 1.5 and SDXL with field defaults", () => {
    expect(resolveModule("sd15", "kohya", "lora")).toMatchObject({ defaults: { model_train_type: "sd-lora" }, storageKey: "sd15-lora" })
    expect(resolveModule("sdxl", "kohya", "lora")).toMatchObject({ defaults: { model_train_type: "sdxl-lora" }, storageKey: "sdxl-lora", legacyStorageKey: "lora-master" })
  })

  it("splits the shared dreambooth schema into SD 1.5 and SDXL finetune with field defaults", () => {
    expect(resolveModule("sd15", "kohya", "finetune")).toMatchObject({ schemaName: "dreambooth", defaults: { model_train_type: "sd-dreambooth" }, storageKey: "sd15-dreambooth" })
    expect(resolveModule("sdxl", "kohya", "finetune")).toMatchObject({ schemaName: "dreambooth", defaults: { model_train_type: "sdxl-finetune" }, storageKey: "sdxl-dreambooth", legacyStorageKey: "dreambooth" })
  })

  it("covers every training schema shipped by the backend except lora-basic", () => {
    expect(resolveModule("lumina", "kohya", "lora")?.schemaName).toBe("lumina2-lora")
    const mapped = new Set(TRAINING_MODULES.map((module) => module.schemaName))
    for (const schema of ["sd3-lora", "anima-lora-fast", "anima-finetune", "lora-master", "dreambooth", "flux-lora", "lumina2-lora"]) {
      expect(mapped.has(schema), schema).toBe(true)
    }
  })

  it("keeps storage keys identical to schemaName for unsplit modules", () => {
    for (const module of TRAINING_MODULES) {
      if (module.model === "sd15" || module.model === "sdxl") continue
      expect(module.storageKey, module.schemaName).toBeUndefined()
      expect(module.legacyStorageKey, module.schemaName).toBeUndefined()
    }
  })

  it("normalizes legacy sd model query to sdxl", () => {
    expect(normalizeModel("sd")).toBe("sdxl")
    expect(normalizeModel("sd15")).toBe("sd15")
    expect(normalizeModel("anima")).toBe("anima")
    expect(normalizeModel("unknown")).toBeUndefined()
    expect(normalizeModel(42)).toBeUndefined()
  })

  it("resolves the default selection to the acceptance path sd3-lora", () => {
    expect(resolveModule(DEFAULT_SELECTION.model, DEFAULT_SELECTION.engine, DEFAULT_SELECTION.target)?.schemaName).toBe("sd3-lora")
  })

  it("returns undefined for unmapped combinations", () => {
    expect(resolveModule("flux", "kohya", "finetune")).toBeUndefined()
    expect(resolveModule("lumina", "kohya", "finetune")).toBeUndefined()
    expect(resolveModule("anima", "musubi", "lora")).toBeUndefined()
  })

  it("limits musubi engine to the krea2 model", () => {
    expect(isEngineSupported("krea2", "musubi")).toBe(true)
    for (const model of TRAINING_MODELS) {
      if (model === "krea2") continue
      expect(isEngineSupported(model, "musubi")).toBe(false)
    }
  })

  it("limits ai-toolkit engine to the klein model", () => {
    expect(isEngineSupported("klein", "ai-toolkit")).toBe(true)
    expect(resolveModule("klein", "ai-toolkit", "lora")?.schemaName).toBe("klein-lora")
    for (const model of TRAINING_MODELS) {
      if (model === "klein") continue
      expect(isEngineSupported(model, "ai-toolkit")).toBe(false)
    }
  })

  it("limits master targets to lora and finetune; adapter types live in the form schema", () => {
    expect(TRAINING_TARGETS).toEqual(["lora", "finetune"])
    for (const module of TRAINING_MODULES) expect(["lora", "finetune"]).toContain(module.target)
  })

  it("limits anima-fast engine to the anima model", () => {
    expect(isEngineSupported("anima", "anima-fast")).toBe(true)
    expect(isEngineSupported("sd15", "anima-fast")).toBe(false)
    expect(isEngineSupported("sdxl", "anima-fast")).toBe(false)
    expect(isEngineSupported("flux", "anima-fast")).toBe(false)
    expect(isEngineSupported("lumina", "anima-fast")).toBe(false)
  })

  it("suggests fallback engine and target for unsupported selections", () => {
    expect(firstSupportedEngine("sd15")).toBe("kohya")
    expect(firstSupportedEngine("sdxl")).toBe("kohya")
    expect(firstSupportedTarget("anima", "kohya")).toBe("lora")
    expect(firstSupportedTarget("flux", "anima-fast")).toBeUndefined()
  })

  it("maps shared schemas back to the sdxl module (previous default)", () => {
    expect(moduleForSchema("sd3-lora")).toMatchObject({ model: "anima", engine: "kohya", target: "lora" })
    expect(moduleForSchema("anima-finetune")).toMatchObject({ target: "finetune" })
    expect(moduleForSchema("lora-master")).toMatchObject({ model: "sdxl", engine: "kohya", target: "lora" })
    expect(moduleForSchema("dreambooth")).toMatchObject({ model: "sdxl", engine: "kohya", target: "finetune" })
    expect(moduleForSchema("lora-basic")).toBeUndefined()
  })

  it("resolves modules from model_train_type without ambiguity", () => {
    expect(moduleForTrainType("sd-lora")).toMatchObject({ model: "sd15", engine: "kohya", target: "lora" })
    expect(moduleForTrainType("sdxl-lora")).toMatchObject({ model: "sdxl", engine: "kohya", target: "lora" })
    expect(moduleForTrainType("sd-dreambooth")).toMatchObject({ model: "sd15", engine: "kohya", target: "finetune" })
    expect(moduleForTrainType("sdxl-finetune")).toMatchObject({ model: "sdxl", engine: "kohya", target: "finetune" })
    expect(moduleForTrainType("sd3-lora")).toMatchObject({ model: "anima", engine: "kohya", target: "lora" })
    expect(moduleForTrainType("flux-lora")).toMatchObject({ model: "flux", target: "lora" })
    expect(moduleForTrainType("unknown-type")).toBeUndefined()
    expect(moduleForTrainType(undefined)).toBeUndefined()
    expect(moduleForTrainType(42)).toBeUndefined()
  })

  it("keeps schema metadata for every mapped schema", () => {
    for (const module of TRAINING_MODULES) expect(SCHEMA_META[module.schemaName], module.schemaName).toBeDefined()
  })
})
