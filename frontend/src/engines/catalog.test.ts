import { describe, expect, it } from "vitest"
import { ENGINE_CATALOG, engineDefinition } from "./catalog"

describe("engine catalog", () => {
  it("keeps kohya and anima-fast optional managed engines", () => {
    expect(engineDefinition("kohya")?.kind).toBe("optional")
    expect(engineDefinition("kohya")?.managesRuntime).toBe(true)
    expect(engineDefinition("anima-fast")?.kind).toBe("optional")
    expect(engineDefinition("anima-fast")?.managesRuntime).toBe(true)
    expect(ENGINE_CATALOG.some((engine) => engine.id === "musubi" && engine.kind === "optional" && engine.managesRuntime)).toBe(true)
  })
})
