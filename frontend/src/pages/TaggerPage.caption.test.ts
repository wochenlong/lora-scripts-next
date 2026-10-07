// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest"
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils"
import { createPinia } from "pinia"
import TaggerPage from "./TaggerPage.vue"
import { i18n } from "../i18n"
import { llmApi } from "../api/llm"
import { taggerApi } from "../api/tagger"
import { ElMessageBox } from "element-plus"

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
  },
}))
vi.mock("../api/tagger", () => ({
  taggerApi: {
    status: vi.fn(),
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
  await wrapper.findAll(".tagger-mode-tabs button")[1].trigger("click")
  await flushPromises()
  return wrapper
}

describe("natural-language TaggerPage", () => {
  it("protects unsaved prompt edits when a template switch is cancelled", async () => {
    vi.spyOn(ElMessageBox, "confirm").mockRejectedValue("cancel")
    const page = await naturalPage()
    await page.get("textarea").setValue("保留我的修改")
    await page.get(".caption-preset-select").setValue("builtin-caption-zh")
    await flushPromises()
    expect(ElMessageBox.confirm).toHaveBeenCalledOnce()
    expect((page.get("textarea").element as HTMLTextAreaElement).value).toBe("保留我的修改")
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

  it("filters text-only profiles and lists remote vision first", async () => {
    const page = await naturalPage()
    const options = page.findAll('select option').filter(option => ["remote", "local", "text"].includes(String(option.attributes("value"))))
    expect(options.map(option => option.attributes("value"))).toEqual(["remote", "local"])
    expect(page.text()).toContain("1.55 GB")
    expect(page.text()).toContain("3.1 GB")
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
    expect(submitted.allow_local_fallback).toBeFalsy()
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

  it("rejects profiles that do not support the selected output language", async () => {
    const page = await naturalPage()
    const language = page.findAll("select").find(select => select.find('option[value="ja"]').exists())!
    await language.setValue("en")
    expect((page.get(".tagger-actions .primary-action").element as HTMLButtonElement).disabled).toBe(true)
    expect(page.findAll('option[value="remote"]')).toHaveLength(0)
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
