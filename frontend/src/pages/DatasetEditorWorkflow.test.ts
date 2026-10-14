// @vitest-environment jsdom
import { KeepAlive, defineComponent } from "vue"
import { flushPromises, mount } from "@vue/test-utils"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { ElMessageBox } from "element-plus"
import { i18n } from "../i18n"
import { datasetApi, type ChangedItem, type DatasetScan } from "../api/dataset"
import { datasetsApi } from "../api/datasets"
import { llmApi } from "../api/llm"
import { useDatasetEditorSession } from "../composables/useDatasetEditorSession"
import DatasetEditorPage from "./DatasetEditorPage.vue"
import ManagedDatasetPicker from "../components/dataset/ManagedDatasetPicker.vue"

vi.mock("vue-router", () => ({ useRoute: () => ({ query: {} }), useRouter: () => ({ replace: vi.fn() }) }))
const state = useDatasetEditorSession()
const wrappers: ReturnType<typeof mount>[] = []
function scan(root: string): DatasetScan {
  return { root, total: 1, items: [{ name: "a.png", relative_path: "a.png", category: "", caption: "original", caption_exists: true, caption_format: "tag", tags: ["original"], image_url: "", thumb_url: "" }], tags: [], categories: [] }
}
function naturalScan(root: string): DatasetScan {
  return { root, total: 1, items: [{ name: "a.png", relative_path: "a.png", category: "", caption: "A cat by a window.", caption_exists: true, caption_format: "natural", tags: [], natural_text: "A cat by a window.", image_url: "", thumb_url: "" }], tags: [], categories: [] }
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
  // Unload lives in the dataset button's caret menu.
  const unload = async () => {
    await wrapper.get(".dataset-split-caret").trigger("click")
    await flushPromises()
    const item = wrapper.findAll(".dataset-split-menu button").find(candidate => candidate.text().includes("卸载"))
    if (!item) throw new Error("unload menu item missing")
    await item.trigger("click")
    await flushPromises()
  }
  await unload()
  expect(state.lastRoot.value).toBe("/A")
  await unload()
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

it("disables batch Tag operations for a natural-language caption dataset", async () => {
  vi.mocked(datasetApi.scan).mockImplementation(async path => naturalScan(path))
  const batchRequest = vi.spyOn(datasetApi, "batch")
  const wrapper = await render()
  const batchButton = wrapper.get(".dataset-batch-entry")
  expect((batchButton.element as HTMLButtonElement).disabled).toBe(true)
  expect(batchRequest).not.toHaveBeenCalled()
})

it("uses the shared LLM fallback setting without exposing a separate caption translation toggle", async () => {
  vi.mocked(datasetApi.scan).mockImplementation(async path => naturalScan(path))
  const request = vi.spyOn(llmApi, "translateCaption").mockResolvedValue({ translation: "一只猫在窗边。", cached: false, skipped: false })
  const wrapper = await render()
  await wrapper.get(".image-grid button").trigger("click")
  await flushPromises()
  expect(wrapper.find(".natural-caption-translation").exists()).toBe(true)
  expect(wrapper.get(".natural-caption-translation").text()).not.toContain(i18n.global.t("datasetEditor.caption.naturalTranslationFallback"))
  await wrapper.findComponent({ name: "ElSwitch" }).vm.$emit("update:modelValue", true)
  await flushPromises()
  expect(wrapper.get(".natural-caption-translation").find('label > input[type="checkbox"]').exists()).toBe(false)
  const retry = wrapper.findAll(".natural-translation-controls button").find(button => button.text() === i18n.global.t("datasetEditor.caption.retryNaturalTranslation"))!
  await retry.trigger("click")
  await flushPromises()
  expect(request).toHaveBeenCalledWith("A cat by a window.", undefined, expect.any(AbortSignal))
  expect(wrapper.get(".natural-caption-translated").text()).toContain("一只猫在窗边。")
})

async function rawEditor(wrapper: ReturnType<typeof mount>) {
  await wrapper.get(".image-grid button").trigger("click")
  await flushPromises()
  const raw = wrapper.findAll(".caption-mode button")[1]
  if (raw) await raw.trigger("click")
  return wrapper.get(".caption-editor textarea")
}

it.each(["B draft", "original"])("preserves editing during a delayed save, including reverting to %s", async next => {
  const wrapper = await render()
  const input = await rawEditor(wrapper)
  let finish!: (value: ChangedItem) => void
  const saving = vi.spyOn(datasetApi, "save").mockReturnValue(new Promise(resolve => { finish = resolve }))
  await input.setValue("A submitted")
  await wrapper.get(".caption-panel .primary-action").trigger("click")
  expect((wrapper.get(".caption-panel .primary-action").element as HTMLButtonElement).disabled).toBe(true)
  await input.setValue(next)
  finish({ image: "a.png", caption: "A submitted", caption_exists: true, caption_format: "tag", tags: ["A submitted"], caption_sha256: "saved-hash" })
  await flushPromises()
  expect(state.items.value[0]?.caption).toBe("A submitted")
  expect((wrapper.get(".caption-editor textarea").element as HTMLTextAreaElement).value).toBe(next)
  expect(state.getDraft("/A", "a.png")).toBe(next)
  expect(saving).toHaveBeenCalledTimes(1)
  expect((wrapper.get(".caption-panel .primary-action").element as HTMLButtonElement).disabled).toBe(false)
})

it("clears only the submitted draft after an unchanged successful save", async () => {
  const wrapper = await render()
  const input = await rawEditor(wrapper)
  await input.setValue("A submitted")
  vi.spyOn(datasetApi, "save").mockResolvedValue({ image: "a.png", caption: "A submitted", caption_exists: true, caption_format: "tag", tags: ["A submitted"] })
  await wrapper.get(".caption-panel .primary-action").trigger("click")
  await flushPromises()
  expect(state.getDraft("/A", "a.png")).toBeUndefined()
  expect((input.element as HTMLTextAreaElement).value).toBe("A submitted")
})

it("preserves another image's draft when the save returns after switching images", async () => {
  vi.mocked(datasetApi.scan).mockImplementation(async path => {
    const data = scan(path)
    data.items.push({ ...data.items[0]!, name: "b.png", relative_path: "b.png", caption: "B baseline" })
    data.total = 2
    return data
  })
  const wrapper = await render()
  const input = await rawEditor(wrapper)
  let finish!: (value: ChangedItem) => void
  vi.spyOn(datasetApi, "save").mockReturnValue(new Promise(resolve => { finish = resolve }))
  await input.setValue("A submitted")
  await wrapper.get(".caption-panel .primary-action").trigger("click")
  await wrapper.findAll(".image-grid button")[1]!.trigger("click")
  await wrapper.get(".caption-editor textarea").setValue("B draft")
  finish({ image: "a.png", caption: "A submitted", caption_exists: true, caption_format: "tag", tags: ["A submitted"] })
  await flushPromises()
  expect(state.getDraft("/A", "b.png")).toBe("B draft")
  expect((wrapper.get(".caption-editor textarea").element as HTMLTextAreaElement).value).toBe("B draft")
})

it("keeps the latest draft and restores save availability after failure", async () => {
  const wrapper = await render()
  const input = await rawEditor(wrapper)
  let fail!: (reason: Error) => void
  vi.spyOn(datasetApi, "save").mockReturnValue(new Promise((_resolve, reject) => { fail = reject }))
  await input.setValue("A submitted")
  await wrapper.get(".caption-panel .primary-action").trigger("click")
  await input.setValue("B draft")
  fail(new Error("conflict"))
  await flushPromises()
  expect(state.getDraft("/A", "a.png")).toBe("B draft")
  expect(state.items.value[0]?.caption).toBe("original")
  expect((wrapper.get(".caption-panel .primary-action").element as HTMLButtonElement).disabled).toBe(false)
})

it.each(["tag", "natural"] as const)("protects unknown short prose until explicit %s confirmation and keeps its draft", async format => {
  vi.mocked(datasetApi.scan).mockImplementation(async path => {
    const data = scan(path)
    data.items[0] = { ...data.items[0]!, caption: "A red car", caption_format: "unknown", tags: [], caption_sha256: "disk-hash" }
    return data
  })
  const confirming = vi.spyOn(datasetApi, "confirmCaptionFormat").mockResolvedValue({ image: "a.png", caption: "A red car", caption_exists: true, caption_format: format, caption_sha256: "disk-hash", tags: format === "tag" ? ["A red car"] : [] })
  const saving = vi.spyOn(datasetApi, "save")
  const wrapper = await render()
  const input = await rawEditor(wrapper)
  expect(wrapper.find(".caption-chips").exists()).toBe(false)
  expect((wrapper.get(".dataset-batch-entry").element as HTMLButtonElement).disabled).toBe(true)
  await input.setValue("Unsaved raw draft")
  await wrapper.get(`.caption-confirm-${format}`).trigger("click")
  await flushPromises()
  expect(confirming).toHaveBeenCalledWith("/A", "a.png", format, "disk-hash")
  expect(saving).not.toHaveBeenCalled()
  expect(state.items.value[0]?.caption_format).toBe(format)
  expect(state.items.value[0]?.caption).toBe("A red car")
  expect(state.getDraft("/A", "a.png")).toBe("Unsaved raw draft")
  expect((wrapper.get(".caption-editor textarea").element as HTMLTextAreaElement).value).toBe("Unsaved raw draft")
})

it("keeps explicit Tag intent for multiple chips in a new file and sends it when saving", async () => {
  vi.mocked(datasetApi.scan).mockImplementation(async path => {
    const data = scan(path)
    data.items[0] = { ...data.items[0]!, caption: "", caption_exists: false, caption_format: "unknown", caption_sha256: null, tags: [] }
    return data
  })
  const saving = vi.spyOn(datasetApi, "save").mockResolvedValue({ image: "a.png", caption: "cat, window", caption_exists: true, caption_format: "tag", caption_sha256: "saved", tags: ["cat", "window"] })
  const wrapper = await render()
  await wrapper.get(".image-grid button").trigger("click")
  await flushPromises()
  for (const tag of ["cat", "window"]) {
    await wrapper.get(".chip-add input").setValue(tag)
    await wrapper.get(".chip-add button").trigger("click")
  }
  expect(wrapper.findAll(".caption-chips .chip")).toHaveLength(2)
  await wrapper.get(".caption-panel .primary-action").trigger("click")
  await flushPromises()
  expect(saving).toHaveBeenCalledWith("/A", "a.png", "cat, window", null, "tag")
  expect(state.items.value[0]?.caption_format).toBe("tag")
})
