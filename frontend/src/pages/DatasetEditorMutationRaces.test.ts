// @vitest-environment jsdom
import { KeepAlive, defineComponent } from "vue"
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { ElDropdownItem, ElMessageBox } from "element-plus"
import { datasetApi, type DatasetMutation, type DatasetScan } from "../api/dataset"
import { datasetsApi } from "../api/datasets"
import { llmApi } from "../api/llm"
import { i18n } from "../i18n"
import { useDatasetEditorSession } from "../composables/useDatasetEditorSession"
import DatasetEditorPage from "./DatasetEditorPage.vue"

vi.mock("vue-router", () => ({ useRoute: () => ({ query: {} }), useRouter: () => ({ replace: vi.fn() }) }))
const root = "/mutation-races"
const state = useDatasetEditorSession()
const wrappers: VueWrapper[] = []

function scan(): DatasetScan {
  return {
    root, total: 2, tags: [], categories: [],
    items: ["a", "b"].map(name => ({
      name: `${name}.png`, relative_path: `${name}.png`, category: "", caption: `${name} baseline`,
      caption_exists: true, caption_format: "tag", caption_sha256: `${name}-before`, tags: [`${name} baseline`], image_url: "", thumb_url: "",
    })),
  }
}

function changed(kind: string): DatasetMutation {
  return {
    changed: 2,
    items: ["a", "b"].map(name => ({ image: `${name}.png`, caption: `${name} ${kind}`, caption_exists: true, caption_format: "tag", caption_sha256: `${name}-${kind}`, tags: [`${name} ${kind}`] })),
  }
}

beforeEach(() => {
  state.unload()
  state.drafts.value = {}
  state.showTranslations.value = false
  state.translationProvider.value = "danbooru"
  state.rememberDataset(root, root)
  vi.spyOn(datasetApi, "scan").mockResolvedValue(scan())
  vi.spyOn(datasetApi, "history").mockResolvedValue({ can_undo: true, can_redo: true, changes: [] })
  vi.spyOn(datasetsApi, "list").mockResolvedValue({ root: "/", exists: true, datasets: [] })
  vi.spyOn(datasetApi, "tagDictionaryStatus").mockRejectedValue(new Error("not configured"))
  vi.spyOn(llmApi, "config").mockRejectedValue(new Error("not configured"))
  vi.spyOn(llmApi, "localVisionStatus").mockRejectedValue(new Error("not configured"))
  vi.spyOn(ElMessageBox, "confirm").mockResolvedValue("confirm" as never)
})

afterEach(() => {
  wrappers.forEach(wrapper => wrapper.unmount())
  wrappers.length = 0
  vi.restoreAllMocks()
})

async function render() {
  const wrapper = mount(defineComponent({ components: { DatasetEditorPage, KeepAlive }, template: "<KeepAlive><DatasetEditorPage /></KeepAlive>" }), {
    global: { plugins: [i18n], stubs: { ElDialog: true, PathPickerDialog: true, ManagedDatasetPicker: true, TagTranslationControls: true, TagTranslationSettingsDialog: true, TagFilterPanel: true } },
  })
  wrappers.push(wrapper)
  await flushPromises()
  await choose(wrapper, 0)
  await wrapper.findAll(".caption-mode button")[1]!.trigger("click")
  return wrapper
}

async function choose(wrapper: VueWrapper, index: number) {
  await wrapper.findAll(".image-grid button")[index]!.trigger("click")
  await flushPromises()
}

async function beginBatch(wrapper: VueWrapper) {
  await wrapper.get(".dataset-batch-entry").trigger("click")
  await wrapper.get(".batch-body .el-input input").setValue("added")
  await wrapper.get(".batch-body .primary-action").trigger("click")
  await flushPromises()
}

async function beginHistory(wrapper: VueWrapper, kind: "undo" | "redo") {
  await wrapper.get(".dataset-tool-more").trigger("click")
  await flushPromises()
  const menuItem = wrapper.findAllComponents(ElDropdownItem).find(item => item.props("command") === kind)
  expect(menuItem?.props("disabled")).toBe(false)
  if (!menuItem) throw new Error(`${kind} menu item missing`)
  await menuItem.get('[role="menuitem"]').trigger("click")
  await flushPromises()
}

