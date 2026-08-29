// @vitest-environment jsdom
import { describe, expect, it } from "vitest"
import router from "./router"

describe("generic plugin routes", () => {
  it("resolves plugin settings and logical artifact detail routes before the catch-all", () => {
    expect(router.resolve("/settings/plugins").matched.at(-1)?.path).toBe("/settings/plugins")
    expect(router.resolve("/settings/plugins/sample-plugin").name).toBe("plugin-settings")
    expect(router.resolve("/plugins/sample-plugin/artifacts/artifact-1").name).toBe("plugin-artifact-detail")
  })

  it("does not contain duplicate settings engine routes", () => {
    expect(router.getRoutes().filter((route) => route.path === "/settings/engines")).toHaveLength(1)
  })
})
