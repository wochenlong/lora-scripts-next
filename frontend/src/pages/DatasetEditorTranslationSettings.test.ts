// @vitest-environment jsdom
import { KeepAlive, defineComponent, ref } from "vue"
import { flushPromises, mount, type VueWrapper } from "@vue/test-utils"
import { afterEach, beforeEach, expect, it, vi } from "vitest"
import { datasetApi, type DatasetScan } from "../api/dataset"
import { datasetsApi } from "../api/datasets"
import { llmApi, type LlmConfig } from "../api/llm"
import LlmSettingsDialog from "../components/LlmSettingsDialog.vue"
import ManagedVisionModel from "../components/ManagedVisionModel.vue"
import TagTranslationControls from "../components/dataset/TagTranslationControls.vue"
import TagTranslationSettingsDialog from "../components/dataset/TagTranslationSettingsDialog.vue"
import { useDatasetEditorSession } from "../composables/useDatasetEditorSession"
import { useTagTranslations } from "../composables/useTagTranslations"
import { i18n } from "../i18n"
import DatasetEditorPage from "./DatasetEditorPage.vue"

const replaceRoute = vi.fn()
vi.mock("vue-router", () => ({ useRoute: () => ({ query: {} }), useRouter: () => ({ replace: replaceRoute }) }))
const state = useDatasetEditorSession()
const wrappers: VueWrapper[] = []
const visible = ref(true)
const Dialog = { props: { modelValue: { type: Boolean, required: true } }, template: '<div v-if="modelValue" class="test-dialog"><slot /><slot name="footer" /></div>' }
let currentConfig: LlmConfig

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
  state.translationProvider.value = "danbooru"
  state.rememberDataset("/translation-entry", "/translation-entry")
  useTagTranslations().clearCache()
  visible.value = true
  currentConfig = config()
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

it("refreshes shared routing and the current natural-language translation after saving", async () => {
  vi.mocked(datasetApi.scan).mockResolvedValue(scan(true))
  const wrapper = await render()
  await wrapper.get(".caption-editor textarea").setValue("An unsaved cat description.")
  await openManager(wrapper)
  state.showTranslations.value = true
  await flushPromises()
  await wrapper.get(".llm-settings select").setValue("remote-b")
  await wrapper.get(".llm-local-fallback").setValue(false)
  const statusReads = vi.mocked(llmApi.localVisionStatus).mock.calls.length
  await wrapper.get(".llm-save").trigger("click")
  await flushPromises()
  expect(llmApi.saveConfig).toHaveBeenCalledWith(expect.objectContaining({ routes: { translation: "remote-b", caption: "" }, local_fallback_enabled: false }))
  expect(wrapper.findComponent(TagTranslationSettingsDialog).props()).toMatchObject({ modelValue: true, llmMode: "remote", remoteConfigured: true })
  expect(vi.mocked(llmApi.localVisionStatus).mock.calls.length).toBeGreaterThan(statusReads)
  expect(llmApi.translateCaption).toHaveBeenCalledWith("An unsaved cat description.", false, expect.any(AbortSignal))
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
