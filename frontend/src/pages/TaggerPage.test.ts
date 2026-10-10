// @vitest-environment jsdom
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils"
import { createPinia } from "pinia"
import { ElMessage } from "element-plus"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { i18n } from "../i18n"
import TaggerPage from "./TaggerPage.vue"
import { llmApi, type CaptionPromptPreset } from "../api/llm"
import { englishCaptionPrompt } from "../dataset/captionPrompts"

vi.mock("vue-router", () => ({ useRoute: () => ({ query: {} }) }))
vi.mock("../api/llm", () => ({
  llmApi: {
    profiles: vi.fn().mockResolvedValue({
      version: 5, routes: {}, prompt_presets: [], cache: {},
      profiles: [
        { id: "text", name: "Text only", source: "remote", capabilities: ["text"], languages: ["zh-CN"], enabled: true, ready: true },
        { id: "local", name: "Local", source: "local-endpoint", capabilities: ["text", "vision"], languages: ["zh-CN"], enabled: true, ready: true },
        { id: "remote", name: "Remote", source: "remote", capabilities: ["text", "vision"], languages: ["zh-CN"], enabled: true, ready: true },
      ],
    }),
    localVisionStatus: vi.fn().mockResolvedValue({ state: "missing", installed: false, downloaded_bytes: 0, total_bytes: 0 }),
    localVisionAction: vi.fn(),
    saveConfig: vi.fn(),
    promptPresets: vi.fn().mockResolvedValue({ presets: [], settings: { default_caption_preset_id: null }, revision: "r1" }),
    savePromptPresets: vi.fn(),
    importLegacyPromptPresets: vi.fn(),
  },
}))
vi.mock("../api/tagger", async importOriginal => ({
  tagJobRequest: (await importOriginal<typeof import("../api/tagger")>()).tagJobRequest,
  taggerApi: {
    models: vi.fn().mockResolvedValue({ models: [
      { id: "wd14-convnextv2-v2", name: "WD", model: "wd14-convnextv2-v2", family: "WD", author: "SmilingWolf", runtime: "local", output: "tag", ready: true, downloaded: false, languages: ["native"], capabilities: ["tag"], parameters: [], profile_id: null },
      { id: "wd-eva02-large-tagger-v3", name: "WD Eva", model: "wd-eva02-large-tagger-v3", family: "WD", author: "", runtime: "local", output: "tag", ready: true, downloaded: true, languages: ["native"], capabilities: ["tag"], parameters: [], profile_id: null },
      { id: "cl_tagger_1_01", name: "CL", model: "cl_tagger_1_01", family: "CL", author: "", runtime: "local", output: "tag", ready: true, downloaded: false, languages: ["native"], capabilities: ["tag"], parameters: [], profile_id: null },
      { id: "llm:local", name: "Local", model: "local-vision", family: "Vision LLM", author: "", runtime: "local", output: "natural", ready: true, downloaded: false, languages: ["zh-CN"], capabilities: ["vision", "caption"], parameters: [], profile_id: "local" },
      { id: "llm:remote", name: "Remote", model: "remote-vision", family: "Vision LLM", author: "", runtime: "api", output: "natural", ready: true, downloaded: false, languages: ["zh-CN"], capabilities: ["vision", "caption"], parameters: [], profile_id: "remote" },
    ] }),
    status: vi.fn().mockResolvedValue({ phase: "idle", message: "", model: "", download: { current: 0, total: 0, percent: 0, filename: "", bytes_current: 0, bytes_total: 0 }, tagging: { current: 0, total: 0, percent: 0, filename: "", bytes_current: 0, bytes_total: 0 }, updated_at: 0 }),
    captionStatus: vi.fn().mockResolvedValue({ job_id: null, phase: "idle", mode: null, message: "", current: 0, total: 0, filename: "", succeeded: 0, failed: 0, cancelled: 0, errors: [], updated_at: 0 }),
    captionHistory: vi.fn().mockResolvedValue({ jobs: [] }),
    captionReport: vi.fn(),
    captionStart: vi.fn().mockResolvedValue({
      job_id: "job", phase: "pending", mode: "natural", message: "", current: 0, total: 1,
      filename: "", succeeded: 0, failed: 0, cancelled: 0, errors: [], updated_at: 0,
    }),
    captionPreview: vi.fn().mockResolvedValue({ caption: "一只猫。", language: "zh-CN", profile_id: "remote", profile_revision: "rev" }),
    captionCancel: vi.fn(),
    captionRetryFailed: vi.fn(),
    captionRollback: vi.fn(),
    captionDeleteHistory: vi.fn(),
  },
}))

