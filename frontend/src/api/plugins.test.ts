// @vitest-environment jsdom
import { describe, expect, it } from "vitest"
import { isSafePluginHostUrl, isValidPluginId } from "./plugins"

describe("plugin host URL policy", () => {
  it("accepts only same-origin plugin-host API paths", () => {
    expect(isSafePluginHostUrl("/api/plugin-host/ui/sample/panel.html")).toBe(true)
    expect(isSafePluginHostUrl("/api/plugins/sample/panel.html")).toBe(false)
    expect(isSafePluginHostUrl("https://provider.example/panel.html")).toBe(false)
    expect(isSafePluginHostUrl("//provider.example/panel.html")).toBe(false)
    expect(isSafePluginHostUrl("javascript:alert(1)")).toBe(false)
    expect(isSafePluginHostUrl("/api/plugin-host/ui/%2e%2e/admin")).toBe(false)
  })

  it("accepts stable logical plugin ids and rejects path-like ids", () => {
    expect(isValidPluginId("sample-plugin.v1")).toBe(true)
    expect(isValidPluginId("../sample-plugin")).toBe(false)
    expect(isValidPluginId("sample/plugin")).toBe(false)
  })
})
