// @vitest-environment jsdom
import { KeepAlive, defineComponent, ref } from "vue"
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { datasetApi, type DatasetScan } from "../api/dataset"
import { datasetsApi } from "../api/datasets"
import { DEFAULT_CAPTION_TRANSLATION_SETTINGS, llmApi, type CaptionTranslationSettingsResponse, type LlmConfig } from "../api/llm"
import LlmSettingsDialog from "../components/LlmSettingsDialog.vue"
import ManagedVisionModel from "../components/ManagedVisionModel.vue"
import TagTranslationControls from "../components/dataset/TagTranslationControls.vue"
import TagTranslationSettingsDialog from "../components/dataset/TagTranslationSettingsDialog.vue"
import { useDatasetEditorSession } from "../composables/useDatasetEditorSession"
import { useTagTranslations } from "../composables/useTagTranslations"
import { i18n } from "../i18n"
import DatasetEditorPage from "./DatasetEditorPage.vue"

const replaceRoute = vi.fn()
const pushRoute = vi.fn()
vi.mock("vue-router", () => ({ useRoute: () => ({ query: {} }), useRouter: () => ({ replace: replaceRoute, push: pushRoute }) }))
const state = useDatasetEditorSession()
const wrappers: VueWrapper[] = []
const visible = ref(true)
const Dialog = { props: { modelValue: { type: Boolean, required: true } }, template: '<div v-if="modelValue" class="test-dialog"><slot /><slot name="footer" /></div>' }
let currentConfig: LlmConfig
let currentCaptionSettings: CaptionTranslationSettingsResponse

function config(): LlmConfig {
  return {
    version: 5, revision: "initial", routes: { translation: "remote-a", caption: "" }, prompt_presets: [],
    cache: { translation: true, caption: true }, local_fallback_enabled: true,
    profiles: [
      { id: "remote-a", name: "Remote A", endpoint: "https://example.test/chat/completions", model: "text-a", source: "remote", capabilities: ["text"], languages: ["en", "zh-CN"], api_key: "********", api_key_configured: true, enabled: true, ready: true, verified_capabilities: ["text"] },
      { id: "remote-b", name: "Remote B", endpoint: "https://example.test/chat/completions", model: "text-b", source: "remote", capabilities: ["text"], languages: ["en", "zh-CN"], api_key: "********", api_key_configured: true, enabled: true, ready: true, verified_capabilities: ["text"] },
      { id: "managed", name: "Qwen3.5-2B", endpoint: "http://127.0.0.1:5011/chat/completions", model: "qwen3.5-2b", source: "managed-local", asset_id: "qwen3.5-2b-local", capabilities: ["text", "vision"], languages: ["en", "zh-CN"], api_key: "", enabled: true, ready: false, verified_capabilities: [] },
    ],
  }
}

function scan(natural = false): DatasetScan {
  const caption = natural ? "A cat by a window." : "translation-entry-tag"
  return { root: "/translation-entry", total: 1, items: [{ name: "a.png", relative_path: "a.png", category: "", caption, caption_exists: true, caption_format: natural ? "natural" : "tag", tags: natural ? [] : [caption], image_url: "", thumb_url: "" }], tags: [], categories: [] }
}

