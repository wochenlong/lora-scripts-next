// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest"
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils"
import { defineComponent } from "vue"
import LlmSettingsDialog from "./LlmSettingsDialog.vue"
import { i18n } from "../i18n"
import { llmApi, type LlmConfig } from "../api/llm"

vi.mock("../api/llm", () => ({ llmApi: { config: vi.fn(), saveConfig: vi.fn(), connectionTest: vi.fn() } }))
const Dialog = defineComponent({ props: { modelValue: { type: Boolean, required: true } }, template: '<div v-if="modelValue"><slot /><slot name="footer" /></div>' })
let page: VueWrapper | undefined
const config = (): LlmConfig => ({ version: 5, routes: { translation: "text", caption: "vision" }, prompt_presets: [], cache: {},
  profiles: [
    { id: "text", name: "Text only", model: "text", endpoint: "https://example.test/chat/completions", source: "remote", capabilities: ["text"], languages: ["zh-CN"], api_key: "********", api_key_configured: true, enabled: true, ready: true },
    { id: "vision", name: "Vision", model: "vision", endpoint: "https://example.test/chat/completions", source: "remote", capabilities: ["text", "vision"], languages: ["zh-CN"], api_key: "********", api_key_configured: true, enabled: true, ready: true },
  ] })

async function open(capability: "text" | "vision" = "vision") {
  vi.mocked(llmApi.config).mockResolvedValue(config())
  page = mount(LlmSettingsDialog, { props: { modelValue: true, capability, imagePath: "D:/public/a.png" }, global: { plugins: [i18n], stubs: { ElDialog: Dialog } } })
  await flushPromises()
  return page
}

afterEach(() => { page?.unmount(); vi.resetAllMocks() })

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
    expect(llmApi.connectionTest).toHaveBeenCalledWith({ capability: "vision", profile_id: "vision", image_path: "D:/public/a.png" })
    await wrapper.get('[data-profile-id="vision"] .llm-profile-name').setValue("Draft")
    expect((button.element as HTMLButtonElement).disabled).toBe(true)
    expect(wrapper.text()).toContain("请先保存修改")
  })
})
