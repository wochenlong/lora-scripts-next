// @vitest-environment jsdom
import { flushPromises, mount } from "@vue/test-utils"
import { afterEach, describe, expect, it, vi } from "vitest"
import AiToolkitGatePage from "./AiToolkitGatePage.vue"
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
const ready: EngineStatus = { id: "ai-toolkit", state: "ready", featureEnabled: true }
const notInstalled: EngineStatus = { id: "ai-toolkit", state: "not_installed", featureEnabled: true }

const trainingPageStub = {
  template: '<div class="training-page-stub"><slot name="form-top" /></div>',
}
const routerLinkStub = {
  props: ["to"],
  template: '<a class="ghost-button"><slot /></a>',
}

function mountPage() {
  return mount(AiToolkitGatePage, {
    global: { plugins: [i18n], stubs: { TrainingPage: trainingPageStub, RouterLink: routerLinkStub } },
  })
}

afterEach(() => {
  vi.restoreAllMocks()
  status.mockReset()
})

describe("AiToolkitGatePage", () => {
  it("shows the training form with a ready chip when ai-toolkit is ready", async () => {
    status.mockResolvedValue(ready)
    const setInterval = vi.spyOn(window, "setInterval")
    const wrapper = mountPage()
    await flushPromises()

    expect(status).toHaveBeenCalledWith("ai-toolkit")
    expect(setInterval).not.toHaveBeenCalled()
    expect(wrapper.find(".training-page-stub").exists()).toBe(true)
    expect(wrapper.get('[data-testid="engine-ready-chip"]').text()).toContain("训练环境准备就绪")
    wrapper.unmount()
  })

  it("shows the install view instead of the form when ai-toolkit is not installed", async () => {
    status.mockResolvedValue(notInstalled)
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.find(".training-page-stub").exists()).toBe(false)
    expect(wrapper.text()).toContain("安装插件")
    wrapper.unmount()
  })
})