beforeEach(() => {
  state.unload()
  state.drafts.value = {}
  state.showTranslations.value = false
  state.translationProvider.value = "mymemory"
  state.rememberDataset("/translation-entry", "/translation-entry")
  useTagTranslations().clearCache()
  useTagTranslations().configureCache(true, "")
  visible.value = true
  currentConfig = config()
  currentCaptionSettings = { settings: { ...DEFAULT_CAPTION_TRANSLATION_SETTINGS }, revision: "initial" }
  vi.spyOn(llmApi, "captionTranslationSettings").mockImplementation(async () => structuredClone(currentCaptionSettings))
  vi.spyOn(llmApi, "saveCaptionTranslationSettings").mockImplementation(async (settings, revision) => {
    expect(revision).toBe(currentCaptionSettings.revision)
    currentCaptionSettings = { settings: { ...settings }, revision: "caption-settings-saved" }
    return structuredClone(currentCaptionSettings)
  })
  vi.spyOn(datasetApi, "scan").mockResolvedValue(scan())
  vi.spyOn(datasetApi, "history").mockResolvedValue({ can_undo: false, can_redo: false, changes: [] })
  vi.spyOn(datasetApi, "save").mockRejectedValue(new Error("must not save captions"))
  vi.spyOn(datasetsApi, "list").mockResolvedValue({ root: "/", exists: true, datasets: [] })
  vi.spyOn(datasetApi, "tagDictionaryStatus").mockResolvedValue({ state: "ready", installed: true, row_count: 1, size_bytes: 10 })
  vi.spyOn(datasetApi, "tagTranslationCache").mockResolvedValue({ total: 0, llm: 0, mymemory: 0 })
  vi.spyOn(datasetApi, "tagTranslations").mockImplementation(async (tags, provider, locale) => ({ items: tags.map(tag => ({ tag, translation: null, source: null, status: "missing" as const })), provider: provider ?? "danbooru", locale: locale ?? "zh-CN" }))
  vi.spyOn(llmApi, "translateCaption").mockResolvedValue({ translation: "一只猫在窗边。", cached: false, skipped: false })
  vi.spyOn(llmApi, "config").mockImplementation(async () => JSON.parse(JSON.stringify(currentConfig)) as LlmConfig)
  vi.spyOn(llmApi, "localVisionStatus").mockResolvedValue({ state: "missing", installed: false, downloaded_bytes: 0, total_bytes: 0 })
  vi.spyOn(llmApi, "saveConfig").mockImplementation(async body => {
    currentConfig = { ...currentConfig, ...body, revision: "saved" }
    return currentConfig
  })
})

afterEach(() => {
  wrappers.forEach(wrapper => wrapper.unmount())
  wrappers.length = 0
  useTagTranslations().clearCache()
  vi.restoreAllMocks()
  vi.clearAllMocks()
})

async function render() {
  const host = defineComponent({ components: { DatasetEditorPage, KeepAlive }, setup: () => ({ visible }), template: "<KeepAlive><DatasetEditorPage v-if='visible' /></KeepAlive>" })
  const wrapper = mount(host, { global: { plugins: [i18n], stubs: { ElDialog: Dialog, PathPickerDialog: true, ManagedDatasetPicker: true, TagFilterPanel: true, ManagedVisionModel: true } } })
  wrappers.push(wrapper)
  await flushPromises()
  await wrapper.get(".image-grid button").trigger("click")
  await flushPromises()
  return wrapper
}

async function openSettings(wrapper: VueWrapper) {
  await wrapper.get(".caption-translation-settings-action").trigger("click")
  await flushPromises()
  expect(wrapper.findComponent(TagTranslationSettingsDialog).props("modelValue")).toBe(true)
}

async function openManager(wrapper: VueWrapper) {
  await openSettings(wrapper)
  await wrapper.get(".translation-manage-llm").trigger("click")
  await flushPromises()
  expect(wrapper.findComponent(TagTranslationSettingsDialog).props("modelValue")).toBe(false)
  expect(wrapper.findComponent(LlmSettingsDialog).props()).toMatchObject({ modelValue: true, capability: "text" })
  expect(replaceRoute).not.toHaveBeenCalled()
}

