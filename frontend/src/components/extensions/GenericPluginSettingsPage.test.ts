// @vitest-environment jsdom
import { createPinia, setActivePinia } from "pinia"
import { flushPromises, mount } from "@vue/test-utils"
import { defineComponent } from "vue"
import { createMemoryHistory, createRouter } from "vue-router"
import { beforeEach, describe, expect, it } from "vitest"
import GenericPluginSettingsPage from "./GenericPluginSettingsPage.vue"
import { i18n } from "../../i18n"
import { useExtensionsStore } from "../../stores/extensions"

async function mountPage(entryUrl?: string) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = useExtensionsStore()
  store.loaded = true
  store.extensions = [
    {
      pluginId: "sample-plugin",
      displayName: "Sample Assistant",
      enabled: true,
      state: "ready",
      capabilities: [],
      ui: { ...(entryUrl ? { settings: { entryUrl } } : {}) },
    },
  ]
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/settings/plugins/:pluginId", component: GenericPluginSettingsPage }],
  })
  await router.push("/settings/plugins/sample-plugin")
  await router.isReady()
  const wrapper = mount(defineComponent({ template: "<RouterView />" }), {
    attachTo: document.body,
    global: { plugins: [pinia, router, i18n] },
  })
  await flushPromises()
  return wrapper
}

beforeEach(() => localStorage.clear())

describe("GenericPluginSettingsPage", () => {
  it("renders a sandboxed same-origin settings contribution", async () => {
    const wrapper = await mountPage("/api/plugin-host/ui/sample-plugin/settings.html")
    const frame = wrapper.get("iframe")
    expect(frame.attributes("sandbox")).toBe("allow-scripts")
    expect(frame.attributes("src")).toBe("/api/plugin-host/ui/sample-plugin/settings.html")
    expect(wrapper.text()).toContain("Sample Assistant")
    wrapper.unmount()
  })

  it("does not render unsafe or missing settings contributions", async () => {
    const wrapper = await mountPage("https://untrusted.example/settings")
    expect(wrapper.find("iframe").exists()).toBe(false)
    expect(wrapper.text()).toContain("设置页面不可用")
    wrapper.unmount()
  })

  it("does not frame another plugin's settings contribution", async () => {
    const wrapper = await mountPage("/api/plugin-host/ui/other-plugin/settings.html")
    expect(wrapper.find("iframe").exists()).toBe(false)
    wrapper.unmount()
  })
})