it.each(["new a draft", "a baseline"])("preserves a later draft during a delayed batch, including %s", async next => {
  const wrapper = await render()
  await wrapper.get(".caption-editor textarea").setValue("a draft before batch")
  let finish!: (data: DatasetMutation) => void
  const request = vi.spyOn(datasetApi, "batch").mockReturnValue(new Promise(resolve => { finish = resolve }))
  await beginBatch(wrapper)
  expect(request).toHaveBeenCalledWith(expect.objectContaining({ root, images: ["a.png", "b.png"], append: ["added"] }))
  expect((wrapper.get(".batch-body .primary-action").element as HTMLButtonElement).disabled).toBe(true)
  // Picking the image opens raw editing while the batch remains in flight.
  await choose(wrapper, 0)
  await wrapper.get(".caption-editor textarea").setValue(next)
  finish(changed("batch"))
  await flushPromises()
  expect(state.items.value[0]?.caption).toBe("a batch")
  expect(state.getDraft(root, "a.png")).toBe(next)
  expect((wrapper.get(".caption-editor textarea").element as HTMLTextAreaElement).value).toBe(next)
  expect((wrapper.get(".caption-panel .primary-action").element as HTMLButtonElement).disabled).toBe(false)
  expect(request).toHaveBeenCalledTimes(1)
})

it.each([
  ["undo", "new a draft"], ["undo", "a baseline"],
  ["redo", "new a draft"], ["redo", "a baseline"],
] as const)("preserves a later draft during delayed %s, including %s", async (kind, next) => {
  const wrapper = await render()
  await wrapper.get(".caption-editor textarea").setValue("a draft before history")
  let finish!: (data: DatasetMutation) => void
  const request = vi.spyOn(datasetApi, kind).mockReturnValue(new Promise(resolve => { finish = resolve }))
  await beginHistory(wrapper, kind)
  expect(request).toHaveBeenCalledWith(root)
  expect((wrapper.get(".caption-panel .primary-action").element as HTMLButtonElement).disabled).toBe(true)
  await wrapper.get(".caption-editor textarea").setValue(next)
  finish(changed(kind))
  await flushPromises()
  expect(state.items.value[0]?.caption).toBe(`a ${kind}`)
  expect(state.getDraft(root, "a.png")).toBe(next)
  expect((wrapper.get(".caption-editor textarea").element as HTMLTextAreaElement).value).toBe(next)
  expect((wrapper.get(".caption-panel .primary-action").element as HTMLButtonElement).disabled).toBe(false)
  expect(request).toHaveBeenCalledTimes(1)
})

it.each(["batch", "undo", "redo"] as const)("preserves the other image's new draft when delayed %s returns after switching", async kind => {
  const wrapper = await render()
  await wrapper.get(".caption-editor textarea").setValue("a draft before mutation")
  let finish!: (data: DatasetMutation) => void
  const request = vi.spyOn(datasetApi, kind).mockReturnValue(new Promise(resolve => { finish = resolve }))
  if (kind === "batch") await beginBatch(wrapper)
  else await beginHistory(wrapper, kind)
  expect(request).toHaveBeenCalledTimes(1)
  await choose(wrapper, 1)
  await wrapper.get(".caption-editor textarea").setValue("new b draft")
  finish(changed(kind))
  await flushPromises()
  expect(state.items.value[1]?.caption).toBe(`b ${kind}`)
  expect(state.getDraft(root, "b.png")).toBe("new b draft")
  expect((wrapper.get(".caption-editor textarea").element as HTMLTextAreaElement).value).toBe("new b draft")
  await choose(wrapper, 0)
  expect((wrapper.get(".caption-editor textarea").element as HTMLTextAreaElement).value).toBe(`a ${kind}`)
  await choose(wrapper, 1)
  expect((wrapper.get(".caption-editor textarea").element as HTMLTextAreaElement).value).toBe("new b draft")
})