it("opens Tag translation settings beside the switch without enabling translation", async () => {
  const wrapper = await render()
  const controls = wrapper.findComponent(TagTranslationControls)
  const heading = controls.get(".caption-translation-heading")
  expect(heading.findComponent({ name: "ElSwitch" }).exists()).toBe(true)
  expect(heading.get("button").text()).toBe(i18n.global.t("datasetEditor.caption.translationSettings"))
  await openSettings(wrapper)
  expect(state.showTranslations.value).toBe(false)
  expect(datasetApi.tagTranslations).not.toHaveBeenCalled()
  expect(llmApi.translateCaption).not.toHaveBeenCalled()
  expect(wrapper.get(".translation-manage-llm").text()).toBe(i18n.global.t("llm.title"))
  expect(wrapper.find('a[href="/settings/api"]').exists()).toBe(false)
  expect(wrapper.findAll('.caption-translation-provider [role="radio"]').map(button => button.text())).toEqual(["词库 + 免费接口", "词库 + LLM"])
  expect(wrapper.find('.natural-translation-parameters').exists()).toBe(false)
  expect(llmApi.captionTranslationSettings).not.toHaveBeenCalled()
  expect(llmApi.saveCaptionTranslationSettings).not.toHaveBeenCalled()
})

it("selects dictionary + free API and sends missing Tags to the MyMemory route without LLM setup", async () => {
  state.translationProvider.value = "llm"
  currentConfig.profiles = []
  vi.mocked(datasetApi.tagDictionaryStatus).mockResolvedValue({ state: "missing", installed: false, row_count: 0, size_bytes: 0 })
  const wrapper = await render()
  await openSettings(wrapper)
  await wrapper.get('.caption-translation-provider [role="radio"]').trigger("click")
  await flushPromises()
  expect(state.translationProvider.value).toBe("mymemory")
  wrapper.findComponent(TagTranslationControls).vm.$emit("update:enabled", true)
  await flushPromises()
  expect(datasetApi.tagTranslations).toHaveBeenCalledWith(["translation-entry-tag"], "mymemory", "zh-CN")
  expect(llmApi.translateCaption).not.toHaveBeenCalled()
})

it("allows dictionary results in the LLM mode when no LLM is configured", async () => {
  state.translationProvider.value = "llm"
  currentConfig.profiles = []
  const wrapper = await render()
  wrapper.findComponent(TagTranslationControls).vm.$emit("update:enabled", true)
  await flushPromises()
  expect(datasetApi.tagTranslations).toHaveBeenCalledWith(["translation-entry-tag"], "llm", "zh-CN")
  expect(wrapper.findComponent(TagTranslationSettingsDialog).props("modelValue")).toBe(false)
})

it("keeps natural captions on the LLM route and hides Tag-only provider and dictionary settings", async () => {
  vi.mocked(datasetApi.scan).mockResolvedValue(scan(true))
  const wrapper = await render()
  await openSettings(wrapper)
  expect(wrapper.findComponent(TagTranslationSettingsDialog).props("contentType")).toBe("natural")
  expect(wrapper.find('.caption-translation-provider').exists()).toBe(false)
  expect(wrapper.find('.caption-translation-cache-row').exists()).toBe(false)
  expect(wrapper.findComponent(TagTranslationSettingsDialog).text()).toContain(i18n.global.t("datasetEditor.caption.naturalTranslationSettingsHint"))
  expect(wrapper.find('.translation-go-llm').exists()).toBe(true)
  state.showTranslations.value = true
  await flushPromises()
  const retry = wrapper.findAll('.natural-translation-controls button').find(button => button.text() === i18n.global.t("datasetEditor.caption.retryNaturalTranslation"))!
  await retry.trigger("click")
  await flushPromises()
  expect(llmApi.translateCaption).toHaveBeenCalledWith("A cat by a window.", undefined, expect.any(AbortSignal))
  expect(datasetApi.tagTranslations).not.toHaveBeenCalled()
})

