// @vitest-environment jsdom
import { createPinia, setActivePinia } from "pinia"
import { flushPromises, mount } from "@vue/test-utils"
import { defineComponent, nextTick } from "vue"
import { createMemoryHistory, createRouter } from "vue-router"
import { beforeEach, describe, expect, it } from "vitest"
import GenericFloatingExtensionHost from "./GenericFloatingExtensionHost.vue"
import { i18n } from "../../i18n"
import { useExtensionsStore } from "../../stores/extensions"
import type { PluginHostExtension } from "../../api/plugins"

const Page = defineComponent({ template: "<div>page</div>" })

function extension(overrides: Partial<PluginHostExtension> = {}): PluginHostExtension {
  return {
    pluginId: "sample-plugin",
    displayName: "Sample Assistant",
    enabled: true,
    state: "ready",
    capabilities: ["theme.get", "locale.get", "context.get"],
    ui: { floatingPanel: { entryUrl: "/api/plugin-host/ui/sample-plugin/panel.html" } },
    ...overrides,
  }
}

async function mountHost(items: PluginHostExtension[]) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = useExtensionsStore()
  store.extensions = items
  store.loaded = true
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: "/one", component: Page },
      { path: "/two", component: Page },
      { path: "/plugins/:pluginId/artifacts/:artifactId", name: "plugin-artifact-detail", component: Page },
    ],
  })
  await router.push("/one")
  await router.isReady()
  const wrapper = mount(GenericFloatingExtensionHost, {
    attachTo: document.body,
    global: { plugins: [pinia, router, i18n] },
  })
  await flushPromises()
  return { wrapper, router, store }
}

beforeEach(() => {
  localStorage.clear()
  Object.defineProperty(window, "innerWidth", { configurable: true, value: 1440 })
  Object.defineProperty(window, "innerHeight", { configurable: true, value: 900 })
})

