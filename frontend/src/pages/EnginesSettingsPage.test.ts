// @vitest-environment jsdom
import { flushPromises, mount } from "@vue/test-utils"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import EnginesSettingsPage from "./EnginesSettingsPage.vue"
import { enginesApi, type EngineStatus } from "../api/engines"
import { i18n } from "../i18n"
import { ENGINE_CATALOG, type EngineDefinition } from "../engines/catalog"

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
const order = (wrapper: ReturnType<typeof mount>) => wrapper.findAll(".engine-row").map((row) => row.attributes("data-engine"))
beforeEach(() => {
  localStorage.clear()
  vi.mocked(enginesApi.list).mockResolvedValue(statuses)
})
afterEach(() => {
  wrappers.forEach((w) => w.unmount())
  wrappers.length = 0
  ;(ENGINE_CATALOG as EngineDefinition[]).splice(5)
  vi.restoreAllMocks()
})

function addTestEngines() {
  for (const id of ["test-one", "test-two"]) {
    ;(ENGINE_CATALOG as EngineDefinition[]).push({ ...ENGINE_CATALOG[0]!, id: id as EngineDefinition["id"] })
  }
}

it("hides pagination for five engines and pages larger catalogs by five", async () => {
  expect((await setup()).find(".engine-pagination").exists()).toBe(false)
  addTestEngines()
  const wrapper = await setup()
  expect(order(wrapper)).toHaveLength(5)
  await wrapper.get('[data-page="next"]').trigger("click")
  expect(order(wrapper)).toEqual(["test-one", "test-two"])
  await wrapper.get('input[type="search"]').setValue("anima-fast")
  expect(order(wrapper)).toEqual(["anima-fast"])
  expect(wrapper.find(".engine-pagination").exists()).toBe(false)
  await wrapper.get('input[type="search"]').setValue("")
  expect(order(wrapper)).toEqual(statuses.map((s) => s.id))
})

it("moves a second-page engine to the global top and returns to page one", async () => {
  addTestEngines()
  localStorage.setItem("nt.settings.engineOrder", JSON.stringify(["test-one", "test-two", ...statuses.map((s) => s.id)]))
  const wrapper = await setup()
  await wrapper.get('[data-page="next"]').trigger("click")
  expect(order(wrapper)).toEqual(["ai-toolkit", "diffsynth"])
  await wrapper.get('[data-engine="diffsynth"].engine-row .engine-more-btn').trigger("click")
  await wrapper.get('[data-action="top"]').trigger("click")
  expect(order(wrapper)).toHaveLength(5)
  expect(order(wrapper)[0]).toBe("diffsynth")
})