it("loads and saves caption-only parameters with CAS while preserving profiles and raw drafts", async () => {
  vi.mocked(datasetApi.scan).mockResolvedValue(scan(true))
  const wrapper = await render()
  await wrapper.get('.caption-editor textarea').setValue('An unsaved cat description.')
  await openSettings(wrapper)
  expect((wrapper.get('.natural-translation-concurrency').element as HTMLInputElement).value).toBe('3')
  expect((wrapper.get('.natural-translation-max-tokens').element as HTMLInputElement).value).toBe('2048')
  expect((wrapper.get('.natural-translation-temperature').element as HTMLInputElement).value).toBe('0.7')
  await wrapper.get('.natural-translation-concurrency').setValue('5')
  await wrapper.get('.natural-translation-max-tokens').setValue('1024')
  await wrapper.get('.natural-translation-temperature').setValue('0.3')
  state.showTranslations.value = true
  await flushPromises()
  vi.mocked(llmApi.translateCaption).mockClear()
  await wrapper.get('.natural-translation-save').trigger('click')
  await flushPromises()
  expect(llmApi.saveCaptionTranslationSettings).toHaveBeenCalledWith({ concurrency: 5, max_tokens: 1024, temperature: 0.3 }, 'initial')
  expect(llmApi.saveConfig).not.toHaveBeenCalled()
  expect(datasetApi.tagTranslations).not.toHaveBeenCalled()
  expect(datasetApi.save).not.toHaveBeenCalled()
  expect(llmApi.translateCaption).toHaveBeenCalledWith('An unsaved cat description.', undefined, expect.any(AbortSignal))
  expect(state.getDraft('/translation-entry', 'a.png')).toBe('An unsaved cat description.')
  wrapper.findComponent(TagTranslationSettingsDialog).vm.$emit('update:modelValue', false)
  await flushPromises()
  await openSettings(wrapper)
  expect((wrapper.get('.natural-translation-concurrency').element as HTMLInputElement).value).toBe('5')
})

it('discards cancelled parameter edits without saving and rejects out-of-range inputs', async () => {
  vi.mocked(datasetApi.scan).mockResolvedValue(scan(true))
  const wrapper = await render()
  await openSettings(wrapper)
  for (const [selector, invalid, valid] of [['.natural-translation-concurrency', '9', '3'], ['.natural-translation-max-tokens', '127', '2048'], ['.natural-translation-temperature', '2.1', '0.7']]) {
    await wrapper.get(selector!).setValue(invalid!)
    expect(wrapper.get('.natural-translation-save').attributes('disabled')).toBeDefined()
    await wrapper.get('.natural-translation-save').trigger('click')
    expect(llmApi.saveCaptionTranslationSettings).not.toHaveBeenCalled()
    await wrapper.get(selector!).setValue(valid!)
    expect(wrapper.get('.natural-translation-save').attributes('disabled')).toBeUndefined()
  }
  wrapper.findComponent(TagTranslationSettingsDialog).vm.$emit('update:modelValue', false)
  await flushPromises()
  await openSettings(wrapper)
  expect((wrapper.get('.natural-translation-concurrency').element as HTMLInputElement).value).toBe('3')
  expect(wrapper.get('.natural-translation-save').attributes('disabled')).toBeUndefined()
})

it('requires a successful load and explicit reload after a save conflict without replacing the draft', async () => {
  vi.mocked(datasetApi.scan).mockResolvedValue(scan(true))
  vi.mocked(llmApi.captionTranslationSettings).mockRejectedValueOnce(new Error('settings unavailable'))
  const wrapper = await render()
  await openSettings(wrapper)
  expect(wrapper.get('.natural-translation-save').attributes('disabled')).toBeDefined()
  expect(wrapper.findComponent(TagTranslationSettingsDialog).text()).toContain('settings unavailable')
  await wrapper.get('.natural-translation-reload').trigger('click')
  await flushPromises()
  await wrapper.get('.natural-translation-concurrency').setValue('4')
  vi.mocked(llmApi.saveCaptionTranslationSettings).mockRejectedValueOnce(new Error('configuration conflict'))
  await wrapper.get('.natural-translation-save').trigger('click')
  await flushPromises()
  expect((wrapper.get('.natural-translation-concurrency').element as HTMLInputElement).value).toBe('4')
  expect(wrapper.findComponent(TagTranslationSettingsDialog).text()).toContain('configuration conflict')
  expect(wrapper.get('.natural-translation-save').attributes('disabled')).toBeDefined()
  currentCaptionSettings = { settings: { concurrency: 2, max_tokens: 4096, temperature: 0.1 }, revision: 'newer-revision' }
  await wrapper.get('.natural-translation-reload').trigger('click')
  await flushPromises()
  expect((wrapper.get('.natural-translation-concurrency').element as HTMLInputElement).value).toBe('2')
  await wrapper.get('.natural-translation-save').trigger('click')
  await flushPromises()
  expect(llmApi.saveCaptionTranslationSettings).toHaveBeenLastCalledWith(currentCaptionSettings.settings, 'newer-revision')
})

