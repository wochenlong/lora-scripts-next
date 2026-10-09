// @vitest-environment jsdom
import { flushPromises, mount } from "@vue/test-utils"
import { createPinia } from "pinia"
import { ElMessage, ElMessageBox } from "element-plus"
import { beforeEach, expect, it, vi } from "vitest"
import { i18n } from "../i18n"
import TaggerPage from "./TaggerPage.vue"

vi.mock("vue-router", () => ({ useRoute: () => ({ query: {} }) }))

const captionPresetService = vi.hoisted(() => ({
  load: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  remove: vi.fn(),
}))

vi.mock("../tagger/captionPresets", () => ({
  createCaptionPresetService: () => captionPresetService,
}))

beforeEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
  captionPresetService.load.mockReset().mockResolvedValue([])
  captionPresetService.create.mockReset()
  captionPresetService.update.mockReset()
  captionPresetService.remove.mockReset()
})

function mountPage() {
  return mount(TaggerPage, { global: {
    plugins: [createPinia(), i18n], stubs: { ManagedDatasetPicker: true },
  } })
}

async function openCaptionSettings(wrapper: ReturnType<typeof mountPage>) {
  await wrapper.get('[data-testid="parameter-toggle"]').trigger("click")
  await wrapper.get('[data-testid="tab-advanced"]').trigger("click")
}

it("keeps unavailable modes quietly disabled and uses a searchable grouped model selector", async () => {
  const wrapper = mountPage()
  expect(wrapper.text()).not.toContain("待接入")
  expect(wrapper.find('[data-testid="preview-pending"]').exists()).toBe(false)
  expect(wrapper.find('[data-testid="retry-failed"]').exists()).toBe(false)
  expect(wrapper.find('input[placeholder*="huggingface"]').exists()).toBe(false)
  expect(wrapper.find("aside.tagger-status").exists()).toBe(false)
  const select = wrapper.findComponent({ name: "ElSelect" })
  expect(select.props("filterable")).toBe(true)
  expect(wrapper.findAllComponents({ name: "ElOptionGroup" })).toHaveLength(2)
  await select.vm.$emit("update:modelValue", "wd-eva02-large-tagger-v3")
  expect(select.props("modelValue")).toBe("wd-eva02-large-tagger-v3")
  expect(wrapper.get(".tagger-future").attributes("open")).toBeUndefined()
  expect(wrapper.get("#tagger-parameters").isVisible()).toBe(false)
  await wrapper.get('[data-testid="parameter-toggle"]').trigger("click")
  expect(wrapper.get("#tagger-parameters").isVisible()).toBe(true)
  await wrapper.get('#tagger-parameters input[type="number"]').setValue("0.5")
  await wrapper.get('[data-testid="parameter-close"]').trigger("click")
  await wrapper.get('[data-testid="parameter-toggle"]').trigger("click")
  expect((wrapper.get('#tagger-parameters input[type="number"]').element as HTMLInputElement).value).toBe("0.5")
  wrapper.unmount()
})

it("provides load, save-as-template and reset actions for natural-language prompts", async () => {
  const wrapper = mountPage()
  await flushPromises()
  await openCaptionSettings(wrapper)
  expect(wrapper.get('[data-testid="caption-load"]').text()).toContain("加载")
  expect(wrapper.get('[data-testid="caption-save-template"]').text()).toContain("保存为模板")
  expect(wrapper.get('[data-testid="caption-reset"]').text()).toContain("重置")
  wrapper.unmount()
})