describe("GenericFloatingExtensionHost visibility", () => {
  it("renders no launcher when no extension is installed", async () => {
    const { wrapper } = await mountHost([])
    expect(wrapper.find('[data-testid="floating-extension-launcher"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it.each([
    extension({ enabled: false, state: "disabled" }),
    extension({ state: "broken" }),
    extension({ state: "absent" }),
    extension({ pluginId: "../sample-plugin" }),
    extension({ ui: { floatingPanel: { entryUrl: "https://untrusted.example/panel" } } }),
    extension({ ui: { floatingPanel: { entryUrl: "/api/plugin-host/ui/other-plugin/panel.html" } } }),
    extension({ ui: { floatingPanel: { entryUrl: "http://localhost:4518", mode: "server" } } }),
    extension({ ui: { floatingPanel: { entryUrl: "http://127.0.0.1:4518/panel", mode: "server" } } }),
  ])("renders no launcher for disabled, broken, absent, or unsafe extensions", async (item) => {
    const { wrapper } = await mountHost([item])
    expect(wrapper.find('[data-testid="floating-extension-launcher"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it("loads a server-mode UI directly without a sandbox or bridge", async () => {
    const { wrapper } = await mountHost([
      extension({
        displayName: "Next Trainer Agent",
        ui: { floatingPanel: { entryUrl: "http://127.0.0.1:4518", mode: "server" } },
      }),
    ])
    const frame = wrapper.get("iframe")
    expect(frame.attributes("src")).toBe("http://127.0.0.1:4518")
    expect(frame.attributes("sandbox")).toBeUndefined()
    wrapper.unmount()
  })

  it("renders an enabled launcher and an exact allow-scripts sandbox", async () => {
    const { wrapper } = await mountHost([extension({ unreadCount: 12 })])
    const launcher = wrapper.get('[data-testid="floating-extension-launcher"]')
    const frame = wrapper.get("iframe")
    expect(launcher.attributes("aria-expanded")).toBe("false")
    expect(frame.attributes("sandbox")).toBe("allow-scripts")
    expect(frame.attributes("sandbox")).not.toContain("allow-same-origin")
    expect(frame.attributes("src")).toBe("/api/plugin-host/ui/sample-plugin/panel.html")
    expect(wrapper.get(".floating-extension-badge").text()).toBe("9+")

    await launcher.trigger("click")
    expect(launcher.attributes("aria-expanded")).toBe("true")
    expect(wrapper.get('[data-testid="floating-extension-panel"]').isVisible()).toBe(true)
    expect(JSON.parse(localStorage.getItem("plugin-floating-panel:sample-plugin") || "{}")).toMatchObject({ open: true })
    wrapper.unmount()
  })
})

describe("GenericFloatingExtensionHost lifecycle", () => {
  it("keeps the same iframe instance across route changes", async () => {
    const { wrapper, router } = await mountHost([extension()])
    const iframe = wrapper.get("iframe").element
    await router.push("/two")
    await nextTick()
    expect(wrapper.get("iframe").element).toBe(iframe)
    wrapper.unmount()
  })

  it("opens and minimizes with Ctrl+Shift+A", async () => {
    const { wrapper } = await mountHost([extension()])
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "A", ctrlKey: true, shiftKey: true, bubbles: true }))
    await nextTick()
    expect(wrapper.get('[data-testid="floating-extension-launcher"]').attributes("aria-expanded")).toBe("true")

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "a", ctrlKey: true, shiftKey: true, bubbles: true }))
    await nextTick()
    expect(wrapper.get('[data-testid="floating-extension-launcher"]').attributes("aria-expanded")).toBe("false")
    wrapper.unmount()
  })

  it("resizes from the upper-left handle and persists bounded dimensions", async () => {
    const { wrapper } = await mountHost([extension()])
    const panel = wrapper.get<HTMLElement>('[data-testid="floating-extension-panel"]')
    const handle = wrapper.get('[data-testid="floating-extension-resize"]')

    handle.element.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true, clientX: 500, clientY: 400 }))
    window.dispatchEvent(new MouseEvent("pointermove", { clientX: 400, clientY: 300 }))
    window.dispatchEvent(new MouseEvent("pointerup", { clientX: 400, clientY: 300 }))
    await nextTick()

    expect(panel.element.style.width).toBe("620px")
    expect(panel.element.style.height).toBe("780px")
    expect(JSON.parse(localStorage.getItem("plugin-floating-panel:sample-plugin") || "{}")).toMatchObject({
      width: 620,
      height: 780,
    })
    wrapper.unmount()
  })

  it("supports keyboard resizing and clamps preferences to the viewport", async () => {
    localStorage.setItem(
      "plugin-floating-panel:sample-plugin",
      JSON.stringify({ open: true, width: 900, height: 900 }),
    )
    const { wrapper } = await mountHost([extension()])
    const panel = wrapper.get<HTMLElement>('[data-testid="floating-extension-panel"]')
    const handle = wrapper.get('[data-testid="floating-extension-resize"]')

    expect(panel.element.style.width).toBe("760px")
    expect(panel.element.style.height).toBe("804px")
    await handle.trigger("keydown", { key: "ArrowRight" })
    await handle.trigger("keydown", { key: "ArrowDown" })
    expect(panel.element.style.width).toBe("744px")
    expect(panel.element.style.height).toBe("788px")
    wrapper.unmount()
  })

  it("removes launcher and iframe immediately when the extension is disabled", async () => {
    const { wrapper, store } = await mountHost([extension()])
    expect(wrapper.find("iframe").exists()).toBe(true)
    store.extensions = [extension({ enabled: false, state: "disabled" })]
    await flushPromises()
    expect(wrapper.find('[data-testid="floating-extension-host"]').exists()).toBe(false)
    expect(wrapper.find("iframe").exists()).toBe(false)
    wrapper.unmount()
  })
})