it('ignores a delayed settings load after closing and reopening the dialog', async () => {
  vi.mocked(datasetApi.scan).mockResolvedValue(scan(true))
  const wrapper = await render()
  let complete!: (value: CaptionTranslationSettingsResponse) => void
  vi.mocked(llmApi.captionTranslationSettings).mockReturnValueOnce(new Promise(resolve => { complete = resolve }))
  await openSettings(wrapper)
  expect(wrapper.get('.natural-translation-save').attributes('disabled')).toBeDefined()
  wrapper.findComponent(TagTranslationSettingsDialog).vm.$emit('update:modelValue', false)
  await flushPromises()
  currentCaptionSettings = { settings: { concurrency: 2, max_tokens: 2048, temperature: 0 }, revision: 'reopened' }
  await openSettings(wrapper)
  complete({ settings: { concurrency: 8, max_tokens: 8192, temperature: 2 }, revision: 'stale' })
  await flushPromises()
  expect((wrapper.get('.natural-translation-concurrency').element as HTMLInputElement).value).toBe('2')
  await wrapper.get('.natural-translation-save').trigger('click')
  await flushPromises()
  expect(llmApi.saveCaptionTranslationSettings).toHaveBeenCalledWith(currentCaptionSettings.settings, 'reopened')
})

it('prevents repeated saves and navigation while saving and ignores the reply after deactivation', async () => {
  vi.mocked(datasetApi.scan).mockResolvedValue(scan(true))
  const wrapper = await render()
  await openSettings(wrapper)
  let complete!: (value: CaptionTranslationSettingsResponse) => void
  vi.mocked(llmApi.saveCaptionTranslationSettings).mockReturnValueOnce(new Promise(resolve => { complete = resolve }))
  await wrapper.get('.natural-translation-save').trigger('click')
  expect(wrapper.get('.natural-translation-save').attributes('disabled')).toBeDefined()
  expect(wrapper.get('.translation-go-llm').attributes('disabled')).toBeDefined()
  await wrapper.get('.natural-translation-save').trigger('click')
  expect(llmApi.saveCaptionTranslationSettings).toHaveBeenCalledTimes(1)
  visible.value = false
  await flushPromises()
  complete({ settings: { concurrency: 8, max_tokens: 8192, temperature: 2 }, revision: 'late' })
  await flushPromises()
  visible.value = true
  await flushPromises()
  await openSettings(wrapper)
  expect((wrapper.get('.natural-translation-concurrency').element as HTMLInputElement).value).toBe('3')
  expect(llmApi.translateCaption).not.toHaveBeenCalled()
})

it("uses the second ready remote even when the preferred remote is not ready", async () => {
  state.translationProvider.value = "llm"
  currentConfig.profiles[0]!.ready = false
  const wrapper = await render()
  await openSettings(wrapper)
  expect(wrapper.findComponent(TagTranslationSettingsDialog).props("remoteConfigured")).toBe(true)
  wrapper.findComponent(TagTranslationControls).vm.$emit("update:enabled", true)
  await flushPromises()
  expect(datasetApi.tagTranslations).toHaveBeenCalledWith(["translation-entry-tag"], "llm", "zh-CN")
})

