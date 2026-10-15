// @vitest-environment jsdom
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils"
import { createPinia } from "pinia"
import { ElMessage } from "element-plus"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { i18n } from "../i18n"
import TaggerPage from "./TaggerPage.vue"
import { llmApi, type CaptionPromptPreset } from "../api/llm"
import { taggerApi } from "../api/tagger"
import { useTaggerStore } from "../stores/tagger"
import { englishCaptionPrompt } from "../dataset/captionPrompts"

vi.mock("vue-router", () => ({ useRoute: () => ({ query: {} }) }))
vi.mock("../api/llm", () => ({
  isVerifiedProfile: (profile: { enabled: boolean; ready: boolean; capabilities: string[]; verified_capabilities?: string[] }, capability: string) => Boolean(profile.enabled && profile.ready && profile.capabilities.includes(capability) && profile.verified_capabilities?.includes(capability)),
  llmApi: {
    profiles: vi.fn().mockResolvedValue({
      version: 5, routes: {}, prompt_presets: [], cache: {},
      profiles: [
      { id: "text", name: "Text only", source: "remote", capabilities: ["text"], languages: ["zh-CN"], enabled: true, ready: true, verified_capabilities: ["text"] },
      { id: "local", name: "Local", source: "local-endpoint", capabilities: ["text", "vision"], languages: ["zh-CN"], enabled: true, ready: true, verified_capabilities: ["text", "vision"] },
      { id: "remote", name: "Remote", source: "remote", capabilities: ["text", "vision"], languages: ["zh-CN"], enabled: true, ready: true, verified_capabilities: ["text", "vision"] },
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
      { id: "wd-swinv2-v3", name: "WD Swin", model: "wd-swinv2-v3", family: "WD", author: "", runtime: "local", output: "tag", ready: true, downloaded: true, languages: ["native"], capabilities: ["tag"], parameters: [], profile_id: null },
      { id: "wd-convnext-v3", name: "WD Conv", model: "wd-convnext-v3", family: "WD", author: "", runtime: "local", output: "tag", ready: true, downloaded: true, languages: ["native"], capabilities: ["tag"], parameters: [], profile_id: null },
      { id: "wd-eva02-large-tagger-v3", name: "WD Eva", model: "wd-eva02-large-tagger-v3", family: "WD", author: "", runtime: "local", output: "tag", ready: true, downloaded: true, languages: ["native"], capabilities: ["tag"], parameters: [], profile_id: null },
      { id: "cl_tagger_1_01", name: "CL", model: "cl_tagger_1_01", family: "CL", author: "", runtime: "local", output: "tag", ready: true, downloaded: false, languages: ["native"], capabilities: ["tag"], parameters: [], profile_id: null },
      { id: "llm:local", name: "Local", model: "local-vision", family: "Vision LLM", author: "", runtime: "local", output: "natural", ready: true, downloaded: false, languages: ["zh-CN"], capabilities: ["vision", "caption"], parameters: [], profile_id: "local" },
      { id: "llm:remote", name: "Remote", model: "remote-vision", family: "Vision LLM", author: "", runtime: "api", output: "natural", ready: true, downloaded: false, languages: ["zh-CN"], capabilities: ["vision", "caption"], parameters: [], profile_id: "remote" },
    ] }),
    status: vi.fn().mockResolvedValue({ phase: "idle", message: "", model: "", download: { current: 0, total: 0, percent: 0, filename: "", bytes_current: 0, bytes_total: 0 }, tagging: { current: 0, total: 0, percent: 0, filename: "", bytes_current: 0, bytes_total: 0 }, updated_at: 0 }),
    prefetch: vi.fn(),
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
  expect(page.find('[data-testid="prefetch-model"]').exists()).toBe(true)
  expect(select.props("filterable")).toBe(true)
  expect(page.findAllComponents({ name: "ElOptionGroup" })).toHaveLength(2)
  await select.vm.$emit("update:modelValue", "wd-eva02-large-tagger-v3")
  expect(select.props("modelValue")).toBe("wd-eva02-large-tagger-v3")
  expect((page.get('[data-testid="prefetch-model"]').element as HTMLButtonElement).disabled).toBe(true)
  await page.get('[data-testid="prefetch-model"]').trigger("click")
  expect(taggerApi.prefetch).not.toHaveBeenCalled()
  expect(page.get("#tagger-parameters").isVisible()).toBe(false)
  await page.get('[data-testid="parameter-toggle"]').trigger("click")
  expect(page.get("#tagger-parameters").isVisible()).toBe(true)
  await page.get('#tagger-parameters input[type="number"]').setValue("0.5")
  await page.get('[data-testid="parameter-close"]').trigger("click")
  await page.get('[data-testid="parameter-toggle"]').trigger("click")
  expect((page.get('#tagger-parameters input[type="number"]').element as HTMLInputElement).value).toBe("0.5")
})

it.each([false, true])("refreshes downloaded models after prefetch without observing an active phase (already_downloaded=%s)", async alreadyDownloaded => {
  const success = vi.spyOn(ElMessage, "success").mockImplementation(() => ({ close: vi.fn() }) as never)
  const page = mountPage()
  await flushPromises()
  const document = await taggerApi.models()
  const modelId = "wd14-convnextv2-v2"
  const complete = { models: document.models.map(model => model.id === modelId ? { ...model, downloaded: true } : model) }
  vi.mocked(taggerApi.models).mockResolvedValueOnce(complete)
  vi.mocked(taggerApi.prefetch).mockResolvedValueOnce({ status: "success", data: { model_id: modelId, already_downloaded: alreadyDownloaded } })
  await page.get('[data-testid="prefetch-model"]').trigger("click")
  await flushPromises()
  expect(taggerApi.prefetch).toHaveBeenCalledWith(modelId)
  expect(success).toHaveBeenCalledWith(i18n.global.t(alreadyDownloaded ? "tagger.msg.alreadyDownloaded" : "tagger.msg.prefetchStarted"))
  expect((page.get('[data-testid="prefetch-model"]').element as HTMLButtonElement).disabled).toBe(true)
  expect(page.get(".tagger-model-state").text()).toBe(i18n.global.t("tagger.workspace.downloaded"))
})

it("refreshes assets when a fast download completes between status polls", async () => {
  const page = mountPage()
  await flushPromises()
  const document = await taggerApi.models()
  const modelId = "wd14-convnextv2-v2"
  vi.mocked(taggerApi.models).mockResolvedValueOnce({ models: document.models.map(model => model.id === modelId ? { ...model, downloaded: true } : model) })
  const store = useTaggerStore()
  store.status = { ...store.status, phase: "done", model: modelId, updated_at: 1 }
  await flushPromises()
  expect((page.get('[data-testid="prefetch-model"]').element as HTMLButtonElement).disabled).toBe(true)
})

it("shares the model-row action position between Tag downloads and Caption LLM management", async () => {
  const page = mountPage()
  await flushPromises()
  expect(page.get('.tagger-model-row [data-testid="prefetch-model"]').text()).toBe(i18n.global.t("tagger.prefetch"))
  expect(page.find('.tagger-actions [data-testid="prefetch-model"]').exists()).toBe(false)
  expect(page.find('[data-testid="llm-model-management"]').exists()).toBe(false)
  await page.get(".tagger-choice-row .tagger-segments").findAll("button")[1].trigger("click")
  expect(page.find('[data-testid="prefetch-model"]').exists()).toBe(false)
  const manage = page.get('.tagger-model-row [data-testid="llm-model-management"]')
  expect(manage.text()).toBe(i18n.global.t("tagger.caption.manageProfiles"))
  await manage.trigger("click")
  expect(page.getComponent({ name: "LlmSettingsDialog" }).props("modelValue")).toBe(true)
  await page.get(".tagger-choice-row .tagger-segments").findAll("button")[0].trigger("click")
  expect(page.find('[data-testid="llm-model-management"]').exists()).toBe(false)
  expect(page.find('.tagger-model-row [data-testid="prefetch-model"]').exists()).toBe(true)
})

it("uses recursive Tag jobs without exposing recursive or local-model controls", async () => {
  const page = mountPage()
  await flushPromises()
  await page.get('[data-testid="parameter-toggle"]').trigger("click")
  expect(page.text()).not.toContain(i18n.global.t("tagger.recursive"))
  expect(page.findComponent({ name: "ManagedVisionModel" }).exists()).toBe(false)
  expect(page.get(".tagger-model-row .inline-config-button").text()).toBe(i18n.global.t("tagger.prefetch"))
  expect(page.find('[data-testid="caption-concurrency"]').exists()).toBe(false)
  const startButton = page.get(".tagger-start").element
  const previewControls = page.get(".caption-preview-controls").element
  expect(startButton.compareDocumentPosition(previewControls) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  await page.get('input[placeholder="/data/datasets/images"]').setValue("/data/datasets/images")
  await page.get(".tagger-start").trigger("click")
  await flushPromises()
  expect(taggerApi.captionStart).toHaveBeenCalledWith(expect.objectContaining({ mode: "tag", recursive: true }))
  expect(vi.mocked(taggerApi.captionStart).mock.calls[0][0]).not.toHaveProperty("concurrency")
})

it("restores caption generation defaults and leaves fallback to the shared configuration", async () => {
  const page = mountPage()
  await openCaptionSettings(page)
  expect(page.text()).not.toContain(i18n.global.t("tagger.caption.enableLocalFallback"))
  expect(page.text()).not.toContain(i18n.global.t("tagger.recursive"))
  await page.get('[data-testid="tab-model"]').trigger("click")
  const parameters = page.findAll('#tagger-parameters input[type="number"]')
  expect((parameters[0].element as HTMLInputElement).value).toBe("1024")
  expect((parameters[1].element as HTMLInputElement).value).toBe("0.7")
  expect((parameters[2].element as HTMLInputElement).value).toBe("3")
  await parameters[0].setValue("768")
  await parameters[1].setValue("0.2")
  await parameters[2].setValue("7")
  await page.get(".tagger-restore").trigger("click")
  expect((parameters[0].element as HTMLInputElement).value).toBe("1024")
  expect((parameters[1].element as HTMLInputElement).value).toBe("0.7")
  expect((parameters[2].element as HTMLInputElement).value).toBe("3")
  await page.get('[data-testid="tab-advanced"]').trigger("click")
  await page.get(".caption-preset-select").setValue("builtin-caption-zh")
  await page.get('input[placeholder="/data/datasets/images"]').setValue("/data/datasets/images")
  await page.get('input[placeholder="/data/datasets/images/example.png"]').setValue("/data/datasets/images/example.png")
  await page.get(".tagger-actions button").trigger("click")
  await flushPromises()
  const previewRequest = vi.mocked(taggerApi.captionPreview).mock.calls[0]?.[0]
  expect(previewRequest).toMatchObject({ mode: "natural", recursive: true, max_tokens: 1024, temperature: 0.7, concurrency: 3 })
  expect(previewRequest).not.toHaveProperty("allow_local_fallback")
  await page.get(".tagger-start").trigger("click")
  await flushPromises()
  const startRequest = vi.mocked(taggerApi.captionStart).mock.calls[0]?.[0]
  expect(startRequest).toMatchObject({ mode: "natural", recursive: true, max_tokens: 1024, temperature: 0.7, concurrency: 3 })
  expect(startRequest).not.toHaveProperty("allow_local_fallback")
})

it("sends the edited Caption concurrency with both preview and batch requests", async () => {
  const page = mountPage()
  await openCaptionSettings(page)
  await page.get(".caption-preset-select").setValue("builtin-caption-zh")
  await page.get('[data-testid="tab-model"]').trigger("click")
  await page.get('[data-testid="caption-concurrency"]').setValue("6")
  await page.get('input[placeholder="/data/datasets/images"]').setValue("/data/datasets/images")
  await page.get('input[placeholder="/data/datasets/images/example.png"]').setValue("/data/datasets/images/example.png")
  await page.get(".tagger-actions button").trigger("click")
  await flushPromises()
  expect(taggerApi.captionPreview).toHaveBeenCalledWith(expect.objectContaining({ concurrency: 6 }))
  await page.get(".tagger-start").trigger("click")
  await flushPromises()
  expect(taggerApi.captionStart).toHaveBeenCalledWith(expect.objectContaining({ concurrency: 6 }))
})

it.each(["0", "17", "1.5", ""])("blocks Caption preview and batch for invalid concurrency %s", async concurrency => {
  const error = vi.spyOn(ElMessage, "error").mockImplementation(() => ({ close: vi.fn() }) as never)
  const page = mountPage()
  await openCaptionSettings(page)
  await page.get(".caption-preset-select").setValue("builtin-caption-zh")
  await page.get('[data-testid="tab-model"]').trigger("click")
  await page.get('[data-testid="caption-concurrency"]').setValue(concurrency)
  await page.get('input[placeholder="/data/datasets/images"]').setValue("/data/datasets/images")
  await page.get('input[placeholder="/data/datasets/images/example.png"]').setValue("/data/datasets/images/example.png")
  await page.get(".tagger-actions button").trigger("click")
  await page.get(".tagger-start").trigger("click")
  await flushPromises()
  expect(taggerApi.captionPreview).not.toHaveBeenCalled()
  expect(taggerApi.captionStart).not.toHaveBeenCalled()
  expect(error).toHaveBeenCalledWith(i18n.global.t("tagger.models.concurrencyRequired"))
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


it("keeps dev task presets and manual model choice inside Tag mode", async () => {
  const page = mountPage()
  await flushPromises()
  expect(page.get('[data-testid="tagger-task-hint"]').text()).toContain("一般用途")
  expect(page.findComponent({ name: "ElSelect" }).props("modelValue")).toBe("wd14-convnextv2-v2")
  await page.get('[data-testid="tagger-task-character"]').trigger("click")
  expect(page.findComponent({ name: "ElSelect" }).props("modelValue")).toBe("wd-swinv2-v3")
  await page.findComponent({ name: "ElSelect" }).vm.$emit("update:modelValue", "wd-eva02-large-tagger-v3")
  expect(page.get(".tagger-model-hint").text()).toContain("已手动更换模型")
  await page.get('[data-testid="parameter-toggle"]').trigger("click")
  await page.get(".tagger-restore").trigger("click")
  expect(page.findComponent({ name: "ElSelect" }).props("modelValue")).toBe("wd-swinv2-v3")
  const numbers = page.findAll('#tagger-parameters input[type="number"]')
  expect((numbers[1].element as HTMLInputElement).value).toBe("0.55")
  await page.get(".tagger-choice-row .tagger-segments").findAll("button")[1].trigger("click")
  expect(page.find('[data-testid="tagger-task"]').exists()).toBe(false)
  expect(page.find('[data-testid="llm-model-management"]').exists()).toBe(true)
  await page.get(".tagger-choice-row .tagger-segments").findAll("button")[0].trigger("click")
  expect(page.findComponent({ name: "ElSelect" }).props("modelValue")).toBe("wd-swinv2-v3")
})
