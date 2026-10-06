// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest"
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils"
import { createPinia } from "pinia"
import TaggerPage from "./TaggerPage.vue"
import { i18n } from "../i18n"
import { llmApi } from "../api/llm"
import { taggerApi } from "../api/tagger"

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
  },
}))
vi.mock("../api/tagger", () => ({
  taggerApi: {
    status: vi.fn(),
    captionStatus: vi.fn(),
    captionStart: vi.fn().mockResolvedValue({
      job_id: "job", phase: "pending", mode: "natural", message: "", current: 0, total: 1,
      filename: "", succeeded: 0, failed: 0, cancelled: 0, errors: [], updated_at: 0,
    }),
    captionPreview: vi.fn().mockResolvedValue({ caption: "一只猫。", language: "zh-CN", profile_id: "remote", profile_revision: "rev" }),
    captionCancel: vi.fn(),
    captionRetryFailed: vi.fn(),
  },
}))

let wrapper: VueWrapper | undefined
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.clearAllMocks()
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
    const config = await llmApi.profiles()
    vi.mocked(llmApi.saveConfig).mockImplementationOnce(async update => ({ ...config, ...update }))
    await page.get(".caption-preset-name").setValue("主体描述")
    await page.get("textarea").setValue("只描述主体 {{language}}")
    await page.findAll(".caption-preset-actions button")[0].trigger("click")
    await flushPromises()
    expect(llmApi.saveConfig).toHaveBeenCalledWith({ prompt_presets: [expect.objectContaining({ name: "主体描述", template: "只描述主体 {{language}}", language: "zh-CN" })] })
    await page.get("textarea").setValue("未保存的修改")
    await page.findAll(".caption-preset-actions button")[1].trigger("click")
    expect((page.get("textarea").element as HTMLTextAreaElement).value).toBe("只描述主体 {{language}}")
    expect(taggerApi.captionStart).not.toHaveBeenCalled()
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
})
