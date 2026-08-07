// @vitest-environment jsdom
import { flushPromises, mount } from "@vue/test-utils"
import { afterEach, describe, expect, it, vi } from "vitest"
import MusubiGatePage from "./MusubiGatePage.vue"
import { enginesApi, type EngineStatus } from "../api/engines"
import { i18n } from "../i18n"

vi.mock("../api/engines", () => ({
  enginesApi: {
    status: vi.fn(),
    list: vi.fn(),
    install: vi.fn(),
    repair: vi.fn(),
    uninstall: vi.fn(),
  },
}))

const status = vi.mocked(enginesApi.status)
const ready: EngineStatus = { id: "musubi", state: "ready", featureEnabled: true }
const installing: EngineStatus = { id: "musubi", state: "installing", featureEnabled: true }
const notInstalled: EngineStatus = { id: "musubi", state: "not_installed", featureEnabled: true }

const trainingPageStub = {
  template: '<div class="training-page-stub"><slot name="form-top" /></div>',
}
const routerLinkStub = {
  props: ["to"],
  template: '<a class="ghost-button"><slot /></a>',
}

function mountPage() {
  return mount(MusubiGatePage, {
    global: { plugins: [i18n], stubs: { TrainingPage: trainingPageStub, RouterLink: routerLinkStub } },
  })
}

afterEach(() => {
  vi.restoreAllMocks()
  status.mockReset()
})

describe("MusubiGatePage", () => {
  it("shows the training form with a ready chip when musubi is ready", async () => {
    status.mockResolvedValue(ready)
    const setInterval = vi.spyOn(window, "setInterval")
    const wrapper = mountPage()
    await flushPromises()

    expect(status).toHaveBeenCalledWith("musubi")
    expect(setInterval).not.toHaveBeenCalled()
    expect(wrapper.find(".training-page-stub").exists()).toBe(true)
    expect(wrapper.get('[data-testid="engine-ready-chip"]').text()).toContain("训练环境准备就绪")
    wrapper.unmount()
  })

  it("shows the install view instead of the form when musubi is not installed", async () => {
    status.mockResolvedValue(notInstalled)
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.find(".training-page-stub").exists()).toBe(false)
    const bar = wrapper.get('[data-testid="engine-status-bar"]')
    expect(bar.attributes("data-state")).toBe("not_installed")
    expect(wrapper.text()).toContain("安装插件")
    wrapper.unmount()
  })

  it("stops polling once the runtime becomes ready", async () => {
    status.mockResolvedValueOnce(installing).mockResolvedValueOnce(ready)
    let poll: (() => void) | undefined
    vi.spyOn(window, "setInterval").mockImplementation((handler) => {
      poll = handler as () => void
      return 42 as unknown as ReturnType<typeof window.setInterval>
    })
    const clearInterval = vi.spyOn(window, "clearInterval")

    const wrapper = mountPage()
    await flushPromises()
    poll?.()
    await flushPromises()

    expect(clearInterval).toHaveBeenCalledWith(42)
    expect(status).toHaveBeenCalledTimes(2)
    expect(wrapper.find(".training-page-stub").exists()).toBe(true)
    wrapper.unmount()
  })
})
