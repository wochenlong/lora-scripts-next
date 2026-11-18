// @vitest-environment jsdom
import { flushPromises, mount } from "@vue/test-utils"
import { beforeEach, describe, expect, it, vi } from "vitest"
import NetworkSettingsPanel from "./NetworkSettingsPanel.vue"

const api = vi.hoisted(() => ({ get: vi.fn(), save: vi.fn() }))
vi.mock("../api/plugins", () => ({ networkApi: api }))
vi.mock("vue-i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }))

const state = {
  settings: { mode: "auto", http_proxy: "", https_proxy: "", no_proxy: "localhost" },
  effective: {
    network_mode: "auto",
    source: "system",
    https_proxy: "http://localhost:7890",
    http_proxy: "",
    warning: "",
    proxy_enabled: true,
  },
}

describe("shared network settings", () => {
  beforeEach(() => {
    api.get.mockReset().mockResolvedValue(state)
    api.save.mockReset().mockResolvedValue(state)
  })

  it("loads server settings on mount and saves direct mode", async () => {
    const wrapper = mount(NetworkSettingsPanel)
    await flushPromises()
    expect(api.get).toHaveBeenCalled()
    expect(wrapper.find('[data-testid="network-settings-card"]').exists()).toBe(true)
    expect(wrapper.text()).toContain("http://localhost:7890")
    await wrapper.get('[data-testid="network-mode"]').setValue("direct")
    await wrapper.get("form").trigger("submit")
    await flushPromises()
    expect(api.save).toHaveBeenCalledWith(expect.objectContaining({ mode: "direct" }))
    wrapper.unmount()
  })

  it("shows server failures and allows retry without losing inputs", async () => {
    const wrapper = mount(NetworkSettingsPanel)
    await flushPromises()
    await wrapper.get('[data-testid="network-mode"]').setValue("manual")
    api.save.mockRejectedValueOnce(new Error("invalid proxy"))
    await wrapper.get("form").trigger("submit")
    await flushPromises()
    expect(wrapper.get("[role=alert]").text()).toBe("invalid proxy")
    expect((wrapper.get('[data-testid="network-mode"]').element as HTMLSelectElement).value).toBe("manual")
    expect(wrapper.get("fieldset").attributes("disabled")).toBeUndefined()
    wrapper.unmount()
  })

  it("keeps retry clickable when the initial load fails", async () => {
    api.get.mockRejectedValueOnce(new Error("request failed (HTTP 403)"))
    const wrapper = mount(NetworkSettingsPanel)
    await flushPromises()
    expect(wrapper.get("[role=alert]").text()).toContain("403")
    expect(wrapper.get("fieldset").attributes("disabled")).toBeDefined()
    const retry = wrapper.get('[data-testid="network-retry"]')
    expect(retry.attributes("disabled")).toBeUndefined()
    api.get.mockResolvedValueOnce(state)
    await retry.trigger("click")
    await flushPromises()
    expect(wrapper.get("fieldset").attributes("disabled")).toBeUndefined()
    expect(wrapper.text()).toContain("http://localhost:7890")
    wrapper.unmount()
  })
})