it("shows Kohya's missing state independently from its default badge", async () => {
  const wrapper = await setup()
  expect(wrapper.get('[data-engine="kohya"].engine-row .engine-title-line').text()).toContain("未安装")
  expect(wrapper.get('[data-engine="diffsynth"].engine-row .engine-title-line').text()).toContain("未知")
})
it("combines search and filters and clears an empty result", async () => {
  const wrapper = await setup()
  await wrapper.get('[data-filter="installed"]').trigger("click")
  expect(order(wrapper)).toEqual(["anima-fast", "ai-toolkit"])
  await wrapper.get('input[type="search"]').setValue("qwen")
  expect(order(wrapper)).toEqual([])
  await wrapper.get(".engine-clear-filters").trigger("click")
  expect(order(wrapper)).toHaveLength(5)
})
it("moves by menu and persists without changing training preferences", async () => {
  localStorage.setItem("nt.training.enginePrefs", '{"rememberLast":false}')
  const wrapper = await setup()
  await wrapper.get('[data-engine="musubi"].engine-row .engine-more-btn').trigger("click")
  await wrapper.get('[data-action="top"]').trigger("click")
  expect(order(wrapper)[0]).toBe("musubi")
  expect(order(await setup())[0]).toBe("musubi")
  expect(localStorage.getItem("nt.training.enginePrefs")).toBe('{"rememberLast":false}')
  expect(enginesApi.install).not.toHaveBeenCalled()
})
it("reorders only internal handle drags and ignores external drops", async () => {
  const wrapper = await setup()
  const target = wrapper.get('[data-engine="kohya"].engine-row')
  await target.trigger("drop")
  expect(order(wrapper)[0]).toBe("kohya")
  await wrapper.get('[data-engine="diffsynth"].engine-row .engine-drag-handle').trigger("dragstart")
  await target.trigger("drop")
  expect(order(wrapper)[0]).toBe("diffsynth")
})
it("moves down within filtered results and restores the complete default order", async () => {
  const wrapper = await setup()
  await wrapper.get('[data-filter="installed"]').trigger("click")
  await wrapper.get('[data-engine="anima-fast"].engine-row .engine-more-btn').trigger("click")
  await wrapper.get('[data-action="down"]').trigger("click")
  expect(order(wrapper)).toEqual(["ai-toolkit", "anima-fast"])
  await wrapper.get('[data-filter="all"]').trigger("click")
  expect(order(wrapper)).toEqual(["kohya", "musubi", "ai-toolkit", "anima-fast", "diffsynth"])
  await wrapper.get('.engine-list-tools .engine-more-btn').trigger("click")
  await wrapper.get('.engine-list-tools .engine-more-menu button').trigger("click")
  expect(order(wrapper)).toEqual(statuses.map((status) => status.id))
})
it("keeps reordered view usable when storage fails", async () => {
  const wrapper = await setup()
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("quota") })
  await wrapper.get('[data-engine="musubi"].engine-row .engine-more-btn').trigger("click")
  await wrapper.get('[data-action="top"]').trigger("click")
  expect(order(wrapper)[0]).toBe("musubi")
})
it("supports pointer dragging for mouse and touch without native HTML drag", async () => {
  const wrapper = await setup()
  const handle = wrapper.get('[data-engine="anima-fast"].engine-row .engine-drag-handle')
  const target = wrapper.get('[data-engine="kohya"].engine-row').element
  Object.defineProperty(document, "elementFromPoint", { configurable: true, value: () => target })
  handle.element.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true, button: 0, clientX: 10, clientY: 100 }))
  handle.element.dispatchEvent(new MouseEvent("pointermove", { bubbles: true, clientX: 10, clientY: 20 }))
  handle.element.dispatchEvent(new MouseEvent("pointerup", { bubbles: true }))
  await flushPromises()
  expect(order(wrapper)[0]).toBe("anima-fast")
})
it.each(["return", "cancel", "lostcapture"])("does not save an abandoned pointer move: %s", async (action) => {
  const wrapper = await setup()
  const handle = wrapper.get('[data-engine="anima-fast"].engine-row .engine-drag-handle')
  let target = wrapper.get('[data-engine="kohya"].engine-row').element
  Object.defineProperty(document, "elementFromPoint", { configurable: true, value: () => target })
  handle.element.dispatchEvent(new MouseEvent("pointerdown", { bubbles: true, button: 0, clientX: 10, clientY: 100 }))
  handle.element.dispatchEvent(new MouseEvent("pointermove", { bubbles: true, clientX: 10, clientY: 20 }))
  if (action === "return") {
    target = handle.element
    handle.element.dispatchEvent(new MouseEvent("pointermove", { bubbles: true, clientX: 10, clientY: 100 }))
  } else {
    handle.element.dispatchEvent(new Event(action === "cancel" ? "pointercancel" : "lostpointercapture"))
  }
  handle.element.dispatchEvent(new MouseEvent("pointerup", { bubbles: true }))
  await flushPromises()
  expect(order(wrapper)).toEqual(statuses.map((s) => s.id))
  expect(localStorage.getItem("nt.settings.engineOrder")).toBeNull()
})

it("retains order across status refresh and clamps a shrinking filtered page", async () => {
  addTestEngines()
  const allReady = (ENGINE_CATALOG as EngineDefinition[]).map((engine) => ({
    id: engine.id, state: "ready" as const, featureEnabled: true,
  }))
  vi.mocked(enginesApi.list).mockResolvedValue(allReady)
  localStorage.setItem("nt.settings.engineOrder", JSON.stringify(["test-one", "test-two", ...statuses.map((s) => s.id)]))
  const wrapper = await setup()
  const savedOrder = localStorage.getItem("nt.settings.engineOrder")
  await wrapper.get('[data-filter="installed"]').trigger("click")
  await wrapper.get('[data-page="next"]').trigger("click")
  expect(order(wrapper)).toEqual(["ai-toolkit", "diffsynth"])
  vi.mocked(enginesApi.list).mockResolvedValue(allReady.map((s) => ({
    ...s, state: s.id === "anima-fast" ? "ready" : "not_installed",
  })))
  await wrapper.get('[data-engine="diffsynth"].engine-row .engine-more-btn').trigger("click")
  const refreshButton = wrapper.findAll('.engine-more-menu button').find((button) => button.text() === i18n.global.t("settings.engines.actions.refresh"))
  expect(refreshButton).toBeDefined()
  await refreshButton!.trigger("click")
  await flushPromises()
  expect(order(wrapper)).toEqual(["anima-fast"])
  expect(wrapper.find(".engine-pagination").exists()).toBe(false)
  expect(localStorage.getItem("nt.settings.engineOrder")).toBe(savedOrder)
})
