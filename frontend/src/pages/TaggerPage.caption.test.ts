// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest"
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils"
import { createPinia } from "pinia"
import TaggerPage from "./TaggerPage.vue"
import { i18n } from "../i18n"
import { llmApi } from "../api/llm"
import { taggerApi } from "../api/tagger"
import { ElMessageBox } from "element-plus"
import { defineComponent } from "vue"

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
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.clearAllMocks()
  vi.restoreAllMocks()
})

async function naturalPage() {
  wrapper = mount(TaggerPage, {
    global: { plugins: [createPinia(), i18n], stubs: { PathPickerDialog: true } },
  })
  await flushPromises()
  await wrapper.findAll(".tagger-mode-tabs button")[1].trigger("click")
  await flushPromises()
  return wrapper
}

describe("natural-language TaggerPage", () => {
  it("starts English-first and switches both built-in prompt fields with output language", async () => {
    const document = await taggerApi.models()
    vi.mocked(taggerApi.models).mockResolvedValueOnce({ models: document.models.map(model => model.output === "natural" ? { ...model, languages: ["en", "zh-CN"] } : model) })
    const page = await naturalPage()
    expect((page.get('.caption-output-language').element as HTMLSelectElement).value).toBe('en')
    expect((page.get('textarea').element as HTMLTextAreaElement).value).toContain('en means English')
    expect((page.get('.caption-system-prompt').element as HTMLTextAreaElement).value).not.toMatch(/[\u3400-\u9fff]/)
    await page.get('.caption-output-language').setValue('zh-CN')
    expect((page.get('textarea').element as HTMLTextAreaElement).value).toContain('请用')
    await page.get('.caption-output-language').setValue('en')
    expect((page.get('textarea').element as HTMLTextAreaElement).value).not.toMatch(/[\u3400-\u9fff]/)
    await page.get('textarea').setValue('我自己的草稿')
    await page.get('.caption-output-language').setValue('zh-CN')
    expect((page.get('textarea').element as HTMLTextAreaElement).value).toBe('我自己的草稿')
  })
  it("shows active Tag downloads beside the selected model", async () => {
    const idle = await taggerApi.status()
    vi.mocked(taggerApi.status).mockResolvedValueOnce({ ...idle, phase: "downloading", model: "wd14-convnextv2-v2", download: { ...idle.download, percent: 52, filename: "model.onnx" } })
    wrapper = mount(TaggerPage, { global: { plugins: [createPinia(), i18n], stubs: { PathPickerDialog: true } } })
    await flushPromises()
    expect(wrapper.get(".tagger-model-download").text()).toContain("52%")
    expect(wrapper.get(".tagger-model-download").text()).toContain("model.onnx")
    expect(wrapper.find(".tagger-model-selector").exists()).toBe(true)
  })
  it("submits Tag previews and batches through the same durable API with only Tag parameters", async () => {
    wrapper = mount(TaggerPage, { global: { plugins: [createPinia(), i18n], stubs: { PathPickerDialog: true } } })
    await flushPromises()
    await wrapper.get('input[placeholder="/data/datasets/images"]').setValue("D:\\samples")
    await wrapper.get('input[placeholder="/data/datasets/images/example.png"]').setValue("D:/samples/a.png")
    vi.mocked(taggerApi.captionPreview).mockResolvedValueOnce({ caption: "cat, window", tags: ["cat", "window"], language: "native" })
    await wrapper.findAll(".tagger-actions button").find(button => button.text().includes("测试当前图片"))!.trigger("click")
    await flushPromises()
    expect(wrapper.get(".caption-preview").text()).toContain("cat, window")
    await wrapper.get(".tagger-actions .primary-action").trigger("click")
    await flushPromises()
    const preview = vi.mocked(taggerApi.captionPreview).mock.calls[0][0]
    const batch = vi.mocked(taggerApi.captionStart).mock.calls[0][0]
    const { image_path, ...configuration } = preview
    expect(image_path).toBe("D:/samples/a.png")
    expect(batch).toEqual(configuration)
    expect(batch).toMatchObject({ path: "D:/samples", mode: "tag", runtime: "local", model_id: "wd14-convnextv2-v2", threshold: .35, recursive: false, conflict_action: "ignore" })
    expect(Object.keys(batch)).not.toEqual(expect.arrayContaining(["prompt", "profile_id"]))
    expect(batch).not.toHaveProperty("batch_input_recursive")
    expect(batch).not.toHaveProperty("max_tokens")
  })
  it("imports legacy presets only after confirmation and preserves the current draft", async () => {
    const config = await llmApi.profiles()
    vi.mocked(llmApi.profiles).mockResolvedValueOnce({ ...config, prompt_presets: [{ id: "legacy", name: "旧预设", template: "旧提示词", language: "zh-CN" }] })
    // Element Plus resolves confirmation actions as strings, while its type
    // declares the input-dialog data/action intersection for all shortcuts.
    vi.spyOn(ElMessageBox, "confirm").mockRejectedValueOnce("cancel").mockResolvedValueOnce("confirm" as Awaited<ReturnType<typeof ElMessageBox.confirm>>)
    vi.mocked(llmApi.importLegacyPromptPresets).mockResolvedValueOnce({ revision: "r2", presets: [{ id: "legacy", kind: "caption_prompt", name: "旧预设", template: "旧提示词", language: "zh-CN", max_length: 2000, output_format: "plain_text", model_capabilities: ["vision", "caption"], revision: "p1" }], settings: { default_caption_preset_id: null, legacy_imported: true } })
    const page = await naturalPage()
    await page.get("textarea").setValue("保留当前草稿")
    await page.get(".caption-legacy-import button").trigger("click")
    await flushPromises()
    expect(llmApi.importLegacyPromptPresets).not.toHaveBeenCalled()
    await page.get(".caption-legacy-import button").trigger("click")
    await flushPromises()
    expect(llmApi.importLegacyPromptPresets).toHaveBeenCalledWith("r1")
    expect((page.get("textarea").element as HTMLTextAreaElement).value).toBe("保留当前草稿")
    expect(page.find('.caption-preset-select option[value="legacy"]').exists()).toBe(true)
    expect(page.find(".caption-legacy-import").exists()).toBe(false)
    expect(llmApi.saveConfig).not.toHaveBeenCalled()
  })

  it("retains the draft and import entry after an import conflict", async () => {
    const config = await llmApi.profiles()
    vi.mocked(llmApi.profiles).mockResolvedValueOnce({ ...config, prompt_presets: [{ id: "legacy", name: "旧预设", template: "旧提示词", language: "zh-CN" }] })
    vi.spyOn(ElMessageBox, "confirm").mockResolvedValue("confirm" as Awaited<ReturnType<typeof ElMessageBox.confirm>>)
    vi.mocked(llmApi.importLegacyPromptPresets).mockRejectedValueOnce(new Error("revision conflict"))
    const page = await naturalPage()
    await page.get("textarea").setValue("未保存草稿")
    await page.get(".caption-legacy-import button").trigger("click")
    await flushPromises()
    expect((page.get("textarea").element as HTMLTextAreaElement).value).toBe("未保存草稿")
    expect(page.find(".caption-legacy-import").exists()).toBe(true)
    expect(page.find('.caption-preset-select option[value="legacy"]').exists()).toBe(false)
  })

  it("discards unsaved system prompt and name changes together", async () => {
    vi.mocked(llmApi.savePromptPresets).mockImplementationOnce(async update => update)
    const page = await naturalPage()
    await page.get(".caption-preset-name").setValue("保存版本")
    await page.get(".caption-system-prompt").setValue("只描述可见内容")
    await page.findAll(".caption-preset-actions button")[0].trigger("click")
    await flushPromises()
    await page.get(".caption-system-prompt").setValue("未保存系统提示词")
    await page.get(".caption-preset-name").setValue("未保存名称")
    await page.findAll(".caption-preset-actions button")[1].trigger("click")
    expect((page.get(".caption-system-prompt").element as HTMLTextAreaElement).value).toBe("只描述可见内容")
    expect((page.get(".caption-preset-name").element as HTMLInputElement).value).toBe("保存版本")
  })

  it("refreshes a conflicting revision without discarding unsaved edits", async () => {
    const page = await naturalPage()
    await page.get("textarea").setValue("并发时保留的草稿")
    await page.get(".caption-preset-name").setValue("我的名称")
    vi.mocked(llmApi.promptPresets).mockResolvedValueOnce({ presets: [], settings: {}, revision: "r2" })
    vi.mocked(llmApi.savePromptPresets).mockImplementationOnce(async update => update)
    await page.get(".caption-refresh-presets").trigger("click")
    await flushPromises()
    expect((page.get("textarea").element as HTMLTextAreaElement).value).toBe("并发时保留的草稿")
    await page.findAll(".caption-preset-actions button")[0].trigger("click")
    await flushPromises()
    expect(llmApi.savePromptPresets).toHaveBeenCalledWith(expect.objectContaining({ revision: "r2", presets: [expect.objectContaining({ name: "我的名称", template: "并发时保留的草稿" })] }))
  })

  it("loads the initial catalog when mounted inside KeepAlive", async () => {
    const host = defineComponent({ components: { TaggerPage }, template: "<KeepAlive><TaggerPage /></KeepAlive>" })
    wrapper = mount(host, { global: { plugins: [createPinia(), i18n], stubs: { PathPickerDialog: true } } })
    await flushPromises()
    expect(wrapper.find(".tagger-model-selector summary").text()).toContain("wd14-convnextv2-v2")
    expect(wrapper.findAll(".tagger-mode-tabs button").some(button => button.text() === "API 服务")).toBe(true)
  })
  it("protects unsaved prompt edits when a template switch is cancelled", async () => {
    vi.spyOn(ElMessageBox, "confirm").mockRejectedValue("cancel")
    const page = await naturalPage()
    await page.get("textarea").setValue("保留我的修改")
    await page.get(".caption-preset-select").setValue("builtin-caption-zh")
    await flushPromises()
    expect(ElMessageBox.confirm).toHaveBeenCalledOnce()
    expect((page.get("textarea").element as HTMLTextAreaElement).value).toBe("保留我的修改")
    expect((page.get(".caption-preset-select").element as HTMLSelectElement).value).toBe("builtin-caption-zh")
    expect(llmApi.savePromptPresets).not.toHaveBeenCalled()
    expect(page.text()).not.toContain("组合打标")
  })

  it("saves edited built-in templates as user copies", async () => {
    vi.mocked(llmApi.savePromptPresets).mockImplementationOnce(async update => update)
    const page = await naturalPage()
    await page.get(".caption-preset-select").setValue("builtin-caption-zh")
    await flushPromises()
    await page.get("textarea").setValue("我的模板 {{language}}")
    await page.findAll(".caption-preset-actions button")[0].trigger("click")
    await flushPromises()
    const saved = vi.mocked(llmApi.savePromptPresets).mock.calls[0][0]
    expect(saved.presets[0].id).not.toBe("builtin-caption-zh")
    expect(saved.presets[0].template).toBe("我的模板 {{language}}")
    expect(saved.revision).toBe("r1")
  })

  it("selects API vision by model capability and excludes text-only models", async () => {
    const page = await naturalPage()
    expect(page.findAll('[data-model-id="llm:remote"]')).toHaveLength(1)
    expect(page.findAll('[data-model-id="llm:local"]')).toHaveLength(0)
    expect(page.text()).not.toContain("Text only")
    expect(page.find(".tagger-model-selector summary").text()).toContain("remote-vision")
    expect(llmApi.localVisionStatus).toHaveBeenCalledOnce()
  })

  it("submits edited prompt through the caption API with local fallback off by default", async () => {
    const page = await naturalPage()
    await page.get('input[placeholder="/data/datasets/images"]').setValue("D:/sample")
    await page.get("textarea").setValue("只描述主体，使用{{language}}")
    await page.get(".tagger-actions .primary-action").trigger("click")
    await flushPromises()
    expect(taggerApi.captionStart).toHaveBeenCalledWith(expect.objectContaining({
      path: "D:/sample", mode: "natural", prompt: "只描述主体，使用{{language}}", profile_id: "remote",
    }))
    const submitted = vi.mocked(taggerApi.captionStart).mock.calls[0][0]
    if (submitted.mode !== "natural") throw new Error("Expected natural Caption request")
    expect(submitted.allow_local_fallback).toBeFalsy()
    expect(submitted.runtime).toBe("api")
    expect(submitted.model_id).toBe("llm:remote")
    expect(submitted).not.toHaveProperty("threshold")
    expect(submitted).not.toHaveProperty("interrogator_model")
  })

  it("previews a single image through the preview endpoint without starting a batch", async () => {
    const page = await naturalPage()
    await page.get('input[placeholder="/data/datasets/images/example.png"]').setValue("D:/sample/a.png")
    await page.findAll(".tagger-actions .secondary-action").at(-1)!.trigger("click")
    await flushPromises()
    expect(taggerApi.captionPreview).toHaveBeenCalledOnce()
    expect(taggerApi.captionStart).not.toHaveBeenCalled()
    expect(page.get(".caption-preview").text()).toContain("一只猫。")
  })

  it("saves a named prompt preset and discards later edits", async () => {
    const page = await naturalPage()
    vi.mocked(llmApi.savePromptPresets).mockImplementationOnce(async update => ({ ...update, presets: update.presets, settings: update.settings }))
    await page.get(".caption-preset-name").setValue("主体描述")
    await page.get("textarea").setValue("只描述主体 {{language}}")
    await page.findAll(".caption-preset-actions button")[0].trigger("click")
    await flushPromises()
    expect(llmApi.savePromptPresets).toHaveBeenCalledWith(expect.objectContaining({ presets: [expect.objectContaining({ kind: "caption_prompt", name: "主体描述", template: "只描述主体 {{language}}", language: "zh-CN" })] }))
    await page.get("textarea").setValue("未保存的修改")
    await page.findAll(".caption-preset-actions button")[1].trigger("click")
    expect((page.get("textarea").element as HTMLTextAreaElement).value).toBe("只描述主体 {{language}}")
    expect(taggerApi.captionStart).not.toHaveBeenCalled()
  })

  it("keeps the saved length limit when discarding prompt changes", async () => {
    const page = await naturalPage()
    vi.mocked(llmApi.savePromptPresets).mockImplementationOnce(async update => ({ ...update, presets: update.presets, settings: update.settings }))
    await page.get(".caption-preset-name").setValue("简洁")
    await page.get(".caption-max-length").setValue("40")
    await page.findAll(".caption-preset-actions button")[0].trigger("click")
    await flushPromises()
    await page.get(".caption-max-length").setValue("120")
    await page.findAll(".caption-preset-actions button")[1].trigger("click")
    expect((page.get(".caption-max-length").element as HTMLInputElement).value).toBe("40")
  })

  it("does not submit or save an invalid caption length limit", async () => {
    const page = await naturalPage()
    await page.get('input[placeholder="/data/datasets/images"]').setValue("D:/sample")
    await page.get(".caption-max-length").setValue("0")
    await page.get(".tagger-actions .primary-action").trigger("click")
    await page.findAll(".caption-preset-actions button")[0].trigger("click")
    await flushPromises()
    expect(taggerApi.captionStart).not.toHaveBeenCalled()
    expect(llmApi.savePromptPresets).not.toHaveBeenCalled()
  })

  it("offers only model-supported output languages", async () => {
    const page = await naturalPage()
    const language = page.get(".caption-output-language")
    expect(language.findAll("option").map(option => option.attributes("value"))).toEqual(["zh-CN"])
    expect((page.get(".tagger-actions .primary-action").element as HTMLButtonElement).disabled).toBe(false)
    expect(page.text()).toContain("remote-vision")
  })

  it("does not show an API tab when the model catalog has no ready API models", async () => {
    const baseline = await taggerApi.models()
    vi.mocked(taggerApi.models).mockResolvedValueOnce({ models: baseline.models.filter(model => model.runtime === "local") })
    wrapper = mount(TaggerPage, { global: { plugins: [createPinia(), i18n], stubs: { PathPickerDialog: true } } })
    await flushPromises()
    expect(wrapper.findAll(".tagger-mode-tabs button").some(button => button.text() === "API 服务")).toBe(false)
    expect(wrapper.findAll(".tagger-mode-tabs button").some(button => button.text() === "本地模型")).toBe(true)
  })

  it("preserves each Caption model's settings across runtime switches", async () => {
    const page = await naturalPage()
    await page.get("textarea").setValue("远程提示词")
    await page.findAll(".tagger-mode-tabs button")[0].trigger("click")
    await page.get('[data-model-id="llm:local"]').trigger("click")
    await page.get("textarea").setValue("本地提示词")
    await page.findAll(".tagger-mode-tabs button")[1].trigger("click")
    expect((page.get("textarea").element as HTMLTextAreaElement).value).toBe("远程提示词")
    await page.findAll(".tagger-mode-tabs button")[0].trigger("click")
    await page.get('[data-model-id="llm:local"]').trigger("click")
    expect((page.get("textarea").element as HTMLTextAreaElement).value).toBe("本地提示词")
  })

  it("disables repeat previews while an inference request is pending", async () => {
    let finish!: () => void
    const pending = new Promise<void>(resolve => { finish = resolve })
    vi.mocked(taggerApi.captionPreview).mockImplementationOnce(async () => {
      await pending
      return { caption: "一只猫。", language: "zh-CN", profile_id: "remote", profile_revision: "rev" }
    })
    const page = await naturalPage()
    await page.get('input[placeholder="/data/datasets/images/example.png"]').setValue("D:/sample/a.png")
    const button = page.findAll(".tagger-actions button").find(item => item.text().includes("测试当前图片"))!
    await button.trigger("click")
    expect((button.element as HTMLButtonElement).disabled).toBe(true)
    await button.trigger("click")
    expect(taggerApi.captionPreview).toHaveBeenCalledOnce()
    finish()
    await flushPromises()
    expect((button.element as HTMLButtonElement).disabled).toBe(false)
  })

  it("shows recovered failures and exposes retry without rewriting completed files", async () => {
    vi.mocked(taggerApi.captionStatus).mockResolvedValueOnce({ job_id: "recovered", phase: "error", mode: "natural", message: "recovered", current: 1, total: 2, filename: "", succeeded: 1, failed: 1, cancelled: 0, errors: [{ filename: "b.png", code: "caption_interrupted", message: "未完成" }], updated_at: 1, recovered: true })
    vi.mocked(taggerApi.captionRetryFailed).mockResolvedValueOnce({ job_id: "retry", phase: "pending", mode: "natural", message: "retry", current: 0, total: 1, filename: "", succeeded: 0, failed: 0, cancelled: 0, errors: [], updated_at: 2 })
    const page = await naturalPage()
    expect(page.text()).toContain("已恢复上次任务")
    const retry = page.findAll(".tagger-actions button").find(button => button.text().includes("重试失败项"))!
    await retry.trigger("click")
    await flushPromises()
    expect(taggerApi.captionRetryFailed).toHaveBeenCalledOnce()
    expect(taggerApi.captionStart).not.toHaveBeenCalled()
  })

  it("loads a historical report with actual profile revisions and write hashes", async () => {
    vi.mocked(taggerApi.captionHistory).mockResolvedValueOnce({ jobs: [{ job_id: "old-job", phase: "done", mode: "natural", message: "", current: 1, total: 1, filename: "", succeeded: 1, failed: 0, cancelled: 0, errors: [], updated_at: 1 }] })
    vi.mocked(taggerApi.captionReport).mockResolvedValueOnce({ job_id: "old-job", phase: "done", snapshot: {}, report: { items: [{ filename: "a.png", status: "written", profile_id: "remote", profile_revision: "profile-rev", before_hash: "before-sha", after_hash: "after-sha" }] } })
    const page = await naturalPage()
    await page.get(".caption-history select").setValue("old-job")
    await flushPromises()
    expect(taggerApi.captionReport).toHaveBeenCalledWith("old-job")
    expect(page.get(".caption-report").text()).toContain("profile-rev")
    expect(page.get(".caption-report").text()).toContain("before-sha → after-sha")
  })

  it("shows errors from older recovered reports even when they lack an error code", async () => {
    vi.mocked(taggerApi.captionReport).mockResolvedValueOnce({ job_id: "old-interrupted", phase: "error", snapshot: {}, report: { items: [{ filename: "a.png", status: "interrupted", error: "服务重启前未完成此图片，可重试" }] } })
    const page = await naturalPage()
    vi.mocked(taggerApi.captionHistory).mockResolvedValueOnce({ jobs: [{ job_id: "old-interrupted", phase: "error", mode: "natural", message: "", current: 0, total: 1, filename: "", succeeded: 0, failed: 1, cancelled: 0, errors: [], updated_at: 1 }] })
    await page.get(".caption-history button").trigger("click")
    await flushPromises()
    await page.get(".caption-history select").setValue("old-interrupted")
    await flushPromises()
    expect(page.get(".caption-report").text()).toContain("服务重启前未完成此图片，可重试")
  })

  it("requires confirmation before rollback and exposes partial conflicts", async () => {
    vi.spyOn(ElMessageBox, "confirm").mockImplementation(vi.fn().mockResolvedValue("confirm"))
    vi.mocked(taggerApi.captionHistory).mockResolvedValueOnce({ jobs: [{ job_id: "done", phase: "done", mode: "natural", message: "", current: 1, total: 1, filename: "", succeeded: 1, failed: 0, cancelled: 0, errors: [], updated_at: 1 }] })
    vi.mocked(taggerApi.captionReport).mockResolvedValue({ job_id: "done", phase: "done", snapshot: {}, report: { items: [{ filename: "a.png", status: "written" }] } })
    vi.mocked(taggerApi.captionRollback).mockResolvedValue({ job_id: "done", restored: 0, conflicts: 1, skipped: 0, items: [{ filename: "a.png", status: "conflict", code: "caption_conflict" }] })
    const page = await naturalPage()
    await page.get(".caption-history select").setValue("done")
    await flushPromises()
    expect(taggerApi.captionRollback).not.toHaveBeenCalled()
    await page.get(".caption-maintenance button").trigger("click")
    await flushPromises()
    expect(ElMessageBox.confirm).toHaveBeenCalled()
    expect(taggerApi.captionRollback).toHaveBeenCalledWith("done")
    expect(page.get(".caption-report").text()).toContain("冲突保留 1")
  })
})
