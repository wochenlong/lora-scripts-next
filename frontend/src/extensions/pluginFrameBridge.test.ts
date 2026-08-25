// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest"
import type { PluginHostExtension } from "../api/plugins"
import type { BridgeRequestEnvelope } from "./pluginBridgeSchemas"
import { bridgeCapabilitiesFor, startPluginEventStream } from "./pluginFrameBridge"

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

describe("plugin event stream admission", () => {
  it("does not acknowledge a subscription until the Sidecar stream is actually connected", async () => {
    let publish: ((event: unknown) => void) | undefined
    const streamCapability = vi.fn(async (
      _pluginId: string,
      _request: Pick<BridgeRequestEnvelope, "type" | "payload">,
      onEvent: (event: unknown) => void,
    ) => {
      publish = onEvent
      await new Promise(() => undefined)
    })
    const postEvent = vi.fn()
    let admitted = false
    const admission = startPluginEventStream({
      pluginId: "sample-plugin",
      request: { type: "session.subscribe", payload: { sessionId: "session-1" } },
      signal: new AbortController().signal,
      streamCapability,
      postEvent,
    }).then(() => { admitted = true })

    await Promise.resolve()
    publish?.({ connected: true })
    await Promise.resolve()
    expect(admitted).toBe(false)

    publish?.({ type: "connected", state: { id: "session-1", status: "idle" } })
    await admission
    expect(admitted).toBe(true)
    expect(postEvent).not.toHaveBeenCalled()
  })
})