it("routes through a ready local endpoint without requiring a managed runtime", async () => {
  state.translationProvider.value = "llm"
  currentConfig.profiles = [{ id: "endpoint", name: "External local", endpoint: "http://127.0.0.1:5000/v1/chat/completions", model: "local-text", source: "local-endpoint", capabilities: ["text"], verified_capabilities: ["text"], languages: ["zh-CN"], api_key: "", enabled: true, ready: true }]
  const wrapper = await render()
  await openSettings(wrapper)
  expect(wrapper.findComponent(TagTranslationSettingsDialog).props()).toMatchObject({ remoteConfigured: false, sharedLocalReady: true })
  wrapper.findComponent(TagTranslationControls).vm.$emit("update:enabled", true)
  await flushPromises()
  expect(datasetApi.tagTranslations).toHaveBeenCalledWith(["translation-entry-tag"], "llm", "zh-CN")
})

it("reloads shared cache policy before translating after KeepAlive reactivation", async () => {
  state.translationProvider.value = "llm"
  state.showTranslations.value = true
  vi.mocked(datasetApi.tagTranslations).mockImplementation(async (tags, provider, locale) => ({ items: tags.map(tag => ({ tag, translation: "旧译文", source: "llm", status: "hit" as const })), provider, locale: locale ?? "zh-CN" }))
  const wrapper = await render()
  await flushPromises()
  expect(useTagTranslations().translationFor("translation-entry-tag", "llm")).toBe("旧译文")
  visible.value = false
  await flushPromises()
  currentConfig = { ...currentConfig, revision: "other-entry-save", cache: { ...currentConfig.cache, translation: false }, routes: { ...currentConfig.routes, translation: "remote-b" } }
  let completeConfig!: (value: LlmConfig) => void
  vi.mocked(llmApi.config).mockReturnValueOnce(new Promise(resolve => { completeConfig = resolve }))
  vi.mocked(datasetApi.tagTranslations).mockClear()
  vi.mocked(datasetApi.tagTranslations).mockImplementation(async (tags, provider, locale) => ({ items: tags.map(tag => ({ tag, translation: "新译文", source: "llm", status: "hit" as const })), provider, locale: locale ?? "zh-CN" }))
  visible.value = true
  await flushPromises()
  expect(datasetApi.tagTranslations).not.toHaveBeenCalled()
  completeConfig(currentConfig)
  await flushPromises()
  expect(datasetApi.tagTranslations).toHaveBeenCalledWith(["translation-entry-tag"], "llm", "zh-CN")
  expect(useTagTranslations().translationFor("translation-entry-tag", "llm")).toBe("新译文")
  await openSettings(wrapper)
  expect(wrapper.findComponent(TagTranslationSettingsDialog).props()).toMatchObject({ remoteConfigured: true, llmMode: "local" })
})

it.each(["disabled", "unverified", "wrong-language", "no-fallback"])("blocks an unavailable local endpoint: %s", async reason => {
  state.translationProvider.value = "llm"
  currentConfig.profiles = [{ id: "endpoint", name: "External local", endpoint: "http://127.0.0.1:5000/v1/chat/completions", model: "local-text", source: "local-endpoint", capabilities: ["text"], verified_capabilities: reason === "unverified" ? [] : ["text"], languages: reason === "wrong-language" ? ["en"] : ["zh-CN"], api_key: "", enabled: reason !== "disabled", ready: true }]
  currentConfig.local_fallback_enabled = reason !== "no-fallback"
  vi.mocked(datasetApi.tagDictionaryStatus).mockResolvedValue({ state: "missing", installed: false, row_count: 0, size_bytes: 0 })
  const wrapper = await render()
  wrapper.findComponent(TagTranslationControls).vm.$emit("update:enabled", true)
  await flushPromises()
  expect(datasetApi.tagTranslations).not.toHaveBeenCalled()
  expect(wrapper.findComponent(TagTranslationSettingsDialog).props("modelValue")).toBe(true)
})