it("loads, updates, and deletes a server-backed prompt template", async () => {
  captionPresetService.load.mockResolvedValue([
    { id: "preset-existing", name: "Existing", prompt: "Original prompt", language: "zh-CN" },
  ])
  captionPresetService.update.mockResolvedValue({
    id: "preset-existing", name: "Existing", prompt: "Edited prompt", language: "en",
  })
  captionPresetService.remove.mockResolvedValue(undefined)
  const wrapper = mountPage()
  await flushPromises()
  await openCaptionSettings(wrapper)
  const select = wrapper.get('[data-testid="caption-template-select"]')
  expect(select.text()).toContain("Existing")
  await select.setValue("preset-existing")
  await wrapper.get('[data-testid="caption-load"]').trigger("click")
  const prompt = wrapper.get('[data-testid="caption-prompt"]')
  expect((prompt.element as HTMLTextAreaElement).value).toBe("Original prompt")
  expect((wrapper.get('[data-testid="caption-language"]').element as HTMLSelectElement).value).toBe("zh-CN")

  await prompt.setValue("Edited prompt")
  await wrapper.get('[data-testid="caption-language"]').setValue("en")
  await wrapper.get('[data-testid="caption-update-template"]').trigger("click")
  await flushPromises()
  expect(captionPresetService.update).toHaveBeenCalledWith("preset-existing", {
    name: "Existing", prompt: "Edited prompt", language: "en",
  })
  expect((select.element as HTMLSelectElement).value).toBe("preset-existing")

  await wrapper.get('[data-testid="caption-delete-template"]').trigger("click")
  await flushPromises()
  expect(captionPresetService.remove).toHaveBeenCalledWith("preset-existing")
  expect((select.element as HTMLSelectElement).value).toBe("default")
  wrapper.unmount()
})

it("creates a named server template from the current prompt and language", async () => {
  vi.spyOn(ElMessageBox, "prompt").mockResolvedValue({ value: "My template", action: "confirm" } as never)
  captionPresetService.create.mockResolvedValue({
    id: "preset-created", name: "My template", prompt: "A custom prompt", language: "zh-CN",
  })
  const wrapper = mountPage()
  await flushPromises()
  await openCaptionSettings(wrapper)

  await wrapper.get('[data-testid="caption-prompt"]').setValue("A custom prompt")
  await wrapper.get('[data-testid="caption-language"]').setValue("zh-CN")
  await wrapper.get('[data-testid="caption-save-template"]').trigger("click")
  await flushPromises()

  expect(captionPresetService.create).toHaveBeenCalledWith({
    name: "My template", prompt: "A custom prompt", language: "zh-CN",
  })
  expect(wrapper.get('[data-testid="caption-template-select"]').text()).toContain("My template")
  expect((wrapper.get('[data-testid="caption-template-select"]').element as HTMLSelectElement).value).toBe("preset-created")
  wrapper.unmount()
})

it("keeps the editor intact and reports failures when preset storage is unavailable", async () => {
  captionPresetService.load.mockRejectedValue(new Error("offline"))
  const error = vi.spyOn(ElMessage, "error").mockImplementation(() => ({ close: vi.fn() }) as never)
  const wrapper = mountPage()
  await flushPromises()
  await openCaptionSettings(wrapper)

  expect((wrapper.get('[data-testid="caption-prompt"]').element as HTMLTextAreaElement).value)
    .toBe(i18n.global.t("tagger.workspace.defaultPrompt"))
  expect(error).toHaveBeenCalled()
  expect(wrapper.get('[data-testid="caption-save-template"]').attributes("disabled")).toBeUndefined()
  wrapper.unmount()
})

it("preserves the selected template and editor when an update fails", async () => {
  captionPresetService.load.mockResolvedValue([
    { id: "preset-existing", name: "Existing", prompt: "Original prompt", language: "en" },
  ])
  captionPresetService.update.mockRejectedValue(new Error("offline"))
  vi.spyOn(ElMessage, "error").mockImplementation(() => ({ close: vi.fn() }) as never)
  const wrapper = mountPage()
  await flushPromises()
  await openCaptionSettings(wrapper)
  const select = wrapper.get('[data-testid="caption-template-select"]')
  await select.setValue("preset-existing")
  await wrapper.get('[data-testid="caption-load"]').trigger("click")
  await wrapper.get('[data-testid="caption-prompt"]').setValue("Unsaved edit")

  await wrapper.get('[data-testid="caption-update-template"]').trigger("click")
  await flushPromises()

  expect((select.element as HTMLSelectElement).value).toBe("preset-existing")
  expect((wrapper.get('[data-testid="caption-prompt"]').element as HTMLTextAreaElement).value).toBe("Unsaved edit")
  wrapper.unmount()
})