let wrapper: VueWrapper | undefined
beforeEach(() => {
  localStorage.clear()
  vi.restoreAllMocks()
  vi.clearAllMocks()
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.restoreAllMocks()
})

function mountPage() {
  wrapper = mount(TaggerPage, { attachTo: document.body, global: {
    plugins: [createPinia(), i18n],
    stubs: { ManagedDatasetPicker: true, PathPickerDialog: true, LlmSettingsDialog: true },
  } })
  return wrapper
}
async function openCaptionSettings(page: VueWrapper) {
  await flushPromises()
  await page.get(".tagger-choice-row .tagger-segments").findAll("button")[1].trigger("click")
  await page.get('[data-testid="parameter-toggle"]').trigger("click")
  await page.get('[data-testid="tab-advanced"]').trigger("click")
}
const existingPreset: CaptionPromptPreset = {
  id: "preset-existing", kind: "caption_prompt", name: "Existing", template: "Original prompt",
  system_prompt: "Visible facts only", language: "zh-CN", max_length: 300, output_format: "plain_text",
  model_capabilities: ["vision", "caption"], revision: "p1",
}

it("keeps unavailable sources disabled and uses a searchable grouped selector with persistent parameter drafts", async () => {
  const page = mountPage()
  await flushPromises()
  expect(page.text()).not.toContain("待接入")
  expect(page.find('[data-testid="preview-pending"]').exists()).toBe(false)
  expect(page.find('[data-testid="retry-failed"]').exists()).toBe(false)
  expect(page.find('input[placeholder*="huggingface"]').exists()).toBe(false)
  expect(page.find("aside.tagger-status").exists()).toBe(false)
  expect((page.findAll(".tagger-choice-row .tagger-segments")[1].findAll("button")[1].element as HTMLButtonElement).disabled).toBe(true)
  const select = page.findComponent({ name: "ElSelect" })
  expect(select.props("filterable")).toBe(true)
  expect(page.findAllComponents({ name: "ElOptionGroup" })).toHaveLength(2)
  await select.vm.$emit("update:modelValue", "wd-eva02-large-tagger-v3")
  expect(select.props("modelValue")).toBe("wd-eva02-large-tagger-v3")
  expect(page.get("#tagger-parameters").isVisible()).toBe(false)
  await page.get('[data-testid="parameter-toggle"]').trigger("click")
  expect(page.get("#tagger-parameters").isVisible()).toBe(true)
  await page.get('#tagger-parameters input[type="number"]').setValue("0.5")
  await page.get('[data-testid="parameter-close"]').trigger("click")
  await page.get('[data-testid="parameter-toggle"]').trigger("click")
  expect((page.get('#tagger-parameters input[type="number"]').element as HTMLInputElement).value).toBe("0.5")
})

it("provides preset selection, save-as and explicit restore actions with no independent language selector", async () => {
  const page = mountPage()
  await openCaptionSettings(page)
  expect(page.find(".caption-preset-select").exists()).toBe(true)
  const actions = page.findAll(".caption-preset-actions button")
  expect(actions[3].text()).toBe(i18n.global.t("tagger.caption.saveAs"))
  expect(actions[1].text()).toBe(i18n.global.t("tagger.caption.restorePrompt"))
  expect(actions[4].text()).toBe(i18n.global.t("tagger.caption.restoreDefault"))
  expect(page.find('[data-testid="caption-language"]').exists()).toBe(false)
  expect(page.find(".caption-output-language").exists()).toBe(false)
})

