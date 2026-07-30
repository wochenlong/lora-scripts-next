// @vitest-environment jsdom
import { flushPromises, mount } from "@vue/test-utils"
import { afterEach, describe, expect, it, vi } from "vitest"
import AnimaFastPage from "./AnimaFastPage.vue"
import { animaFastApi, type AnimaFastStatus } from "../api/animaFast"

vi.mock("../api/animaFast", () => ({
  animaFastApi: {
    status: vi.fn(),
    install: vi.fn(),
    repair: vi.fn(),
  },
}))

const status = vi.mocked(animaFastApi.status)
const ready: AnimaFastStatus = { state: "ready", feature_enabled: true }
const installing: AnimaFastStatus = { state: "installing", feature_enabled: true }

afterEach(() => {
  vi.restoreAllMocks()
  status.mockReset()
})

describe("AnimaFastPage polling", () => {
  it("does not poll when the runtime is already ready", async () => {
    status.mockResolvedValue(ready)
    const setInterval = vi.spyOn(window, "setInterval")

    const wrapper = mount(AnimaFastPage, {
      global: { stubs: { TrainingPage: true } },
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
      global: { stubs: { TrainingPage: true } },
    })
    await flushPromises()
    poll?.()
    await flushPromises()

    expect(clearInterval).toHaveBeenCalledWith(42)
    expect(status).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })
})
