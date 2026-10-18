// @vitest-environment jsdom
import { flushPromises, mount } from "@vue/test-utils"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { ElMessage, ElMessageBox, type MessageBoxData } from "element-plus"
import MossGatePage from "./MossGatePage.vue"
import { enginesApi, type EngineStatus } from "../api/engines"
import { tasksApi } from "../api/tasks"
import { i18n } from "../i18n"

vi.mock("../api/engines", () => ({
  enginesApi: { status: vi.fn(), install: vi.fn(), repair: vi.fn() },
}))
vi.mock("../api/tasks", () => ({ tasksApi: { terminate: vi.fn() } }))

const ready: EngineStatus = { id: "moss", state: "ready", featureEnabled: true }
const missing: EngineStatus = { id: "moss", state: "not_installed", featureEnabled: true }
const installing: EngineStatus = { id: "moss", state: "installing", featureEnabled: true, facts: { task_id: "moss-install-1" } }
const wrappers: ReturnType<typeof mount>[] = []
class MockEventSource {
  static sources: MockEventSource[] = []
  onmessage?: (event: { data: string }) => void
  close = vi.fn()
  constructor(public url: string) { MockEventSource.sources.push(this) }
}
function mountPage() {
  const wrapper = mount(MossGatePage, {
    props: { bare: true },
    global: { plugins: [i18n], stubs: {
      TrainingPage: { props: ["schemaName"], template: '<div class="training-page-stub" :data-schema="schemaName"><slot name="form-top" /></div>' },
      RouterLink: { props: ["to"], template: '<a><slot /></a>' },
    } },
  })
  wrappers.push(wrapper)
  return wrapper
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.clearAllMocks()
  MockEventSource.sources = []
  vi.stubGlobal("EventSource", MockEventSource)
  vi.mocked(enginesApi.status).mockResolvedValue(missing)
  vi.spyOn(ElMessageBox, "confirm").mockResolvedValue("confirm" as MessageBoxData)
  vi.spyOn(ElMessage, "success").mockImplementation(() => ({ close: vi.fn() }))
  vi.spyOn(ElMessage, "error").mockImplementation(() => ({ close: vi.fn() }))
})
afterEach(() => {
  wrappers.splice(0).forEach(wrapper => wrapper.unmount())
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe("MOSS runtime gate", () => {
  it("opens the MOSS schema only when the runtime is ready and enabled", async () => {
    vi.mocked(enginesApi.status).mockResolvedValue(ready)
    const wrapper = mountPage()
    await flushPromises()
    expect(enginesApi.status).toHaveBeenCalledWith("moss")
    expect(wrapper.get(".training-page-stub").attributes("data-schema")).toBe("moss-image-anima-lora")
    expect(wrapper.find('[data-testid="engine-ready-chip"]').exists()).toBe(true)
    expect(vi.getTimerCount()).toBe(0)
  })

  it.each(["not_installed", "unknown", "installed_unverified", "broken", "disabled"] as const)("blocks training in %s state", async state => {
    vi.mocked(enginesApi.status).mockResolvedValue({ ...missing, state })
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.find(".training-page-stub").exists()).toBe(false)
    if (state === "unknown") expect(wrapper.find(".fast-actions").exists()).toBe(false)
    if (state === "disabled") expect(wrapper.get(".fast-actions .primary-action").attributes("disabled")).toBeDefined()
  })

  it("does not open training when the feature is disabled despite a stale ready state", async () => {
    vi.mocked(enginesApi.status).mockResolvedValue({ ...ready, featureEnabled: false })
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.find(".training-page-stub").exists()).toBe(false)
    expect(wrapper.get(".fast-actions .primary-action").attributes("disabled")).toBeDefined()
  })

  it("installs once, streams progress, polls to ready, and closes streams", async () => {
    const wrapper = mountPage()
    await flushPromises()
    vi.mocked(enginesApi.install).mockResolvedValue({ taskId: "moss-install-1", status: installing,
      logStream: "/api/mock/moss/log", progressStream: "/api/mock/moss/progress" })
    vi.mocked(enginesApi.status).mockResolvedValue(installing)
    await wrapper.get(".fast-actions .primary-action").trigger("click")
    await flushPromises()
    expect(enginesApi.install).toHaveBeenCalledExactlyOnceWith("moss")
    expect(MockEventSource.sources.map(source => source.url)).toEqual(["/api/mock/moss/log", "/api/mock/moss/progress"])
    MockEventSource.sources[0].onmessage?.({ data: JSON.stringify({ text: "Auditing MOSS" }) })
    MockEventSource.sources[1].onmessage?.({ data: JSON.stringify({ type: "progress", percent: 75, message: "Audit" }) })
    await flushPromises()
    expect(wrapper.get('[data-testid="install-console"]').text()).toContain("75%")
    expect(wrapper.text()).toContain("Auditing MOSS")
    await wrapper.get(".fast-actions .primary-action").trigger("click")
    expect(enginesApi.install).toHaveBeenCalledTimes(1)
    vi.mocked(enginesApi.status).mockResolvedValue(ready)
    await vi.advanceTimersByTimeAsync(2000)
    await flushPromises()
    expect(wrapper.find(".training-page-stub").exists()).toBe(true)
    expect(MockEventSource.sources.every(source => source.close.mock.calls.length > 0)).toBe(true)
    expect(vi.getTimerCount()).toBe(0)
  })

  it("resumes an existing installation and cleans up on unmount", async () => {
    vi.mocked(enginesApi.status).mockResolvedValue(installing)
    const wrapper = mountPage()
    await flushPromises()
    expect(MockEventSource.sources.map(source => source.url)).toEqual([
      "/api/engines/moss/install/log/stream/moss-install-1", "/api/engines/moss/install/progress/stream/moss-install-1",
    ])
    wrapper.unmount()
    expect(MockEventSource.sources.every(source => source.close.mock.calls.length > 0)).toBe(true)
    expect(vi.getTimerCount()).toBe(0)
  })

  it("honors a dismissed installation confirmation and reports installation failure", async () => {
    const wrapper = mountPage()
    await flushPromises()
    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce("cancel")
    await wrapper.get(".fast-actions .primary-action").trigger("click")
    await flushPromises()
    expect(enginesApi.install).not.toHaveBeenCalled()
    expect(ElMessage.error).not.toHaveBeenCalled()
    vi.mocked(enginesApi.install).mockRejectedValueOnce(new Error("mock installer failed"))
    await wrapper.get(".fast-actions .primary-action").trigger("click")
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith("mock installer failed")
    expect(wrapper.get(".fast-actions .primary-action").attributes("disabled")).toBeUndefined()
  })

  it("cancels the active install task without starting training", async () => {
    vi.mocked(enginesApi.status).mockResolvedValue(installing)
    const wrapper = mountPage()
    await flushPromises()
    vi.mocked(enginesApi.status).mockResolvedValue(missing)
    await wrapper.get('[data-testid="engine-cancel-install"]').trigger("click")
    await flushPromises()
    expect(tasksApi.terminate).toHaveBeenCalledWith("moss-install-1")
    expect(wrapper.find(".training-page-stub").exists()).toBe(false)
  })

  it("does not recreate polling after navigating away during the initial status request", async () => {
    let resolveStatus!: (value: EngineStatus) => void
    vi.mocked(enginesApi.status).mockReturnValue(new Promise(resolve => { resolveStatus = resolve }))
    const wrapper = mountPage()
    wrapper.unmount()
    resolveStatus(installing)
    await flushPromises()
    expect(MockEventSource.sources).toHaveLength(0)
    expect(vi.getTimerCount()).toBe(0)
  })

  it("ignores repeated install clicks while confirmation is pending", async () => {
    let resolveConfirm!: (value: MessageBoxData) => void
    vi.mocked(ElMessageBox.confirm).mockReturnValue(new Promise(resolve => { resolveConfirm = resolve }))
    vi.mocked(enginesApi.install).mockResolvedValue({ alreadyReady: true, status: ready })
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.get(".fast-actions .primary-action").trigger("click")
    await wrapper.get(".fast-actions .primary-action").trigger("click")
    expect(ElMessageBox.confirm).toHaveBeenCalledTimes(1)
    expect(enginesApi.install).not.toHaveBeenCalled()
    resolveConfirm("confirm" as MessageBoxData)
    await flushPromises()
    expect(enginesApi.install).toHaveBeenCalledExactlyOnceWith("moss")
  })


  it("shows the backend reason when an environment needs repair", async () => {
    vi.mocked(enginesApi.status).mockResolvedValue({ ...missing, state: "broken", message: "MOSS source fingerprint changed" })
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.text()).toContain("MOSS source fingerprint changed")
  })

})
