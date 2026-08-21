// @vitest-environment jsdom
import { createPinia, setActivePinia } from "pinia"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { pluginsApi, type PluginHostExtension } from "../api/plugins"
import { useExtensionsStore } from "./extensions"

function extension(): PluginHostExtension {
  return {
    pluginId: "sample-plugin",
    displayName: "Sample Assistant",
    enabled: true,
    state: "ready",
    capabilities: [],
    ui: { floatingPanel: { entryUrl: "/api/plugin-host/ui/sample-plugin/0.1.0/index.html" } },
  }
}

describe("extensions store authority gate", () => {
  beforeEach(() => setActivePinia(createPinia()))
  afterEach(() => vi.restoreAllMocks())

  it("does not register a launcher when loopback bootstrap is unavailable", async () => {
    vi.spyOn(pluginsApi, "ensureHostAuthority").mockRejectedValue(new Error("sensitive authority detail"))
    const list = vi.spyOn(pluginsApi, "listExtensions")
    const store = useExtensionsStore()
    store.extensions = [extension()]

    await store.refresh()

    expect(list).not.toHaveBeenCalled()
    expect(store.extensions).toEqual([])
    expect(store.floatingExtensions).toEqual([])
    expect(store.error).toBe("Plugin host is unavailable.")
    expect(store.loaded).toBe(true)
  })

  it("registers only after bootstrap and discovery both succeed", async () => {
    const bootstrap = vi.spyOn(pluginsApi, "ensureHostAuthority").mockResolvedValue()
    const list = vi.spyOn(pluginsApi, "listExtensions").mockResolvedValue({ extensions: [extension()] })
    const store = useExtensionsStore()

    await store.refresh()

    expect(bootstrap).toHaveBeenCalledTimes(1)
    expect(list).toHaveBeenCalledTimes(1)
    expect(store.floatingExtensions.map((item) => item.pluginId)).toEqual(["sample-plugin"])
  })
})