it("loads, updates and deletes server-backed presets while preserving their schema and revision", async () => {
  vi.mocked(llmApi.promptPresets).mockResolvedValueOnce({ presets: [existingPreset], settings: {}, revision: "r1" })
  vi.mocked(llmApi.savePromptPresets).mockImplementation(async document => ({ ...document, revision: document.revision === "r1" ? "r2" : "r3" }))
  const page = mountPage()
  await openCaptionSettings(page)
  const select = page.get(".caption-preset-select")
  expect(select.text()).toContain("Existing")
  await select.setValue("preset-existing")
  await flushPromises()
  const prompt = page.get(".caption-prompt-editor textarea")
  expect((prompt.element as HTMLTextAreaElement).value).toBe("Original prompt")
  expect(page.get(".caption-preset-properties").text()).toContain("简体中文")
  await prompt.setValue("Edited prompt")
  await page.findAll(".caption-preset-actions button")[0].trigger("click")
  await flushPromises()
  expect(llmApi.savePromptPresets).toHaveBeenNthCalledWith(1, {
    revision: "r1", settings: { default_caption_preset_id: "preset-existing" },
    presets: [expect.objectContaining({ id: "preset-existing", name: "Existing", template: "Edited prompt", language: "zh-CN", system_prompt: "Visible facts only", max_length: 300, output_format: "plain_text", model_capabilities: ["vision", "caption"] })],
  })
  expect((select.element as HTMLSelectElement).value).toBe("preset-existing")
  await page.findAll(".caption-preset-actions button")[2].trigger("click")
  await flushPromises()
  expect(llmApi.savePromptPresets).toHaveBeenNthCalledWith(2, { presets: [], settings: { default_caption_preset_id: null }, revision: "r2" })
  expect((select.element as HTMLSelectElement).value).toBe("")
})

it("creates a named server preset from the current prompt and base preset language", async () => {
  vi.mocked(llmApi.savePromptPresets).mockImplementationOnce(async document => ({ ...document, revision: "r2" }))
  const page = mountPage()
  await openCaptionSettings(page)
  await page.get(".caption-preset-select").setValue("builtin-caption-zh")
  await flushPromises()
  await page.get(".caption-preset-name").setValue("My template")
  await page.get(".caption-prompt-editor textarea").setValue("A custom prompt")
  await page.findAll(".caption-preset-actions button")[3].trigger("click")
  await flushPromises()
  expect(llmApi.savePromptPresets).toHaveBeenCalledWith(expect.objectContaining({
    revision: "r1", presets: [expect.objectContaining({ name: "My template", template: "A custom prompt", language: "zh-CN", kind: "caption_prompt" })],
  }))
  expect(page.get(".caption-preset-select").text()).toContain("My template")
  expect((page.get(".caption-preset-select").element as HTMLSelectElement).value).toMatch(/^caption-/)
})

it("keeps the editor intact and reports failures when preset storage is unavailable", async () => {
  vi.mocked(llmApi.promptPresets).mockRejectedValueOnce(new Error("offline"))
  const error = vi.spyOn(ElMessage, "error").mockImplementation(() => ({ close: vi.fn() }) as never)
  const page = mountPage()
  await flushPromises()
  // A failed initial load remains recoverable without discarding the built-in draft.
  expect(page.get('[role="alert"]').text()).toContain("offline")
  await page.get(".tagger-model-row .secondary-action").trigger("click")
  await flushPromises()
  await openCaptionSettings(page)
  expect((page.get(".caption-prompt-editor textarea").element as HTMLTextAreaElement).value).toBe(englishCaptionPrompt)
  vi.mocked(llmApi.promptPresets).mockRejectedValueOnce(new Error("offline"))
  await page.get(".caption-refresh-presets").trigger("click")
  await flushPromises()
  expect(error).toHaveBeenCalled()
  expect(page.findAll(".caption-preset-actions button")[3].attributes("disabled")).toBeUndefined()
})

it("preserves the selected preset and editor when an update fails", async () => {
  vi.mocked(llmApi.promptPresets).mockResolvedValueOnce({ presets: [{ ...existingPreset, language: "en" }], settings: {}, revision: "r1" })
  vi.mocked(llmApi.savePromptPresets).mockRejectedValueOnce(new Error("offline"))
  const error = vi.spyOn(ElMessage, "error").mockImplementation(() => ({ close: vi.fn() }) as never)
  const page = mountPage()
  await openCaptionSettings(page)
  const select = page.get(".caption-preset-select")
  await select.setValue("preset-existing")
  await flushPromises()
  await page.get(".caption-prompt-editor textarea").setValue("Unsaved edit")
  await page.findAll(".caption-preset-actions button")[0].trigger("click")
  await flushPromises()
  expect(error).toHaveBeenCalled()
  expect((select.element as HTMLSelectElement).value).toBe("preset-existing")
  expect((page.get(".caption-prompt-editor textarea").element as HTMLTextAreaElement).value).toBe("Unsaved edit")
})
