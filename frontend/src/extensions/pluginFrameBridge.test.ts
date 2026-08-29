// @vitest-environment jsdom
import { describe, expect, it } from "vitest"
import type { PluginHostExtension } from "../api/plugins"
import { bridgeCapabilitiesFor } from "./pluginFrameBridge"

function extension(overrides: Partial<PluginHostExtension> = {}): PluginHostExtension {
  return {
    pluginId: "sample-plugin",
    displayName: "Sample Assistant",
    enabled: true,
    state: "ready",
    capabilities: ["session.list", "session.subscribe", "provider.list", "provider.saveKey"],
    ui: {
      floatingPanel: { entryUrl: "/api/plugin-host/ui/sample-plugin/0.1.0/index.html" },
      settings: { entryUrl: "/api/plugin-host/ui/sample-plugin/0.1.0/index.html?view=settings" },
      artifactDetail: true,
    },
    ...overrides,
  }
}

describe("plugin frame capability grants", () => {
  it("grants the floating frame broker methods plus constrained host-local methods", () => {
    expect(bridgeCapabilitiesFor(extension(), "floating-panel")).toEqual([
      "navigation.openExternal",
      "navigation.openPluginRoute",
      "theme.get",
      "locale.get",
      "context.get",
      "artifact.open",
      "session.list",
      "session.subscribe",
      "provider.list",
      "provider.saveKey",
    ])
  })

  it("limits the independent settings frame to Provider and presentation methods", () => {
    expect(bridgeCapabilitiesFor(extension(), "settings")).toEqual([
      "navigation.openExternal",
      "navigation.openPluginRoute",
      "theme.get",
      "locale.get",
      "context.get",
      "provider.list",
      "provider.saveKey",
    ])
  })

  it("does not grant artifact navigation when the plugin has no artifact contribution", () => {
    const value = extension({ ui: { floatingPanel: { entryUrl: "/api/plugin-host/ui/sample-plugin/0.1.0/index.html" } } })
    expect(bridgeCapabilitiesFor(value, "floating-panel")).not.toContain("artifact.open")
  })
})
