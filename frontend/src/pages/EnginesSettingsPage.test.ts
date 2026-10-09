// @vitest-environment jsdom
import { flushPromises, mount } from "@vue/test-utils"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import EnginesSettingsPage from "./EnginesSettingsPage.vue"
import { enginesApi, type EngineStatus } from "../api/engines"
import { i18n } from "../i18n"

vi.mock("../api/engines", () => ({
  enginesApi: { list: vi.fn(), install: vi.fn(), repair: vi.fn(), uninstall: vi.fn() },
}))
const statuses: EngineStatus[] = [
  { id: "kohya", state: "not_installed", featureEnabled: true },
  { id: "anima-fast", state: "ready", featureEnabled: true },
  { id: "musubi", state: "broken", featureEnabled: true },
  { id: "ai-toolkit", state: "installed_unverified", featureEnabled: true },
  { id: "diffsynth", state: "unknown", featureEnabled: true },
]
const wrappers: ReturnType<typeof mount>[] = []
async function setup() {
  const wrapper = mount(EnginesSettingsPage, {
    global: { plugins: [i18n], stubs: { NetworkSettingsPanel: true, DownloadSourcesPanel: true } },
  })
  wrappers.push(wrapper)
  await flushPromises()
  return wrapper
}
it("allows changing the default engine and retains it across mounts", async () => {
  const wrapper = await setup()
  const select = wrapper.get(".toolbar-default select")
  expect(select.attributes("disabled")).toBeUndefined()
  await select.setValue("musubi")
  expect(JSON.parse(localStorage.getItem("nt.training.enginePrefs")!).defaultEngine).toBe("musubi")
  expect(((await setup()).get(".toolbar-default select").element as HTMLSelectElement).value).toBe("musubi")
})
beforeEach(() => {
  localStorage.clear()
  vi.mocked(enginesApi.list).mockResolvedValue(statuses)
})
afterEach(() => {
  wrappers.forEach((w) => w.unmount())
  wrappers.length = 0
  vi.restoreAllMocks()
})
