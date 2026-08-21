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
  ])("renders no launcher for disabled, broken, absent, or unsafe extensions", async (item) => {
    const { wrapper } = await mountHost([item])
    expect(wrapper.find('[data-testid="floating-extension-launcher"]').exists()).toBe(false)
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
    expect(JSON.parse(localStorage.getItem("plugin-floating-panel:sample-plugin") || "{}")).toEqual({ open: true })
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
