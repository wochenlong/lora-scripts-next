// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest"
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils"
import { defineComponent } from "vue"
import LlmSettingsDialog from "./LlmSettingsDialog.vue"
import { i18n } from "../i18n"
import { llmApi, type LlmConfig } from "../api/llm"

vi.mock("../api/llm", () => ({
  llmApi: { config: vi.fn(), saveConfig: vi.fn(), connectionTest: vi.fn(), localVisionStatus: vi.fn(), localVisionAction: vi.fn() },
  isVerifiedProfile: (profile: { enabled: boolean; ready: boolean; capabilities: string[]; verified_capabilities?: string[] }, capability: string) => Boolean(profile.enabled && profile.ready && profile.capabilities.includes(capability) && profile.verified_capabilities?.includes(capability)),
}))
const Dialog = defineComponent({ props: { modelValue: { type: Boolean, required: true } }, template: '<div v-if="modelValue"><slot /><slot name="footer" /></div>' })
let page: VueWrapper | undefined
const config = (): LlmConfig => ({ version: 5, routes: { translation: "text", caption: "vision" }, prompt_presets: [], cache: {},
  profiles: [
    { id: "text", name: "Text only", model: "text", endpoint: "https://example.test/chat/completions", source: "remote", capabilities: ["text"], languages: ["zh-CN"], api_key: "********", api_key_configured: true, enabled: true, ready: true, verified_capabilities: ["text"] },
    { id: "vision", name: "Vision", model: "vision", endpoint: "https://example.test/chat/completions", source: "remote", capabilities: ["text", "vision"], languages: ["zh-CN"], api_key: "********", api_key_configured: true, enabled: true, ready: true, verified_capabilities: ["text", "vision"] },
  ] })

async function open(capability: "text" | "vision" = "vision") {
  vi.mocked(llmApi.config).mockResolvedValue(config())
  vi.mocked(llmApi.localVisionStatus).mockResolvedValue({ state: "missing", installed: false, downloaded_bytes: 0, total_bytes: 0 })
  page = mount(LlmSettingsDialog, { props: { modelValue: true, capability, imagePath: "D:/public/a.png" }, global: { plugins: [i18n], stubs: { ElDialog: Dialog } } })
  await flushPromises()
  return page
}

afterEach(() => { page?.unmount(); vi.resetAllMocks(); vi.useRealTimers() })