it("returns to translation settings after cancelling LLM edits and preserves the caption draft", async () => {
  const wrapper = await render()
  const rawButton = wrapper.findAll(".caption-mode button")[1]!
  await rawButton.trigger("click")
  await wrapper.get(".caption-editor textarea").setValue("draft, translation-entry-tag")
  await openManager(wrapper)
  // The real ElDialog forwards false after the settings leave transition.
  wrapper.findComponent(TagTranslationSettingsDialog).vm.$emit("update:modelValue", false)
  await flushPromises()
  await wrapper.get('[data-profile-id="remote-a"] .llm-profile-name').setValue("Discarded")
  await wrapper.get('[data-profile-id="remote-a"] input[type="password"]').setValue("fixture-unsaved-key")
  await wrapper.get(".llm-cancel").trigger("click")
  await flushPromises()
  expect(wrapper.findComponent(TagTranslationSettingsDialog).props("modelValue")).toBe(true)
  expect(wrapper.findComponent(LlmSettingsDialog).props("modelValue")).toBe(false)
  expect(llmApi.saveConfig).not.toHaveBeenCalled()
  expect(datasetApi.save).not.toHaveBeenCalled()
  expect(state.getDraft("/translation-entry", "a.png")).toBe("draft, translation-entry-tag")
  await wrapper.get(".translation-manage-llm").trigger("click")
  await flushPromises()
  expect((wrapper.get('[data-profile-id="remote-a"] .llm-profile-name').element as HTMLInputElement).value).toBe("Remote A")
  expect((wrapper.get('[data-profile-id="remote-a"] input[type="password"]').element as HTMLInputElement).value).toBe("********")
})

it("opens the LLM management page directly and reloads shared settings on return without losing a natural caption draft", async () => {
  vi.mocked(datasetApi.scan).mockResolvedValue(scan(true))
  const wrapper = await render()
  await wrapper.get(".caption-editor textarea").setValue("An unsaved cat description.")
  await openSettings(wrapper)
  state.showTranslations.value = true
  await flushPromises()
  await wrapper.get(".translation-go-llm").trigger("click")
  expect(pushRoute).toHaveBeenCalledWith("/settings/api")
  expect(wrapper.findComponent(LlmSettingsDialog).props("modelValue")).toBe(false)
  visible.value = false
  await flushPromises()
  currentConfig = { ...currentConfig, revision: "other-page-save", routes: { translation: "remote-b", caption: "" }, local_fallback_enabled: false }
  const statusReads = vi.mocked(llmApi.localVisionStatus).mock.calls.length
  visible.value = true
  await flushPromises()
  await openSettings(wrapper)
  await flushPromises()
  expect(llmApi.saveConfig).not.toHaveBeenCalled()
  expect(wrapper.findComponent(TagTranslationSettingsDialog).props()).toMatchObject({ modelValue: true, llmMode: "remote", remoteConfigured: true })
  expect(vi.mocked(llmApi.localVisionStatus).mock.calls.length).toBeGreaterThan(statusReads)
  wrapper.findComponent(TagTranslationSettingsDialog).vm.$emit('update:modelValue', false)
  await flushPromises()
  const retry = wrapper.findAll('.natural-translation-controls button').find(button => button.text() === i18n.global.t('datasetEditor.caption.retryNaturalTranslation'))!
  await retry.trigger('click')
  await flushPromises()
  expect(llmApi.translateCaption).toHaveBeenCalledWith("An unsaved cat description.", undefined, expect.any(AbortSignal))
  expect(wrapper.get(".natural-caption-translated").text()).toContain("一只猫在窗边。")
  expect(state.getDraft("/translation-entry", "a.png")).toBe("An unsaved cat description.")
  expect(datasetApi.save).not.toHaveBeenCalled()
})

