// @vitest-environment jsdom
import { flushPromises, mount } from "@vue/test-utils"
import { beforeEach, describe, expect, it, vi } from "vitest"
import NetworkSettingsPanel from "./NetworkSettingsPanel.vue"

const api = vi.hoisted(() => ({ get: vi.fn(), save: vi.fn() }))
vi.mock("../api/plugins", () => ({ networkApi: api }))
vi.mock("vue-i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }))
const state = {
  settings: { mode: "auto", http_proxy: "", https_proxy: "", no_proxy: "localhost" },
  effective: { network_mode: "auto", source: "system", https_proxy: "http://localhost:7890", http_proxy: "", warning: "", proxy_enabled: true },
}

describe("shared network settings", () => {
  beforeEach(() => { api.get.mockReset().mockResolvedValue(state); api.save.mockReset().mockResolvedValue(state) })

  it("loads server settings on expansion and saves direct mode", async () => {
    const wrapper = mount(NetworkSettingsPanel)
    expect(api.get).not.toHaveBeenCalled()
    const details = wrapper.get('details')
    ;(details.element as HTMLDetailsElement).open = true
    await details.trigger('toggle')
    await flushPromises()
    expect(wrapper.text()).toContain('http://localhost:7890')
    await wrapper.get('select').setValue('direct')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(api.save).toHaveBeenCalledWith(expect.objectContaining({ mode: 'direct' }))
    wrapper.unmount()
  })

  it("shows server failures and allows retry without losing inputs", async () => {
    const wrapper = mount(NetworkSettingsPanel)
    ;(wrapper.get('details').element as HTMLDetailsElement).open = true
    await wrapper.get('details').trigger('toggle')
    await flushPromises()
    await wrapper.get('select').setValue('manual')
    api.save.mockRejectedValueOnce(new Error('invalid proxy'))
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.get('[role=alert]').text()).toBe('invalid proxy')
    expect(wrapper.get('select').element.value).toBe('manual')
    expect(wrapper.get('fieldset').attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })
})
