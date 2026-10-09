// @vitest-environment jsdom
import { KeepAlive, defineComponent } from "vue"
import { flushPromises, mount } from "@vue/test-utils"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { ElMessageBox } from "element-plus"
import { i18n } from "../i18n"
import { datasetApi, type ChangedItem, type DatasetScan } from "../api/dataset"
import { datasetsApi } from "../api/datasets"
import { useDatasetEditorSession } from "../composables/useDatasetEditorSession"
import DatasetEditorPage from "./DatasetEditorPage.vue"
import ManagedDatasetPicker from "../components/dataset/ManagedDatasetPicker.vue"

vi.mock("vue-router", () => ({ useRoute: () => ({ query: {} }), useRouter: () => ({ replace: vi.fn() }) }))
const state = useDatasetEditorSession()
const wrappers: ReturnType<typeof mount>[] = []
function scan(root: string): DatasetScan {
  return { root, total: 1, items: [{ name: "a.png", relative_path: "a.png", category: "", caption: "original", caption_exists: true, tags: ["original"], image_url: "", thumb_url: "" }], tags: [], categories: [] }
}
beforeEach(() => {
  state.unload()
  state.drafts.value = {}
  state.rememberDataset("/A", "/A")
  vi.spyOn(datasetApi, "scan").mockImplementation(async path => scan(path))
  vi.spyOn(datasetApi, "history").mockResolvedValue({ can_undo: false, can_redo: false, changes: [] })
  vi.spyOn(datasetsApi, "list").mockResolvedValue({ root: "/", exists: true, datasets: [] })
  vi.spyOn(datasetApi, "tagTranslationConfig").mockRejectedValue(new Error("not configured"))
  vi.spyOn(datasetApi, "tagDictionaryStatus").mockRejectedValue(new Error("not configured"))
  vi.spyOn(datasetApi, "localModelStatus").mockRejectedValue(new Error("not configured"))
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
  return wrapper
}

it("confirms draft loss and unloads without any file deletion", async () => {
  const wrapper = await render()
  const deleting = vi.spyOn(datasetsApi, "deleteDataset")
  state.setDraft("/A", "a.png", "draft")
  state.setDraft("/A", "other.png", "draft")
  const confirm = vi.spyOn(ElMessageBox, "confirm").mockRejectedValueOnce("cancel").mockResolvedValue("confirm" as never)
  // Unload lives in the toolbar's "more actions" menu.
  const menu = wrapper.findComponent({ name: "ElDropdown" })
  menu.vm.$emit("command", "unload")
  await flushPromises()
  expect(state.lastRoot.value).toBe("/A")
  menu.vm.$emit("command", "unload")
  await flushPromises()
  expect(confirm).toHaveBeenCalledTimes(2)
  expect(state.lastRoot.value).toBe("")
  expect((wrapper.find('[data-testid="scan-action"]').element as HTMLButtonElement).textContent).toContain("加载")
  expect(deleting).not.toHaveBeenCalled()
})

it("does not apply a late save from A to B or clear B's draft", async () => {
  const wrapper = await render()
  let finish!: (value: ChangedItem) => void
  vi.spyOn(datasetApi, "save").mockReturnValue(new Promise(resolve => { finish = resolve }))
  // Scanning keeps the pure gallery; the editor only opens once an image is picked.
  expect(wrapper.find(".caption-panel .primary-action").exists()).toBe(false)
  await wrapper.get(".image-grid button").trigger("click")
  await flushPromises()
  await wrapper.get(".caption-panel .primary-action").trigger("click")
  await wrapper.get('[data-testid="scan-action"]').trigger("click")
  await flushPromises()
  wrapper.findComponent(ManagedDatasetPicker).vm.$emit("select", "/B")
  await flushPromises()
  state.setDraft("/B", "a.png", "B draft")
  finish({ image: "a.png", caption: "A saved", tags: ["A"], caption_exists: true })
  await flushPromises()
  expect(state.lastRoot.value).toBe("/B")
  expect(state.items.value[0]?.caption).toBe("original")
  expect(state.getDraft("/B", "a.png")).toBe("B draft")
})

it("loads a directly typed path with Enter without opening the dataset selector", async () => {
  const wrapper = await render()
  await wrapper.get("#editor-dataset-path").setValue("/typed-folder")
  await wrapper.get("#editor-dataset-path").trigger("keyup.enter")
  await flushPromises()
  expect(datasetApi.scan).toHaveBeenLastCalledWith("/typed-folder")
  expect(state.lastRoot.value).toBe("/typed-folder")
})
