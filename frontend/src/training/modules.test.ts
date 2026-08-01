import { describe, expect, it } from "vitest"
import {
  DEFAULT_SELECTION,
  SCHEMA_META,
  TRAINING_ENGINES,
  TRAINING_MODELS,
  TRAINING_MODULES,
  firstSupportedEngine,  firstSupportedTarget,
  isEngineSupported,
  isTargetSupported,
  moduleForSchema,
  resolveModule,
} from "./modules"

describe("training module mapping", () => {
  it("resolves every v1 minimal mapping", () => {
    expect(resolveModule("anima", "kohya", "lora")?.schemaName).toBe("sd3-lora")
    expect(resolveModule("anima", "anima-fast", "lora")?.schemaName).toBe("anima-lora-fast")
    expect(resolveModule("anima", "kohya", "finetune")?.schemaName).toBe("anima-finetune")
    expect(resolveModule("sd", "kohya", "lora")?.schemaName).toBe("lora-master")
    expect(resolveModule("flux", "kohya", "lora")?.schemaName).toBe("flux-lora")
  })

  it("covers every training schema shipped by the backend except lora-basic", () => {
    expect(resolveModule("sd", "kohya", "finetune")?.schemaName).toBe("dreambooth")
    expect(resolveModule("lumina", "kohya", "lora")?.schemaName).toBe("lumina2-lora")
    const mapped = new Set(TRAINING_MODULES.map((module) => module.schemaName))
    for (const schema of ["sd3-lora", "anima-lora-fast", "anima-finetune", "lora-master", "dreambooth", "flux-lora", "lumina2-lora"]) {
      expect(mapped.has(schema), schema).toBe(true)
    }
  })

  it("resolves the default selection to the acceptance path sd3-lora", () => {
    expect(resolveModule(DEFAULT_SELECTION.model, DEFAULT_SELECTION.engine, DEFAULT_SELECTION.target)?.schemaName).toBe("sd3-lora")
  })

  it("returns undefined for unmapped combinations", () => {
    expect(resolveModule("anima", "kohya", "lokr")).toBeUndefined()
    expect(resolveModule("flux", "kohya", "finetune")).toBeUndefined()
    expect(resolveModule("lumina", "kohya", "finetune")).toBeUndefined()
    expect(resolveModule("anima", "musubi", "lora")).toBeUndefined()
  })

  it("marks musubi as unsupported for every model", () => {
    for (const model of TRAINING_MODELS) expect(isEngineSupported(model, "musubi")).toBe(false)
  })

  it("marks lokr as unsupported for every listed combination", () => {
    for (const module of TRAINING_MODULES) expect(module.target).not.toBe("lokr")
    for (const model of TRAINING_MODELS) {
      for (const engine of TRAINING_ENGINES) expect(isTargetSupported(model, engine, "lokr")).toBe(false)
    }
  })

  it("limits anima-fast engine to the anima model", () => {
    expect(isEngineSupported("anima", "anima-fast")).toBe(true)
    expect(isEngineSupported("sd", "anima-fast")).toBe(false)
    expect(isEngineSupported("flux", "anima-fast")).toBe(false)
    expect(isEngineSupported("lumina", "anima-fast")).toBe(false)
  })

  it("suggests fallback engine and target for unsupported selections", () => {
    expect(firstSupportedEngine("sd")).toBe("kohya")
    expect(firstSupportedTarget("anima", "kohya")).toBe("lora")
    expect(firstSupportedTarget("flux", "anima-fast")).toBeUndefined()
  })

  it("maps schema names back to modules", () => {
    expect(moduleForSchema("sd3-lora")).toMatchObject({ model: "anima", engine: "kohya", target: "lora" })
    expect(moduleForSchema("anima-finetune")).toMatchObject({ target: "finetune" })
    expect(moduleForSchema("dreambooth")).toMatchObject({ model: "sd", engine: "kohya", target: "finetune" })
    expect(moduleForSchema("lora-basic")).toBeUndefined()
  })

  it("keeps schema metadata for every mapped schema", () => {
    for (const module of TRAINING_MODULES) expect(SCHEMA_META[module.schemaName], module.schemaName).toBeDefined()
  })
})
