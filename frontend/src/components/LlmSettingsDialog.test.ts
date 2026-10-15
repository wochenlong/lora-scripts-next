// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest"
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils"
import { defineComponent } from "vue"
import { ElMessageBox } from "element-plus"
import LlmSettingsDialog from "./LlmSettingsDialog.vue"
import { i18n } from "../i18n"
import { llmApi, type LlmConfig } from "../api/llm"

const configureCache = vi.hoisted(() => vi.fn())
vi.mock("../composables/useTagTranslations", () => ({ useTagTranslations: () => ({ configureCache }) }))

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

async function open() {
  vi.mocked(llmApi.config).mockResolvedValue(config())
  vi.mocked(llmApi.localVisionStatus).mockResolvedValue({ state: "missing", installed: false, downloaded_bytes: 0, total_bytes: 0 })
  page = mount(LlmSettingsDialog, { props: { modelValue: true }, global: { plugins: [i18n], stubs: { ElDialog: Dialog } } })
  await flushPromises()
  return page
}

afterEach(() => { page?.unmount(); vi.resetAllMocks(); vi.restoreAllMocks(); vi.useRealTimers() })

describe("shared LLM settings", () => {
  it("publishes the shared browser cache policy from every manager save", async () => {
    const wrapper = await open()
    expect(configureCache).toHaveBeenCalledWith(true, expect.any(String))
    const saved = config()
    saved.revision = "caption-manager-save"
    saved.cache.translation = false
    vi.mocked(llmApi.saveConfig).mockResolvedValue(saved)
    await wrapper.get(".llm-save").trigger("click")
    await flushPromises()
    expect(configureCache).toHaveBeenLastCalledWith(false, "caption-manager-save")
  })

  it("blocks concurrent masked credential changes even when server display values match", async () => {
    const wrapper = await open()
    const initial = config()
    initial.revision = "credential-baseline"
    initial.profiles[1]!.secret_revision = 1
    vi.mocked(llmApi.config).mockResolvedValue(initial)
    await wrapper.setProps({ modelValue: false })
    await wrapper.setProps({ modelValue: true })
    await flushPromises()
    await wrapper.get('[data-profile-id="vision"] input[type="password"]').setValue("fixture-local-replacement")
    const latest = JSON.parse(JSON.stringify(initial)) as LlmConfig
    latest.revision = "credential-changed-elsewhere"
    latest.profiles[1]!.secret_revision = 2
    vi.mocked(llmApi.config).mockResolvedValue(latest)
    vi.mocked(llmApi.localVisionAction).mockResolvedValue({ state: "running", installed: true, downloaded_bytes: 0, total_bytes: 0 })
    await wrapper.get(".managed-vision-model button").trigger("click")
    await flushPromises()
    expect((wrapper.get(".llm-save").element as HTMLButtonElement).disabled).toBe(true)
    expect((wrapper.get('[data-profile-id="vision"] input[type="password"]').element as HTMLInputElement).value).toBe("fixture-local-replacement")
    expect(wrapper.get('[role="alert"]').text()).toContain(i18n.global.t("llm.runtimeConfigConflict"))
    expect(llmApi.saveConfig).not.toHaveBeenCalled()
  })

  it("absorbs a masked credential rotation when the local key was not edited", async () => {
    const wrapper = await open()
    const latest = config()
    latest.revision = "credential-rotation"
    latest.profiles[1]!.secret_revision = 2
    vi.mocked(llmApi.config).mockResolvedValue(latest)
    vi.mocked(llmApi.localVisionAction).mockResolvedValue({ state: "running", installed: true, downloaded_bytes: 0, total_bytes: 0 })
    await wrapper.get(".managed-vision-model button").trigger("click")
    await flushPromises()
    expect((wrapper.get(".llm-save").element as HTMLButtonElement).disabled).toBe(false)
    vi.mocked(llmApi.saveConfig).mockResolvedValue(latest)
    await wrapper.get(".llm-save").trigger("click")
    await flushPromises()
    expect(llmApi.saveConfig).toHaveBeenCalledWith(expect.objectContaining({ revision: "credential-rotation", profiles: expect.arrayContaining([expect.objectContaining({ id: "vision", api_key: "********", secret_revision: 2 })]) }))
  })
  it("allows text-only translation while the caption route contains only vision", async () => {
    const wrapper = await open()
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
    const wrapper = await open()
    expect(wrapper.get(".llm-managed-profile").text()).toContain("Qwen3.5-2B")
    expect(llmApi.localVisionAction).not.toHaveBeenCalled()
    vi.mocked(llmApi.localVisionStatus).mockImplementation(() => new Promise(() => {}))
    vi.advanceTimersByTime(1200)
    const signal = vi.mocked(llmApi.localVisionStatus).mock.calls.at(-1)?.[0]
    await wrapper.get(".llm-cancel").trigger("click")
    expect(signal?.aborted).toBe(true)
  })

  it("publishes a completed background installation while preserving edits made during its config refresh", async () => {
    vi.useFakeTimers()
    const wrapper = await open()
    vi.mocked(llmApi.localVisionAction).mockResolvedValue({ state: "downloading", installed: false, downloaded_bytes: 0, total_bytes: 100 })
    await wrapper.get(".managed-vision-model button").trigger("click")
    await flushPromises()
    let finishRefresh!: (value: LlmConfig) => void
    vi.mocked(llmApi.config).mockImplementationOnce(() => new Promise(resolve => { finishRefresh = resolve }))
    vi.mocked(llmApi.localVisionStatus).mockResolvedValue({ state: "running", installed: true, runtime_installed: true, model_id: "qwen3.5-2b-local", port: 28000, downloaded_bytes: 100, total_bytes: 100 })
    vi.advanceTimersByTime(1200)
    await flushPromises()
    expect((wrapper.get(".llm-save").element as HTMLButtonElement).disabled).toBe(true)
    await wrapper.get('[data-profile-id="text"] .llm-profile-name').setValue("Draft typed during refresh")
    await wrapper.get(".llm-settings select").setValue("vision")
    await wrapper.get(".llm-caption-cache").setValue(false)
    await wrapper.get(".llm-local-fallback").setValue(false)
    const ready = config()
    ready.revision = "background-install-ready"
    ready.profiles[0]!.endpoint = "https://external-update.example.test/chat/completions"
    ready.profiles.push({ ...ready.profiles[1]!, id: "qwen3.5-2b-local", source: "managed-local", asset_id: "qwen3.5-2b-local" })
    finishRefresh(ready)
    await flushPromises()
    expect(wrapper.find('[data-profile-id="qwen3.5-2b-local"]').exists()).toBe(true)
    expect((wrapper.get('[data-profile-id="text"] .llm-profile-name').element as HTMLInputElement).value).toBe("Draft typed during refresh")
    expect(wrapper.emitted("saved")?.at(-1)).toEqual([ready])
    expect(llmApi.saveConfig).not.toHaveBeenCalled()
    const refreshCount = vi.mocked(llmApi.config).mock.calls.length
    vi.advanceTimersByTime(2400)
    await flushPromises()
    expect(llmApi.config).toHaveBeenCalledTimes(refreshCount)
    vi.mocked(llmApi.saveConfig).mockResolvedValue(ready)
    await wrapper.get(".llm-save").trigger("click")
    await flushPromises()
    expect(vi.mocked(llmApi.saveConfig).mock.calls[0]![0]).toMatchObject({ revision: "background-install-ready", routes: { translation: "vision" }, cache: { caption: false }, local_fallback_enabled: false })
    expect(vi.mocked(llmApi.saveConfig).mock.calls[0]![0].profiles!.find(profile => profile.id === "text")).toMatchObject({ name: "Draft typed during refresh", endpoint: "https://external-update.example.test/chat/completions" })
  })

  it("preserves a conflicting draft and its original CAS revision after a background readiness refresh", async () => {
    vi.useFakeTimers()
    const wrapper = await open()
    await wrapper.get('[data-profile-id="text"] .llm-profile-name').setValue("Unsaved conflicting name")
    const ready = config()
    ready.revision = "conflicting-background-install"
    ready.profiles[0]!.name = "Name saved by another tab"
    ready.profiles.push({ ...ready.profiles[1]!, id: "qwen3.5-2b-local", source: "managed-local", asset_id: "qwen3.5-2b-local" })
    vi.mocked(llmApi.config).mockResolvedValue(ready)
    vi.mocked(llmApi.localVisionStatus).mockResolvedValue({ state: "running", installed: true, runtime_installed: true, downloaded_bytes: 100, total_bytes: 100 })
    vi.advanceTimersByTime(1200)
    await flushPromises()
    expect((wrapper.get('[data-profile-id="text"] .llm-profile-name').element as HTMLInputElement).value).toBe("Unsaved conflicting name")
    expect(wrapper.get('[role="alert"]').text()).toContain(i18n.global.t("llm.runtimeConfigConflict"))
    expect((wrapper.get(".llm-save").element as HTMLButtonElement).disabled).toBe(true)
    await wrapper.get(".llm-save").trigger("click")
    expect(llmApi.saveConfig).not.toHaveBeenCalled()
    expect(wrapper.emitted("saved")?.at(-1)).toEqual([ready])
  })

  it("discards an old readiness refresh after closing and reopening the manager", async () => {
    vi.useFakeTimers()
    const wrapper = await open()
    let finishOldRefresh!: (value: LlmConfig) => void
    vi.mocked(llmApi.config).mockImplementationOnce(() => new Promise(resolve => { finishOldRefresh = resolve }))
    vi.mocked(llmApi.localVisionStatus).mockResolvedValue({ state: "running", installed: true, downloaded_bytes: 100, total_bytes: 100 })
    vi.advanceTimersByTime(1200)
    await flushPromises()
    await wrapper.setProps({ modelValue: false })
    const reopened = config()
    reopened.revision = "reopened-current-config"
    reopened.profiles[0]!.name = "Current reopened profile"
    vi.mocked(llmApi.config).mockResolvedValue(reopened)
    vi.mocked(llmApi.localVisionStatus).mockResolvedValue({ state: "missing", installed: false, downloaded_bytes: 0, total_bytes: 100 })
    await wrapper.setProps({ modelValue: true })
    await flushPromises()
    const obsolete = config()
    obsolete.revision = "obsolete-background-result"
    obsolete.profiles[0]!.name = "Obsolete profile"
    finishOldRefresh(obsolete)
    await flushPromises()
    expect((wrapper.get('[data-profile-id="text"] .llm-profile-name').element as HTMLInputElement).value).toBe("Current reopened profile")
    expect(wrapper.emitted("saved")).toBeUndefined()
    expect((wrapper.get(".llm-save").element as HTMLButtonElement).disabled).toBe(false)
  })

  it("keeps unsaved profile inputs when a runtime action refreshes the managed profile", async () => {
    const wrapper = await open()
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

  it("merges unrelated server changes with local edits before adopting the runtime revision", async () => {
    const wrapper = await open()
    await wrapper.get('[data-profile-id="text"] .llm-profile-name').setValue("My unsaved name")
    const updated = config()
    updated.revision = "external-update-and-runtime"
    updated.profiles[0]!.endpoint = "https://updated.example.test/chat/completions"
    updated.profiles[1]!.name = "External tab vision name"
    updated.routes.translation = "vision"
    updated.cache.caption = false
    updated.profiles.push({ ...updated.profiles[1]!, id: "qwen3.5-2b-local", source: "managed-local", asset_id: "qwen3.5-2b-local" })
    vi.mocked(llmApi.config).mockResolvedValue(updated)
    vi.mocked(llmApi.localVisionAction).mockResolvedValue({ state: "running", installed: true, runtime_installed: true, downloaded_bytes: 0, total_bytes: 0 })
    await wrapper.get(".managed-vision-model button").trigger("click")
    await flushPromises()
    expect((wrapper.get('[data-profile-id="text"] .llm-profile-name').element as HTMLInputElement).value).toBe("My unsaved name")
    expect((wrapper.get('[data-profile-id="vision"] .llm-profile-name').element as HTMLInputElement).value).toBe("External tab vision name")
    vi.mocked(llmApi.saveConfig).mockResolvedValue(updated)
    await wrapper.get(".llm-save").trigger("click")
    await flushPromises()
    const body = vi.mocked(llmApi.saveConfig).mock.calls[0]![0]
    expect(body.revision).toBe("external-update-and-runtime")
    expect(body.profiles!.find(profile => profile.id === "text")).toMatchObject({ name: "My unsaved name", endpoint: "https://updated.example.test/chat/completions" })
    expect(body.profiles!.find(profile => profile.id === "vision")!.name).toBe("External tab vision name")
    expect(body.routes!.translation).toBe("vision")
    expect(body.cache!.caption).toBe(false)
  })

  it("retains and blocks a conflicting draft until server reload is explicitly confirmed", async () => {
    const wrapper = await open()
    await wrapper.get('[data-profile-id="text"] .llm-profile-name').setValue("My conflicting name")
    const updated = config()
    updated.revision = "latest-conflicting-revision"
    updated.profiles[0]!.name = "External tab conflicting name"
    vi.mocked(llmApi.config).mockResolvedValue(updated)
    vi.mocked(llmApi.localVisionAction).mockResolvedValue({ state: "running", installed: true, runtime_installed: true, downloaded_bytes: 0, total_bytes: 0 })
    await wrapper.get(".managed-vision-model button").trigger("click")
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain("当前草稿已保留")
    expect((wrapper.get('[data-profile-id="text"] .llm-profile-name').element as HTMLInputElement).value).toBe("My conflicting name")
    expect((wrapper.get(".llm-save").element as HTMLButtonElement).disabled).toBe(true)
    await wrapper.get(".llm-save").trigger("click")
    expect(llmApi.saveConfig).not.toHaveBeenCalled()
    const confirm = vi.spyOn(ElMessageBox, "confirm").mockRejectedValueOnce("cancel").mockResolvedValueOnce("confirm" as never)
    await wrapper.get(".llm-reload-config").trigger("click")
    await flushPromises()
    expect(confirm).toHaveBeenCalledOnce()
    expect((wrapper.get('[data-profile-id="text"] .llm-profile-name').element as HTMLInputElement).value).toBe("My conflicting name")
    await wrapper.get(".llm-reload-config").trigger("click")
    await flushPromises()
    expect((wrapper.get('[data-profile-id="text"] .llm-profile-name').element as HTMLInputElement).value).toBe("External tab conflicting name")
    expect((wrapper.get(".llm-save").element as HTMLButtonElement).disabled).toBe(false)
    vi.mocked(llmApi.saveConfig).mockResolvedValue(updated)
    await wrapper.get(".llm-save").trigger("click")
    await flushPromises()
    expect(vi.mocked(llmApi.saveConfig).mock.calls[0]![0]).toMatchObject({ revision: "latest-conflicting-revision" })
  })

  it("keeps local route and cache edits while adopting a runtime-only configuration update", async () => {
    const wrapper = await open()
    await wrapper.get(".llm-settings select").setValue("vision")
    await wrapper.get(".llm-translation-cache").setValue(false)
    await wrapper.get(".llm-local-fallback").setValue(false)
    const updated = config()
    updated.revision = "own-runtime-revision"
    updated.profiles.push({ ...updated.profiles[1]!, id: "qwen3.5-2b-local", source: "managed-local", asset_id: "qwen3.5-2b-local" })
    vi.mocked(llmApi.config).mockResolvedValue(updated)
    vi.mocked(llmApi.localVisionAction).mockResolvedValue({ state: "running", installed: true, runtime_installed: true, downloaded_bytes: 0, total_bytes: 0 })
    await wrapper.get(".managed-vision-model button").trigger("click")
    await flushPromises()
    expect((wrapper.get(".llm-save").element as HTMLButtonElement).disabled).toBe(false)
    vi.mocked(llmApi.saveConfig).mockResolvedValue(updated)
    await wrapper.get(".llm-save").trigger("click")
    await flushPromises()
    expect(vi.mocked(llmApi.saveConfig).mock.calls[0]![0]).toMatchObject({ revision: "own-runtime-revision", routes: { translation: "vision" }, cache: { translation: false }, local_fallback_enabled: false })
  })

  it("retains unsaved managed enablement while refreshing its verified runtime state", async () => {
    const initial = config()
    initial.revision = "managed-before-start"
    initial.profiles.push({ ...initial.profiles[1]!, id: "managed", source: "managed-local", asset_id: "qwen3.5-2b-local", ready: false, verified_capabilities: [] })
    await open()
    vi.mocked(llmApi.config).mockResolvedValue(initial)
    await page!.setProps({ modelValue: false })
    await page!.setProps({ modelValue: true })
    await flushPromises()
    const wrapper = page!
    await wrapper.get('[data-profile-id="managed"] .llm-profile-enabled input').setValue(false)
    const updated = JSON.parse(JSON.stringify(initial)) as LlmConfig
    updated.revision = "managed-after-start"
    updated.profiles.find(profile => profile.id === "managed")!.ready = true
    updated.profiles.find(profile => profile.id === "managed")!.verified_capabilities = ["text", "vision"]
    vi.mocked(llmApi.config).mockResolvedValue(updated)
    vi.mocked(llmApi.localVisionAction).mockResolvedValue({ state: "running", installed: true, runtime_installed: true, downloaded_bytes: 0, total_bytes: 0 })
    await wrapper.get(".managed-vision-model button").trigger("click")
    await flushPromises()
    expect((wrapper.get('[data-profile-id="managed"] .llm-profile-enabled input').element as HTMLInputElement).checked).toBe(false)
    vi.mocked(llmApi.saveConfig).mockResolvedValue(updated)
    await wrapper.get(".llm-save").trigger("click")
    await flushPromises()
    expect(vi.mocked(llmApi.saveConfig).mock.calls[0]![0].profiles!.find(profile => profile.id === "managed")).toMatchObject({ enabled: false, ready: true, verified_capabilities: ["text", "vision"] })
  })

  it("absorbs server additions and removals without resurrecting an unchanged deleted endpoint", async () => {
    const wrapper = await open()
    await wrapper.get('[data-profile-id="vision"] .llm-profile-name').setValue("My vision name")
    const updated = config()
    updated.revision = "external-profile-list-update"
    updated.profiles = updated.profiles.filter(profile => profile.id !== "text")
    updated.profiles.push({ ...updated.profiles[0]!, id: "external-new", name: "External new endpoint" })
    updated.routes.translation = "vision"
    vi.mocked(llmApi.config).mockResolvedValue(updated)
    vi.mocked(llmApi.localVisionAction).mockResolvedValue({ state: "running", installed: true, runtime_installed: true, downloaded_bytes: 0, total_bytes: 0 })
    await wrapper.get(".managed-vision-model button").trigger("click")
    await flushPromises()
    expect(wrapper.find('[data-profile-id="text"]').exists()).toBe(false)
    expect(wrapper.find('[data-profile-id="external-new"]').exists()).toBe(true)
    vi.mocked(llmApi.saveConfig).mockResolvedValue(updated)
    await wrapper.get(".llm-save").trigger("click")
    await flushPromises()
    const body = vi.mocked(llmApi.saveConfig).mock.calls[0]![0]
    expect(body.profiles!.map(profile => profile.id)).toEqual(["vision", "external-new"])
    expect(body.profiles!.find(profile => profile.id === "vision")!.name).toBe("My vision name")
  })

  it("blocks merging an externally deleted endpoint that still has local edits", async () => {
    const wrapper = await open()
    await wrapper.get('[data-profile-id="text"] .llm-profile-name').setValue("Do not lose this edit")
    const updated = config()
    updated.revision = "external-deletion"
    updated.profiles = updated.profiles.filter(profile => profile.id !== "text")
    updated.routes.translation = "vision"
    vi.mocked(llmApi.config).mockResolvedValue(updated)
    vi.mocked(llmApi.localVisionAction).mockResolvedValue({ state: "running", installed: true, runtime_installed: true, downloaded_bytes: 0, total_bytes: 0 })
    await wrapper.get(".managed-vision-model button").trigger("click")
    await flushPromises()
    expect((wrapper.get('[data-profile-id="text"] .llm-profile-name').element as HTMLInputElement).value).toBe("Do not lose this edit")
    expect((wrapper.get(".llm-save").element as HTMLButtonElement).disabled).toBe(true)
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
    const wrapper = await open()
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
    const wrapper = await open()
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