describe("shared LLM settings", () => {
  it("allows text-only translation while the caption route contains only vision", async () => {
    const wrapper = await open("text")
    const selectors = wrapper.findAll("select")
    expect(selectors[0].findAll("option").map(option => option.attributes("value"))).toEqual(["", "text", "vision"])
    expect(selectors[1].findAll("option").map(option => option.attributes("value"))).toEqual(["", "vision"])
    const textCard = wrapper.get('[data-profile-id="text"]')
    expect((textCard.findAll("button")[0].element as HTMLButtonElement).disabled).toBe(false)
  })

  it("discards edited profiles and runtime key input on cancel without saving", async () => {
    const wrapper = await open()
    await wrapper.get('[data-profile-id="vision"] .llm-profile-name').setValue("Unsaved")
    await wrapper.get('[data-profile-id="vision"] input[type="password"]').setValue("transient-fixture-value")
    await wrapper.get(".llm-cancel").trigger("click")
    expect(llmApi.saveConfig).not.toHaveBeenCalled()
    expect(wrapper.emitted("update:modelValue")).toEqual([[false]])
    await wrapper.setProps({ modelValue: false })
    await wrapper.setProps({ modelValue: true })
    await flushPromises()
    expect((wrapper.get('[data-profile-id="vision"] .llm-profile-name').element as HTMLInputElement).value).toBe("Vision")
    expect((wrapper.get('[data-profile-id="vision"] input[type="password"]').element as HTMLInputElement).value).toBe("********")
  })

  it("saves the shared profiles and routes without overwriting concurrent presets", async () => {
    const wrapper = await open()
    vi.mocked(llmApi.saveConfig).mockResolvedValue(config())
    await wrapper.get('[data-profile-id="vision"] .llm-profile-name').setValue("Changed")
    await wrapper.get(".llm-save").trigger("click")
    await flushPromises()
    const payload = vi.mocked(llmApi.saveConfig).mock.calls[0][0]
    expect(payload.profiles?.find(profile => profile.id === "vision")?.name).toBe("Changed")
    expect(payload.profiles?.find(profile => profile.id === "text")?.api_key).toBe("********")
    expect(payload).not.toHaveProperty("prompt_presets")
    expect(wrapper.emitted("saved")).toHaveLength(1)
  })

  it("tests exactly the saved selected vision profile and requires saving edits first", async () => {
    const wrapper = await open()
    vi.mocked(llmApi.connectionTest).mockResolvedValue({ ok: true })
    const button = wrapper.get('[data-profile-id="vision"]').findAll("button")[0]
    await button.trigger("click")
    await flushPromises()
    expect(llmApi.connectionTest).toHaveBeenCalledWith({ profile_id: "vision" })
    await wrapper.get('[data-profile-id="vision"] .llm-profile-name').setValue("Draft")
    expect((button.element as HTMLButtonElement).disabled).toBe(true)
    expect(wrapper.text()).toContain("请先保存修改")
  })

  it("shares the vision asset controls with translation without an automatic download", async () => {
    vi.useFakeTimers()
    const wrapper = await open("text")
    expect(wrapper.get(".llm-managed-profile").text()).toContain("Qwen3.5-2B")
    expect(llmApi.localVisionAction).not.toHaveBeenCalled()
    vi.mocked(llmApi.localVisionStatus).mockImplementation(() => new Promise(() => {}))
    vi.advanceTimersByTime(1200)
    const signal = vi.mocked(llmApi.localVisionStatus).mock.calls.at(-1)?.[0]
    await wrapper.get(".llm-cancel").trigger("click")
    expect(signal?.aborted).toBe(true)
  })

  it("keeps unsaved profile inputs when a runtime action refreshes the managed profile", async () => {
    const wrapper = await open("text")
    await wrapper.get('[data-profile-id="text"] .llm-profile-name').setValue("Unsaved name")
    const updated = config()
    updated.profiles.push({ ...updated.profiles[1], id: "qwen3.5-2b-local", source: "managed-local", asset_id: "qwen3.5-2b-local" })
    vi.mocked(llmApi.config).mockResolvedValue(updated)
    vi.mocked(llmApi.localVisionAction).mockResolvedValue({ state: "running", installed: true, runtime_installed: true, downloaded_bytes: 0, total_bytes: 0 })
    await wrapper.get(".managed-vision-model button").trigger("click")
    await flushPromises()
    expect(llmApi.localVisionAction).toHaveBeenCalledWith("setup")
    expect((wrapper.get('[data-profile-id="text"] .llm-profile-name').element as HTMLInputElement).value).toBe("Unsaved name")
    expect(wrapper.find('[data-profile-id="qwen3.5-2b-local"]').exists()).toBe(true)
    expect(llmApi.saveConfig).not.toHaveBeenCalled()
  })

  it("blocks saving an empty draft when the shared configuration failed to load", async () => {
    const wrapper = await open()
    await wrapper.setProps({ modelValue: false })
    vi.mocked(llmApi.config).mockRejectedValue(new Error("Configuration unreadable"))
    await wrapper.setProps({ modelValue: true })
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain("Configuration unreadable")
    expect((wrapper.get(".llm-save").element as HTMLButtonElement).disabled).toBe(true)
    await wrapper.get(".llm-save").trigger("click")
    expect(llmApi.saveConfig).not.toHaveBeenCalled()
  })

  it("keeps the translation prompt internal while allowing reasoning without changing caption presets", async () => {
    const wrapper = await open("text")
    vi.mocked(llmApi.saveConfig).mockResolvedValue(config())
    expect(wrapper.find(".llm-translation-prompt").exists()).toBe(false)
    expect(wrapper.find(".llm-capabilities").exists()).toBe(false)
    await wrapper.get('[data-profile-id="text"] .llm-reasoning').setValue("high")
    await wrapper.get(".llm-save").trigger("click")
    await flushPromises()
    const payload = vi.mocked(llmApi.saveConfig).mock.calls[0][0]
    expect(payload.profiles?.find(profile => profile.id === "text")?.metadata).toEqual({ reasoning_effort: "high" })
    expect(payload).not.toHaveProperty("prompt_presets")
  })

  it("starts with collapsed model cards and enabled advanced defaults, saving an explicit fallback disable", async () => {
    const wrapper = await open()
    for (const card of wrapper.findAll(".llm-profile-card")) expect(card.attributes("open")).toBeUndefined()
    expect(wrapper.get(".llm-advanced-settings").attributes("open")).toBeUndefined()
    expect((wrapper.get(".llm-translation-cache").element as HTMLInputElement).checked).toBe(true)
    expect((wrapper.get(".llm-caption-cache").element as HTMLInputElement).checked).toBe(true)
    expect((wrapper.get(".llm-local-fallback").element as HTMLInputElement).checked).toBe(true)
    vi.mocked(llmApi.saveConfig).mockResolvedValue(config())
    await wrapper.get(".llm-local-fallback").setValue(false)
    await wrapper.get(".llm-save").trigger("click")
    await flushPromises()
    expect(vi.mocked(llmApi.saveConfig).mock.calls[0][0].local_fallback_enabled).toBe(false)
  })

  it("detects all capabilities without requiring a user image and refreshes verified routes", async () => {
    const wrapper = await open()
    expect(wrapper.find(".llm-test-image").exists()).toBe(false)
    const updated = config()
    updated.profiles[0].capabilities = ["text", "vision"]
    updated.profiles[0].verified_capabilities = ["text", "vision"]
    vi.mocked(llmApi.config).mockResolvedValue(updated)
    vi.mocked(llmApi.connectionTest).mockResolvedValue({ ok: true })
    await wrapper.get('[data-profile-id="text"]').findAll("button")[0].trigger("click")
    await flushPromises()
    expect(llmApi.connectionTest).toHaveBeenCalledWith({ profile_id: "text" })
    expect(wrapper.findAll("select")[1].findAll("option").map(option => option.attributes("value"))).toContain("text")
  })

  it("reports a text-only detection as unavailable for image captioning", async () => {
    const wrapper = await open()
    vi.mocked(llmApi.connectionTest).mockResolvedValue({ verified_capabilities: ["text"], vision_error_code: "unsupported_content" })
    await wrapper.get('[data-profile-id="text"]').findAll("button")[0].trigger("click")
    await flushPromises()
    const result = wrapper.findAll('[role="status"]').find(item => item.text().includes("Text only"))
    expect(result?.text()).toContain("文本")
    expect(result?.text()).toContain("不能用于图像打标")
    expect(result?.text()).not.toContain("unsupported_content")
  })

  it("renders the same editor inline without closing after save", async () => {
    const wrapper = await open("text")
    await wrapper.setProps({ embedded: true })
    vi.mocked(llmApi.saveConfig).mockResolvedValue(config())
    await wrapper.get(".llm-save").trigger("click")
    await flushPromises()
    expect(llmApi.saveConfig).toHaveBeenCalledOnce()
    expect(wrapper.emitted("update:modelValue")).toBeUndefined()
    expect(wrapper.find(".llm-settings").exists()).toBe(true)
    expect(wrapper.find(".llm-cancel").exists()).toBe(false)
  })
})