it("refreshes local text readiness after a shared runtime action while keeping Tag translation settings hidden", async () => {
  state.translationProvider.value = "llm"
  currentConfig.profiles.filter(profile => profile.source === "remote").forEach(profile => { profile.ready = false })
  const wrapper = await render()
  await openManager(wrapper)
  state.showTranslations.value = true
  const local = currentConfig.profiles.find(profile => profile.source === "managed-local")!
  local.ready = true
  local.verified_capabilities = ["text", "vision"]
  const status = { state: "running", installed: true, model_id: "qwen3.5-2b-local", downloaded_bytes: 0, total_bytes: 0 }
  vi.mocked(llmApi.localVisionStatus).mockResolvedValue(status)
  vi.spyOn(llmApi, "localVisionAction").mockResolvedValue(status)
  wrapper.findComponent(ManagedVisionModel).vm.$emit("action", "start")
  await flushPromises()
  expect(llmApi.localVisionAction).toHaveBeenCalledWith("start")
  expect(wrapper.findComponent(TagTranslationSettingsDialog).props()).toMatchObject({ modelValue: false, remoteConfigured: false, sharedLocalReady: true, llmMode: "local" })
  expect(wrapper.findComponent(LlmSettingsDialog).props("modelValue")).toBe(true)
  expect(datasetApi.tagTranslations).toHaveBeenCalledWith(["translation-entry-tag"], "llm", "zh-CN")
  expect(llmApi.saveConfig).not.toHaveBeenCalled()
})

it("keeps both dialogs closed when a readiness request finishes after editor deactivation", async () => {
  const wrapper = await render()
  await openManager(wrapper)
  state.showTranslations.value = true
  state.translationProvider.value = "llm"
  let complete!: (value: LlmConfig) => void
  vi.mocked(llmApi.config).mockReturnValue(new Promise(resolve => { complete = resolve }))
  const settings = wrapper.findComponent(TagTranslationSettingsDialog)
  const manager = wrapper.findComponent(LlmSettingsDialog)
  manager.vm.$emit("saved", currentConfig)
  await flushPromises()
  visible.value = false
  await flushPromises()
  currentConfig.profiles.forEach(profile => { profile.ready = false })
  complete(currentConfig)
  await flushPromises()
  expect(settings.props("modelValue")).toBe(false)
  expect(manager.props("modelValue")).toBe(false)
  expect(datasetApi.tagTranslations).not.toHaveBeenCalled()
})

it("keeps a newly saved shared config when an older settings request arrives late", async () => {
  const wrapper = await render()
  const oldConfig = config()
  let completeOld!: (value: LlmConfig) => void
  vi.mocked(llmApi.config).mockReturnValueOnce(new Promise(resolve => { completeOld = resolve }))
  await wrapper.get(".caption-translation-settings-action").trigger("click")
  await flushPromises()
  expect(wrapper.findComponent(TagTranslationSettingsDialog).props("loading")).toBe(true)
  await wrapper.get(".translation-manage-llm").trigger("click")
  await flushPromises()
  currentConfig.routes.translation = "remote-b"
  currentConfig.local_fallback_enabled = false
  currentConfig.profiles.find(profile => profile.id === "remote-b")!.ready = false
  currentConfig.profiles.find(profile => profile.id === "remote-a")!.ready = false
  const local = currentConfig.profiles.find(profile => profile.source === "managed-local")!
  local.ready = true
  local.verified_capabilities = ["text", "vision"]
  wrapper.findComponent(LlmSettingsDialog).vm.$emit("saved", currentConfig)
  await flushPromises()
  const settings = wrapper.findComponent(TagTranslationSettingsDialog)
  expect(settings.props()).toMatchObject({ loading: false, remoteConfigured: false, sharedLocalReady: true, llmMode: "remote" })
  completeOld(oldConfig)
  await flushPromises()
  expect(settings.props()).toMatchObject({ loading: false, remoteConfigured: false, sharedLocalReady: true, llmMode: "remote" })
  expect(llmApi.saveConfig).not.toHaveBeenCalled()
})
