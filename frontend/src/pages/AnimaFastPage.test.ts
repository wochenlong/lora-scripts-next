// @vitest-environment jsdom
import { flushPromises, mount } from "@vue/test-utils"
import { afterEach, describe, expect, it, vi } from "vitest"
import AnimaFastPage from "./AnimaFastPage.vue"
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
const ready: EngineStatus = { id: "anima-fast", state: "ready", featureEnabled: true }
const installing: EngineStatus = { id: "anima-fast", state: "installing", featureEnabled: true }
const unknown: EngineStatus = { id: "anima-fast", state: "unknown", featureEnabled: true }

const trainingPageStub = {
  template: '<div class="training-page-stub"><slot name="form-top" /></div>',
}
const routerLinkStub = {
  props: ["to"],
  template: '<a class="ghost-button"><slot /></a>',
}

afterEach(() => {
  vi.restoreAllMocks()
  status.mockReset()
})

describe("AnimaFastPage polling", () => {
  it("does not poll when the runtime is already ready", async () => {
    status.mockResolvedValue(ready)
    const setInterval = vi.spyOn(window, "setInterval")

    const wrapper = mount(AnimaFastPage, {
      global: { plugins: [i18n], stubs: { TrainingPage: trainingPageStub, RouterLink: routerLinkStub } },
    })
    await flushPromises()

    expect(setInterval).not.toHaveBeenCalled()
    wrapper.unmount()
  })

  it("stops polling when the runtime becomes ready", async () => {
    status.mockResolvedValueOnce(installing).mockResolvedValueOnce(ready)
    let poll: (() => void) | undefined
    vi.spyOn(window, "setInterval").mockImplementation((handler) => {
      poll = handler as () => void
      return 42 as unknown as ReturnType<typeof window.setInterval>
    })
    const clearInterval = vi.spyOn(window, "clearInterval")

    const wrapper = mount(AnimaFastPage, {
      global: { plugins: [i18n], stubs: { TrainingPage: trainingPageStub, RouterLink: routerLinkStub } },
    })
    await flushPromises()
    poll?.()
    await flushPromises()

    expect(clearInterval).toHaveBeenCalledWith(42)
    expect(status).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })
})

describe("AnimaFastPage status bar", () => {
  it("shows a compact ready chip on the training form", async () => {
    status.mockResolvedValue(ready)
    const wrapper = mount(AnimaFastPage, {
      global: { plugins: [i18n], stubs: { TrainingPage: trainingPageStub, RouterLink: routerLinkStub } },
    })
    await flushPromises()

    const chip = wrapper.get('[data-testid="engine-ready-chip"]')
    expect(chip.text()).toContain("训练环境准备就绪")
    expect(wrapper.find('[data-testid="engine-status-bar"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it("shows not-ready status on the install page", async () => {
    status.mockResolvedValue(unknown)
    const wrapper = mount(AnimaFastPage, {
      global: { plugins: [i18n], stubs: { TrainingPage: trainingPageStub, RouterLink: routerLinkStub } },
    })
    await flushPromises()

    const bar = wrapper.get('[data-testid="engine-status-bar"]')
    expect(bar.attributes("data-state")).toBe("unknown")
    expect(bar.text()).toContain("状态未知")
    wrapper.unmount()
  })
})
