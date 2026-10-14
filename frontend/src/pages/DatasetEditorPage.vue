<script setup lang="ts">
import { computed, onActivated, onDeactivated, onUnmounted, ref, watch } from "vue"
import { ElButton, ElDropdown, ElDropdownItem, ElDropdownMenu, ElInput, ElOption, ElSelect, ElSwitch, ElMessage, ElMessageBox } from "element-plus"
import { Setting } from "@element-plus/icons-vue"
import { useI18n } from "vue-i18n"
import { useRoute, useRouter } from "vue-router"
import { datasetApi, type CaptionFormat, type ChangedItem, type DatasetItem, type TagDictionaryStatus } from "../api/dataset"
import { DEFAULT_CAPTION_TRANSLATION_SETTINGS, llmApi, type CaptionTranslationSettings, type LlmConfig, type LlmProfile, type LocalVisionStatus } from "../api/llm"
import { datasetFileUrl, datasetsApi } from "../api/datasets"
import TagFilterPanel from "../components/dataset/TagFilterPanel.vue"
import TagTranslationControls from "../components/dataset/TagTranslationControls.vue"
import TagTranslationSettingsDialog from "../components/dataset/TagTranslationSettingsDialog.vue"
import LlmSettingsDialog from "../components/LlmSettingsDialog.vue"
import ManagedDatasetPicker from "../components/dataset/ManagedDatasetPicker.vue"
import { useDatasetTagFilter } from "../composables/useDatasetTagFilter"
import { addTagToCaption, captionEditingFormat, captionEditingTags, moveCaptionTag, removeTagFromCaption } from "../dataset/caption"
import { useTagTranslations } from "../composables/useTagTranslations"
import { useDatasetEditorSession } from "../composables/useDatasetEditorSession"
import { useCaptionTranslation } from "../composables/useCaptionTranslation"

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

type RightPanelMode = "caption" | "filter" | "batch"

const PAGE_SIZE_KEY = "dataset-editor-page-size"
const editorSession = useDatasetEditorSession()
const path = ref(editorSession.lastPath.value)
const root = editorSession.lastRoot
const items = editorSession.items
const tags = editorSession.tags
const categories = editorSession.categories
const category = editorSession.category
const query = editorSession.query
const selected = editorSession.selected
const selectedPaths = editorSession.selectedPaths
const lastSelectedIndex = ref<number>()
const initialItem = items.value.find((item) => item.relative_path === selected.value)
const caption = ref(initialItem && root.value ? editorSession.getDraft(root.value, initialItem.relative_path) ?? initialItem.caption : "")
let captionHydrated = Boolean(initialItem)
const append = ref("")
const remove = ref("")
const replaceFrom = ref("")
const replaceTo = ref("")
const clean = ref(false)
const sort = ref(false)
const underscoreToSpace = ref(false)
const stripEscapeChars = ref(false)
const loading = ref(false)
const mutationBusy = ref(false)
const appendPosition = ref<"front" | "back">("back")
const newCaptionTag = ref("")
const page = editorSession.page
const pageSize = ref(Number(localStorage.getItem(PAGE_SIZE_KEY)) || 48)
const historyOpen = ref(false)
const rightPanelMode = editorSession.rightPanelMode
const selectMenuOpen = ref(false)
const sessionHistory = editorSession.history
const previewOpen = ref(false)
const showTranslations = editorSession.showTranslations
const captionTranslation = useCaptionTranslation()
let captionTranslationTimer: ReturnType<typeof setTimeout> | undefined
/** 标签编辑 = chips; 自由编辑 = raw caption text. */
const captionMode = ref<"tags" | "raw">("tags")
const newTagDraftImages = ref(new Set<string>())
const translationProvider = editorSession.translationProvider
const { loading: translationsLoading, error: translationsError, progress: translationProgress, unresolved: translationUnresolved, resolve: resolveTranslations, translationFor, cancelCurrent: cancelTranslations, configureCache } = useTagTranslations()
const translationSettingsOpen = ref(false)
const profileEditorOpen = ref(false)
const captionSettings = ref<CaptionTranslationSettings>({ ...DEFAULT_CAPTION_TRANSLATION_SETTINGS })
const captionSettingsRevision = ref("")
const captionSettingsLoaded = ref(false)
const captionSettingsLoading = ref(false)
const captionSettingsSaving = ref(false)
const captionSettingsError = ref("")
let captionSettingsGeneration = 0
let editorActive = true
let editorLifecycleGeneration = 0
let translationConfigGeneration = 0
let translationSettingsPending: Promise<void> | undefined
const sharedLocalTextReady = ref(false)
const translationSettingsLoading = ref(false)
const translationSettingsError = ref("")
const translationReadinessLoaded = ref(false)
const llmProfiles = ref<LlmProfile[]>([])
const activeRemoteId = ref("default")
const llmMode = ref<"remote" | "local">("remote")
const committedLlmProfiles = ref<LlmProfile[]>([])
const committedActiveRemoteId = ref("default")
const committedLlmMode = ref<"remote" | "local">("remote")
const translationCacheCount = ref(0)
const dictionaryStatus = ref<TagDictionaryStatus>({ state: "missing", installed: false, row_count: 0, size_bytes: 0, error: null })
const dictionaryBusy = ref(false)
const localModelStatus = ref<LocalVisionStatus>({ state: "missing", model_id: "", model_filename: "", model_url: "", model_path: "", installed: false, size_bytes: 0, downloaded_bytes: 0, total_bytes: 0, endpoint: "", port: 0, error: null })
const sharedConfigRevision = ref("")
let translationSettingsPoll: ReturnType<typeof setTimeout> | undefined
const managedPaths = ref<Array<{ name: string; path: string }>>([])
const managedName = computed(() => managedPaths.value.find((item) => item.path === root.value)?.name ?? "")

async function refreshManagedPaths() {
  try {
    const data = await datasetsApi.list()
    managedPaths.value = data.datasets.map(({ name, path: datasetPath }) => ({ name, path: datasetPath }))
  } catch {
    managedPaths.value = []
  }
}

function onPreviewKeydown(event: KeyboardEvent) {
  if (event.key !== "Escape") return
  previewOpen.value = false
  selectMenuOpen.value = false
  if (rightPanelMode.value !== "caption") rightPanelMode.value = "caption"
}

const filtered = computed(() =>
  tagFilteredItems.value.filter(
    (item) =>
      (!category.value || item.category === category.value) &&
      (!query.value ||
        item.caption.toLowerCase().includes(query.value.toLowerCase()) ||
        item.name.toLowerCase().includes(query.value.toLowerCase()) ||
        item.tags.some((tag) => tag.toLowerCase().includes(query.value.toLowerCase()))),
  ),
)
const pageCount = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize.value)))
const paged = computed(() => filtered.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))
const current = computed(() => items.value.find((item) => item.relative_path === selected.value))
/** The single-image panel only earns its 320px when it has something to show. */
const panelOpen = computed(() => rightPanelMode.value !== "caption" || Boolean(current.value))
const targets = computed(() =>
  selectedPaths.value.size ? items.value.filter((item) => selectedPaths.value.has(item.relative_path)) : filtered.value,
)
const captionFormat = computed(() => !current.value?.caption_exists && newTagDraftImages.value.has(editKey(selected.value))
  ? "tag" : captionEditingFormat(caption.value, current.value))
const captionTags = computed(() => current.value ? captionEditingTags(caption.value, { ...current.value, caption_exists: newTagDraftImages.value.has(editKey(selected.value)) || current.value.caption_exists, caption_format: captionFormat.value }) : [])
const tagEditingAllowed = computed(() => captionFormat.value === "tag" || (!current.value?.caption_exists && !caption.value.trim()))
const batchTagEditingAllowed = computed(() => targets.value.every(item => {
  const text = editorSession.getDraft(root.value, item.relative_path) ?? item.caption
  return captionEditingFormat(text, item) === "tag" || (!item.caption_exists && !text.trim())
}))
const allDatasetTags = computed(() => {
  const unique = new Set<string>(tags.value.map((item) => item.tag))
  items.value.forEach((item) => {
    item.tags.forEach((tag) => unique.add(tag))
    const draft = root.value ? editorSession.getDraft(root.value, item.relative_path) : undefined
    if (draft !== undefined) captionEditingTags(draft, item).forEach((tag) => unique.add(tag))
  })
  return [...unique]
})
const allDatasetTagSignature = computed(() => [...allDatasetTags.value].sort().join("\u0000"))
const filterTagCounts = computed(() => {
  const counts = new Map<string, number>()
  items.value.forEach((item) => {
    const draft = root.value ? editorSession.getDraft(root.value, item.relative_path) : undefined
    const sourceTags = draft === undefined ? item.tags : captionEditingTags(draft, item)
    sourceTags.forEach((tag) => counts.set(tag, (counts.get(tag) || 0) + 1))
  })
  return [...counts].map(([tag, count]) => ({ tag, count })).sort((a, b) => b.count - a.count || a.tag.localeCompare(b.tag))
})
const filterItems = computed(() => items.value.map((item) => {
  const draft = root.value ? editorSession.getDraft(root.value, item.relative_path) : undefined
  return draft === undefined ? item : { ...item, tags: captionEditingTags(draft, item) }
}))
const { state: tagFilter, filteredItems: tagFilteredItems, visibleTagList, hasActiveFilter, toggleTag, clearTags, reset: resetTagFilter } =
  useDatasetTagFilter(filterItems, filterTagCounts, editorSession.tagFilter)
const hasWorkingFilter = computed(
  () => Boolean(category.value) || Boolean(query.value.trim()) || hasActiveFilter.value,
)
const totalImageCount = computed(() => items.value.length)
const workingScopeCount = computed(() => filtered.value.length)
const workingScopeFullySelected = computed(
  () =>
    filtered.value.length > 0 &&
    filtered.value.every((item) => selectedPaths.value.has(item.relative_path)),
)

async function translateWholeDataset() {
  if (!tagEditingAllowed.value) return
  if (!translationReadinessLoaded.value) await loadTranslationReadiness()
  if (!translationAvailable.value) {
    showTranslations.value = false
    cancelTranslations()
    ElMessage.warning(translationUnavailableHint.value)
    return
  }
  if (!allDatasetTags.value.length) return
  await resolveTranslations(allDatasetTags.value, translationProvider.value, "zh-CN")
}

let translationRefreshTimer: ReturnType<typeof setTimeout> | undefined

function scheduleTranslationRefresh() {
  if (!showTranslations.value) return
  if (translationRefreshTimer) clearTimeout(translationRefreshTimer)
  translationRefreshTimer = setTimeout(() => {
    translationRefreshTimer = undefined
    void translateWholeDataset()
  }, 350)
}

async function setTranslationsEnabled(value: boolean) {
  if (!value) {
    showTranslations.value = false
    cancelTranslations()
    return
  }
  showTranslations.value = true
  if (!translationReadinessLoaded.value) await loadTranslationReadiness()
  // Readiness can reset the switch while its request is in flight; re-assert it.
  showTranslations.value = true
  if (translationProvider.value === "llm") {
    void ensureLlmReady().then((ready) => {
      if (ready && showTranslations.value && translationProvider.value === "llm") void translateWholeDataset()
    })
    return
  }
  if (!translationAvailable.value) {
    // 翻译是刚需：首次打开就用默认方式（Danbooru 词库）自动补齐。
    ElMessage.info(t("datasetEditor.caption.translationDownloading"))
    void startDefaultDictionaryDownload()
    return
  }
  void translateWholeDataset()
}

const dictionaryDownloading = ref(false)
/** Set on unmount so the download poll stops touching a disposed page. */
let dictionaryPollDisposed = false

/** Wait for the auto-started dictionary download, then translate. */
async function startDefaultDictionaryDownload() {
  if (dictionaryDownloading.value) return
  dictionaryDownloading.value = true
  try {
    await datasetApi.updateTagDictionary(false)
    for (let attempt = 0; attempt < 240; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 1500))
      if (dictionaryPollDisposed || !showTranslations.value) return
      await loadDictionaryStatus()
      if (dictionaryStatus.value.installed) {
        ElMessage.success(t("datasetEditor.caption.translationDownloaded"))
        void translateWholeDataset()
        return
      }
      if (dictionaryStatus.value.state === "error") {
        ElMessage.error(dictionaryStatus.value.error || t("datasetEditor.caption.translationUnavailable"))
        return
      }
    }
    ElMessage.warning(t("datasetEditor.caption.translationUnavailable"))
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t("datasetEditor.caption.translationUnavailable"))
  } finally {
    dictionaryDownloading.value = false
  }
}

/** The dialog's source picker persists the LLM mode so the choice sticks. */
async function onLlmModeChange(value: "remote" | "local") {
  llmMode.value = value
  try {
    const current = await llmApi.config()
    const saved = await llmApi.saveConfig({
      ...current,
      revision: sharedConfigRevision.value || current.revision,
      local_fallback_enabled: value === "local",
      routes: { ...current.routes, translation: activeRemoteId.value },
    })
    sharedConfigRevision.value = saved.revision || ""
  } catch {
    // The settings page owns the full config; a transient failure keeps the local choice.
  }
}

async function refreshTranslationSettings(config: LlmConfig) {
  const lifecycle = editorLifecycleGeneration
  // Saved/test/runtime events carry the authoritative shared config. A late
  // settings request must not replace it with a pre-save snapshot.
  translationConfigGeneration += 1
  translationSettingsLoading.value = false
  translationSettingsError.value = ""
  applyTranslationSettings(config)
  await Promise.all([loadLocalModelStatus(), loadTranslationCacheStatus(), loadDictionaryStatus()])
  if (!editorActive || lifecycle !== editorLifecycleGeneration) return
  translationReadinessLoaded.value = true
  await refreshTranslationsAfterSettingsChange()
}

function setTranslationProvider(value: typeof translationProvider.value) {
  translationProvider.value = value
  cancelTranslations()
  if (value === "llm") {
    void ensureLlmReady().then((ready) => {
      if (ready && showTranslations.value && translationProvider.value === "llm") void translateWholeDataset()
    })
    return
  }
  if (showTranslations.value) void translateWholeDataset()
}

function cloneProfiles(profiles: LlmProfile[]) {
  return profiles.map((profile) => ({ ...profile }))
}

function snapshotTranslationSettings() {
  committedLlmProfiles.value = cloneProfiles(llmProfiles.value)
  committedActiveRemoteId.value = activeRemoteId.value
  committedLlmMode.value = llmMode.value
}

function restoreTranslationSettings() {
  llmProfiles.value = cloneProfiles(committedLlmProfiles.value)
  activeRemoteId.value = committedActiveRemoteId.value
  llmMode.value = committedLlmMode.value
}

function applyTranslationSettings(config: LlmConfig) {
  sharedConfigRevision.value = config.revision || ""
  configureCache(config.cache.translation !== false, config.revision || JSON.stringify(config.profiles))
  sharedLocalTextReady.value = config.profiles.some(profile => profile.source !== "remote" && translationProfileReady(profile))
  llmProfiles.value = config.profiles
  const configuredRoute = config.routes.translation
  activeRemoteId.value = config.profiles.some(profile => profile.source === "remote" && profile.id === configuredRoute)
    ? configuredRoute
    : config.profiles.find(profile => profile.source === "remote")?.id || "default"
  llmMode.value = config.local_fallback_enabled ? "local" : "remote"
  snapshotTranslationSettings()
}

function loadTranslationSettings(force = false): Promise<void> {
  if (translationSettingsLoading.value && translationSettingsPending) return translationSettingsPending
  if (!force && llmProfiles.value.length) return Promise.resolve()
  const generation = ++translationConfigGeneration
  translationSettingsLoading.value = true
  translationSettingsError.value = ""
  translationSettingsPending = (async () => {
    try {
      const config = await llmApi.config()
      if (generation !== translationConfigGeneration) return
      applyTranslationSettings(config)
    } catch (caught) {
      if (generation === translationConfigGeneration) translationSettingsError.value = caught instanceof Error ? caught.message : String(caught)
    } finally {
      if (generation === translationConfigGeneration) translationSettingsLoading.value = false
    }
  })()
  return translationSettingsPending
}

async function loadTranslationReadiness(force = false) {
  const lifecycle = editorLifecycleGeneration
  await Promise.all([loadTranslationSettings(force), loadDictionaryStatus(), loadLocalModelStatus()])
  if (!editorActive || lifecycle !== editorLifecycleGeneration) return
  translationReadinessLoaded.value = true
  if (tagEditingAllowed.value && !translationAvailable.value && showTranslations.value && !dictionaryDownloading.value) {
    showTranslations.value = false
    cancelTranslations()
  }
}

async function refreshTranslationsAfterSettingsChange() {
  if (!showTranslations.value) return
  if (!tagEditingAllowed.value) {
    await captionTranslation.translate(caption.value)
    return
  }
  if (translationProvider.value === "llm") {
    const ready = await ensureLlmReady()
    if (!ready || !showTranslations.value || translationProvider.value !== "llm") return
  }
  await translateWholeDataset()
}

function translationProfileReady(profile: LlmProfile) {
  return Boolean(profile.enabled && profile.ready && profile.capabilities.includes("text") &&
    profile.verified_capabilities?.includes("text") &&
    (profile.languages.includes("zh-CN") || profile.languages.includes("*")))
}
const remoteProfileConfigured = computed(() => llmProfiles.value.some(profile => {
  if (profile.source !== "remote" || !translationProfileReady(profile)) return false
  const endpoint = profile.endpoint.trim().toLowerCase()
  return Boolean(profile.api_key_configured || /^http:\/\/(127\.0\.0\.1|localhost|\[::1\])(?::\d+)?\//.test(endpoint))
}))
const localTranslationReady = computed(() => llmProfiles.value.some(profile => translationProfileReady(profile) && (
  profile.source === "local-endpoint" ||
  (profile.source === "managed-local" && localModelStatus.value.state === "running" && localModelStatus.value.installed)
)))
const translationAvailable = computed(() => Boolean(translationProvider.value === "mymemory" || dictionaryStatus.value.installed || remoteProfileConfigured.value || (llmMode.value === "local" && localTranslationReady.value)))
const translationUnavailableHint = computed(() => t("datasetEditor.caption.translationUnavailable"))

async function ensureLlmReady() {
  const lifecycle = editorLifecycleGeneration
  await Promise.all([loadTranslationSettings(true), loadLocalModelStatus()])
  if (!editorActive || lifecycle !== editorLifecycleGeneration) return false
  const ready = dictionaryStatus.value.installed || remoteProfileConfigured.value || (llmMode.value === "local" && localTranslationReady.value)
  if (!ready) {
    const message = llmMode.value === "local"
      ? t("datasetEditor.caption.translationLocalUnavailable")
      : t("datasetEditor.caption.translationRemoteNotConfigured")
    translationSettingsOpen.value = true
    await Promise.all([loadTranslationCacheStatus(), loadDictionaryStatus()])
    ElMessage.warning(message)
  }
  return ready
}

async function openTranslationSettings() {
  translationSettingsOpen.value = true
  await Promise.all([
    ...(!tagEditingAllowed.value ? [loadCaptionTranslationSettings()] : []),
    loadTranslationSettings(true),
    loadTranslationCacheStatus(),
    loadDictionaryStatus(),
    loadLocalModelStatus(),
  ])
  translationReadinessLoaded.value = true
}

function onTranslationSettingsModelChange(value: boolean) {
  // ElDialog emits false after its leave transition when we hide it to
  // show model management. Keep the return destination open in that case.
  if (!value && profileEditorOpen.value) return
  translationSettingsOpen.value = value
  if (!value) {
    invalidateCaptionSettings()
    restoreTranslationSettings()
  }
}

function invalidateCaptionSettings() {
  captionSettingsGeneration += 1
  captionSettingsLoading.value = false
  captionSettingsSaving.value = false
  captionSettingsLoaded.value = false
}

async function loadCaptionTranslationSettings() {
  const generation = ++captionSettingsGeneration
  const lifecycle = editorLifecycleGeneration
  captionSettingsLoading.value = true
  captionSettingsLoaded.value = false
  captionSettingsError.value = ""
  try {
    const result = await llmApi.captionTranslationSettings()
    if (!editorActive || lifecycle !== editorLifecycleGeneration || generation !== captionSettingsGeneration) return
    captionSettings.value = { ...result.settings }
    captionSettingsRevision.value = result.revision
    captionSettingsLoaded.value = true
  } catch (caught) {
    if (generation === captionSettingsGeneration && editorActive) captionSettingsError.value = caught instanceof Error ? caught.message : String(caught)
  } finally {
    if (generation === captionSettingsGeneration) captionSettingsLoading.value = false
  }
}

async function saveCaptionTranslationSettings(settings: CaptionTranslationSettings) {
  if (!captionSettingsLoaded.value || captionSettingsLoading.value || captionSettingsSaving.value) return
  const generation = ++captionSettingsGeneration
  const lifecycle = editorLifecycleGeneration
  captionSettingsSaving.value = true
  captionSettingsError.value = ""
  try {
    const result = await llmApi.saveCaptionTranslationSettings(settings, captionSettingsRevision.value)
    if (!editorActive || lifecycle !== editorLifecycleGeneration || generation !== captionSettingsGeneration) return
    captionSettings.value = { ...result.settings }
    captionSettingsRevision.value = result.revision
    ElMessage.success(t("datasetEditor.caption.naturalParametersSaved"))
    if (showTranslations.value && !tagEditingAllowed.value) void captionTranslation.translate(caption.value)
  } catch (caught) {
    if (generation === captionSettingsGeneration && editorActive) {
      captionSettingsError.value = caught instanceof Error ? caught.message : String(caught)
      // Reload explicitly before another save: another writer may own a newer revision.
      captionSettingsLoaded.value = false
    }
  } finally {
    if (generation === captionSettingsGeneration) captionSettingsSaving.value = false
  }
}

function goToLlmPage() {
  if (captionSettingsSaving.value) return
  rememberCurrentDraft()
  onTranslationSettingsModelChange(false)
  void router.push("/settings/api")
}

async function loadTranslationCacheStatus() {
  try {
    translationCacheCount.value = (await datasetApi.tagTranslationCache()).total
  } catch {
    translationCacheCount.value = 0
  }
}

async function loadDictionaryStatus() {
  try {
    dictionaryStatus.value = await datasetApi.tagDictionaryStatus()
  } catch (caught) {
    dictionaryStatus.value = { ...dictionaryStatus.value, state: "error", error: caught instanceof Error ? caught.message : String(caught) }
  }
}

async function loadLocalModelStatus() {
  try { localModelStatus.value = await llmApi.localVisionStatus() }
  catch (caught) { localModelStatus.value = { ...localModelStatus.value, state: "error", error: caught instanceof Error ? caught.message : String(caught) } }
}

function scheduleTranslationSettingsPoll() {
  if (translationSettingsPoll) clearTimeout(translationSettingsPoll)
  if (dictionaryStatus.value.state !== "downloading" && localModelStatus.value.state !== "downloading" && localModelStatus.value.state !== "installing" && localModelStatus.value.runtime_state !== "installing") return
  translationSettingsPoll = setTimeout(async () => {
    await Promise.all([loadDictionaryStatus(), loadLocalModelStatus()])
    scheduleTranslationSettingsPoll()
  }, 1000)
}

async function checkDictionary() {
  dictionaryBusy.value = true
  try { dictionaryStatus.value = await datasetApi.checkTagDictionary() }
  catch (caught) { dictionaryStatus.value = { ...dictionaryStatus.value, state: "error", error: caught instanceof Error ? caught.message : String(caught) } }
  finally { dictionaryBusy.value = false }
}

async function updateDictionary() {
  dictionaryBusy.value = true
  try { dictionaryStatus.value = await datasetApi.updateTagDictionary(false); scheduleTranslationSettingsPoll() }
  catch (caught) { dictionaryStatus.value = { ...dictionaryStatus.value, state: "error", error: caught instanceof Error ? caught.message : String(caught) } }
  finally { dictionaryBusy.value = false }
}

async function retryDictionary() {
  dictionaryBusy.value = true
  try { dictionaryStatus.value = await datasetApi.retryTagDictionary(); scheduleTranslationSettingsPoll() }
  catch (caught) { dictionaryStatus.value = { ...dictionaryStatus.value, state: "error", error: caught instanceof Error ? caught.message : String(caught) } }
  finally { dictionaryBusy.value = false }
}

async function cancelDictionary() {
  dictionaryBusy.value = true
  try { dictionaryStatus.value = await datasetApi.cancelTagDictionary() }
  catch (caught) { dictionaryStatus.value = { ...dictionaryStatus.value, state: "error", error: caught instanceof Error ? caught.message : String(caught) } }
  finally { dictionaryBusy.value = false }
}

const selectAllLabel = computed(() =>
  workingScopeFullySelected.value
    ? t("datasetEditor.gallery.deselectAll", { n: workingScopeCount.value })
    : hasWorkingFilter.value
      ? t("datasetEditor.gallery.selectFiltered", { n: workingScopeCount.value })
      : t("datasetEditor.gallery.selectAll", { n: workingScopeCount.value }),
)
const panelTitle = computed(() => {
  if (rightPanelMode.value === "filter") return t("datasetEditor.filter.drawerTitle")
  if (rightPanelMode.value === "batch") {
    return selectedPaths.value.size
      ? t("datasetEditor.batch.drawerTitleSelected", { n: selectedPaths.value.size })
      : t("datasetEditor.batch.drawerTitle")
  }
  return t("datasetEditor.caption.panelTitle")
})

function openRightPanel(mode: RightPanelMode) {
  rightPanelMode.value = rightPanelMode.value === mode && mode !== "caption" ? "caption" : mode
}

function closeToolPanel() {
  rightPanelMode.value = "caption"
}

/** Closing the single-image panel goes back to the pure gallery. */
function closePanel() {
  if (rightPanelMode.value !== "caption") {
    closeToolPanel()
    return
  }
  rememberCurrentDraft()
  selected.value = ""
  editorSession.rememberSelection("")
}

function addCaptionTag() {
  if (!tagEditingAllowed.value) {
    ElMessage.warning(t("datasetEditor.caption.naturalTagEditBlocked"))
    return
  }
  const next = addTagToCaption(caption.value, newCaptionTag.value, tagEditingAllowed.value ? "tag" : captionFormat.value)
  if (next !== caption.value) {
    if (!current.value?.caption_exists) newTagDraftImages.value = new Set([...newTagDraftImages.value, editKey(selected.value)])
    caption.value = next
  }
  newCaptionTag.value = ""
}

function removeCaptionTag(tag: string) {
  if (!tagEditingAllowed.value) {
    ElMessage.warning(t("datasetEditor.caption.naturalTagEditBlocked"))
    return
  }
  caption.value = removeTagFromCaption(caption.value, tag, captionFormat.value)
}

const dragTagIndex = ref<number | null>(null)

function onChipDragStart(index: number, event: DragEvent) {
  if (!tagEditingAllowed.value) { event.preventDefault(); return }
  dragTagIndex.value = index
  event.dataTransfer?.setData("text/plain", String(index))
  if (event.dataTransfer) event.dataTransfer.effectAllowed = "move"
}

function onChipDragOver(event: DragEvent) {
  event.preventDefault()
  if (event.dataTransfer) event.dataTransfer.dropEffect = "move"
}

function onChipDrop(toIndex: number, event: DragEvent) {
  event.preventDefault()
  if (!tagEditingAllowed.value) return
  const from = dragTagIndex.value
  dragTagIndex.value = null
  if (from == null || from === toIndex) return
  caption.value = moveCaptionTag(caption.value, from, toIndex, captionFormat.value)
}

function onChipDragEnd() {
  dragTagIndex.value = null
}

watch(tagEditingAllowed, (allowed) => {
  if (!allowed) captionMode.value = "raw"
}, { immediate: true })

let restoringCaption = false
const captionEdits = new Map<string, { version: number; text: string }>()

function editKey(image: string) { return `${root.value}\u0000${image}` }

function rememberCurrentDraft() {
  if (!captionHydrated || !root.value || !selected.value) return
  const item = items.value.find((candidate) => candidate.relative_path === selected.value)
  if (!item) return
  if (caption.value === item.caption) editorSession.clearDraft(root.value, selected.value)
  else editorSession.setDraft(root.value, selected.value, caption.value)
}

async function restoreDiskCaption() {
  if (!current.value) return
  try { await ElMessageBox.confirm(t('datasetEditor.caption.restoreDiskConfirm'), { type: "warning" }) }
  catch { return }
  editorSession.clearDraft(root.value, current.value.relative_path)
  restoringCaption = true
  caption.value = current.value.caption
  restoringCaption = false
}

function cancelCaptionTranslation() {
  if (captionTranslationTimer) clearTimeout(captionTranslationTimer)
  captionTranslationTimer = undefined
  captionTranslation.cancel()
}

watch([caption, selected, root, showTranslations, tagEditingAllowed], () => {
  cancelCaptionTranslation()
  if (!showTranslations.value || tagEditingAllowed.value || !caption.value.trim()) return
  captionTranslationTimer = setTimeout(() => {
    captionTranslationTimer = undefined
    void captionTranslation.translate(caption.value)
  }, 350)
})

function choose(item: DatasetItem, event?: MouseEvent, remember = true) {
  // Modifier clicks update batch selection without switching the editor.
  if (event && (event.shiftKey || event.ctrlKey || event.metaKey)) {
    toggleChecked(item, event)
    return
  }
  if (remember) rememberCurrentDraft()
  selected.value = item.relative_path
  editorSession.rememberSelection(item.relative_path)
  restoringCaption = true
  caption.value = root.value ? editorSession.getDraft(root.value, item.relative_path) ?? item.caption : item.caption
  restoringCaption = false
  captionHydrated = true
  rightPanelMode.value = "caption"
  lastSelectedIndex.value = filtered.value.findIndex((candidate) => candidate.relative_path === item.relative_path)
}

/** Batch selection lives on the tile checkbox; Shift extends a range. */
function toggleChecked(item: DatasetItem, event?: MouseEvent) {
  const index = filtered.value.findIndex((candidate) => candidate.relative_path === item.relative_path)
  const next = new Set(selectedPaths.value)
  if (event?.shiftKey && lastSelectedIndex.value !== undefined && lastSelectedIndex.value >= 0) {
    const [start, end] = [lastSelectedIndex.value, index].sort((a, b) => a - b)
    filtered.value.slice(start, end + 1).forEach((candidate) => next.add(candidate.relative_path))
  } else if (next.has(item.relative_path)) {
    next.delete(item.relative_path)
  } else {
    next.add(item.relative_path)
  }
  selectedPaths.value = next
  lastSelectedIndex.value = index
}

/** Double clicking a tile opens the full-size preview for it. */
function openLightbox(item: DatasetItem) {
  if (selected.value !== item.relative_path) choose(item)
  previewOpen.value = true
}

function draftSnapshot(images: string[]) {
  return new Map(images.map(image => [image, {
    draft: editorSession.getDraft(root.value, image), version: captionEdits.get(editKey(image))?.version ?? 0,
  }]))
}

function apply(changes: ChangedItem[], consumedDrafts = new Map<string, { draft: string | undefined; version: number }>()) {
  const map = new Map(changes.map((item) => [item.image, item]))
  for (const change of changes) {
    const snapshot = consumedDrafts.get(change.image)
    const edited = captionEdits.get(editKey(change.image))
    if (snapshot && edited && edited.version !== snapshot.version) {
      editorSession.setDraft(root.value, change.image, edited.text)
    } else if (snapshot && editorSession.getDraft(root.value, change.image) === snapshot.draft) {
      editorSession.clearDraft(root.value, change.image)
    }
  }
  items.value = items.value.map((item) => {
    const change = map.get(item.relative_path)
    return change ? { ...item, caption: change.caption, tags: change.tags, caption_exists: change.caption_exists, caption_format: change.caption_format ?? item.caption_format, caption_sha256: change.caption_sha256 } : item
  })
  if (current.value) {
    restoringCaption = true
    caption.value = editorSession.getDraft(root.value, current.value.relative_path) ?? current.value.caption
    restoringCaption = false
  }
  rebuildTags()
}

function rebuildTags() {
  const counts = new Map<string, number>()
  items.value.forEach((item) => item.tags.forEach((tag) => counts.set(tag, (counts.get(tag) || 0) + 1)))
  tags.value = [...counts].map(([tag, count]) => ({ tag, count })).sort((a, b) => b.count - a.count || a.tag.localeCompare(b.tag))
}

async function refreshHistory() {
  const requestedRoot = root.value
  const request = scanGeneration
  if (!requestedRoot) return
  const data = await datasetApi.history(requestedRoot)
  if (root.value === requestedRoot && request === scanGeneration) sessionHistory.value = data
}

let scanGeneration = 0
async function toggleDataset() {
  if (!root.value) return scan()
  rememberCurrentDraft()
  const hasDrafts = Object.keys(editorSession.drafts.value).some(key => key.startsWith(`${root.value}\u0000`))
  if (hasDrafts) {
    try { await ElMessageBox.confirm(t("datasetManage.unloadConfirm"), { type: "warning" }) }
    catch { return }
  }
  scanGeneration++
  cancelCaptionTranslation()
  cancelTranslations()
  if (translationRefreshTimer) clearTimeout(translationRefreshTimer)
  captionHydrated = false
  caption.value = ""
  previewOpen.value = false
  historyOpen.value = false
  selectMenuOpen.value = false
  editorSession.unload()
  resetTagFilter()
  path.value = ""
  loading.value = false
  if (route.query.path) {
    const nextQuery = { ...route.query }
    delete nextQuery.path
    await router.replace({ query: nextQuery })
  }
}

function selectManagedPath(next: string) {
  path.value = next
  void scan()
}

const pickerOpen = ref(false)
const datasetMenuOpen = ref(false)

let datasetMenuOutside: ((event: MouseEvent) => void) | undefined
function closeDatasetMenu() {
  datasetMenuOpen.value = false
  if (datasetMenuOutside) {
    document.removeEventListener("click", datasetMenuOutside)
    datasetMenuOutside = undefined
  }
}

function toggleDatasetMenu() {
  if (datasetMenuOpen.value) {
    closeDatasetMenu()
    return
  }
  datasetMenuOpen.value = true
  datasetMenuOutside = (event: MouseEvent) => {
    if (!(event.target as HTMLElement | null)?.closest?.(".dataset-split")) closeDatasetMenu()
  }
  // Defer so the click that opened the menu does not close it again.
  window.setTimeout(() => {
    if (datasetMenuOpen.value && datasetMenuOutside) document.addEventListener("click", datasetMenuOutside)
  }, 0)
}

/** The button tracks the typed path: load it, then re-load it as "更换". */
const scannerAction = computed<"load" | "replace">(() => (root.value ? "replace" : "load"))
const scannerLabel = computed(() => (scannerAction.value === "replace" ? t("datasetEditor.replace") : t("datasetEditor.scan")))

function runScannerAction() {
  if (!path.value.trim()) {
    pickerOpen.value = true
    return
  }
  void scan()
}

function onDatasetMenuAction(command: "pick" | "unload") {
  closeDatasetMenu()
  if (command === "pick") {
    pickerOpen.value = true
    return
  }
  void toggleDataset()
}

function onToolCommand(command: string | number | object) {
  if (command === "translation") {
    void openTranslationSettings()
    return
  }
  if (command === "history") {
    historyOpen.value = true
    return
  }
  if (command === "undo" || command === "redo") changeHistory(command)
}

async function scan() {
  if (!path.value.trim()) return
  const request = ++scanGeneration
  rememberCurrentDraft()
  loading.value = true
  try {
    const data = await datasetApi.scan(path.value)
    if (request !== scanGeneration) return
    const restoring = editorSession.lastRoot.value === data.root
    const restoredPanel = rightPanelMode.value
    // Keep server data as the baseline. Unsaved captions live in the session
    // draft map and are loaded only into the active editor field, so a draft
    // is never mistaken for a saved caption and cleared on the next switch.
    const restoredItems = data.items
    root.value = data.root
    path.value = data.root
    editorSession.rememberDataset(path.value, root.value)
    items.value = restoredItems
    tags.value = data.tags.sort((a, b) => b.count - a.count)
    categories.value = data.categories
    if (!restoring) {
      selectedPaths.value = new Set()
      selected.value = ""
      sessionHistory.value = { can_undo: false, can_redo: false, changes: [] }
      category.value = ""
      query.value = ""
      resetTagFilter()
      page.value = 1
      rightPanelMode.value = "caption"
    }
    // Default state is the pure gallery; only an explicit (restored) selection reopens the editor.
    const restoredItem = restoring && selected.value
      ? restoredItems.find((item) => item.relative_path === selected.value)
      : undefined
    if (restoredItem) choose(restoredItem, undefined, false)
    else {
      restoringCaption = true
      caption.value = ""
      restoringCaption = false
      captionHydrated = false
    }
    if (restoring) rightPanelMode.value = restoredPanel
    await Promise.all([refreshHistory(), refreshManagedPaths()])
    if (request !== scanGeneration) return
    if (showTranslations.value) void translateWholeDataset()
    ElMessage.success(t("datasetEditor.scanMsg.loaded", { n: data.total }))
  } catch (error) {
    if (request === scanGeneration) ElMessage.error(error instanceof Error ? error.message : t("datasetEditor.scanMsg.fail"))
  } finally {
    if (request === scanGeneration) loading.value = false
  }
}

async function save() {
  if (!current.value || mutationBusy.value) return
  const request = scanGeneration
  const requestedRoot = root.value
  const image = current.value.relative_path
  const submitted = caption.value
  const expectedHash = current.value.caption_sha256
  const explicitFormat = !current.value.caption_exists && newTagDraftImages.value.has(editKey(image)) ? "tag" as const : undefined
  const drafts = draftSnapshot([image])
  mutationBusy.value = true
  try {
    const saved = await datasetApi.save(requestedRoot, image, submitted, expectedHash, explicitFormat)
    if (request !== scanGeneration) return
    apply([saved], drafts)
    await refreshHistory()
    if (request !== scanGeneration) return
    ElMessage.success(t("datasetEditor.caption.saved"))
  } catch (error) {
    if (request === scanGeneration) ElMessage.error(error instanceof Error ? error.message : t("datasetEditor.caption.saveFail"))
  } finally {
    mutationBusy.value = false
  }
}

async function confirmCaptionFormat(format: Extract<CaptionFormat, "tag" | "natural">) {
  if (!current.value || mutationBusy.value) return
  const request = scanGeneration
  const requestedRoot = root.value
  const image = current.value.relative_path
  const expectedHash = current.value.caption_sha256 ?? null
  mutationBusy.value = true
  try {
    const changed = await datasetApi.confirmCaptionFormat(requestedRoot, image, format, expectedHash)
    if (request !== scanGeneration) return
    // This action only confirms the disk format; unsaved raw text stays a draft.
    apply([changed])
  } catch (error) {
    if (request === scanGeneration) ElMessage.error(error instanceof Error ? error.message : t("datasetEditor.caption.formatConfirmFailed"))
  } finally {
    mutationBusy.value = false
  }
}

function splitTags(value: string) {
  return value.split(/[,，\n]/).map((item) => item.trim()).filter(Boolean)
}

async function batch() {
  if (!targets.value.length || mutationBusy.value) return
  const request = scanGeneration
  if (!batchTagEditingAllowed.value) {
    ElMessage.warning(t("datasetEditor.caption.naturalBatchBlocked"))
    return
  }
  mutationBusy.value = true
  try {
    await ElMessageBox.confirm(
      t("datasetEditor.batch.confirm", { n: targets.value.length }),
      selectedPaths.value.size ? t("datasetEditor.batch.confirmSelected") : t("datasetEditor.batch.confirmFiltered"),
    )
    if (request !== scanGeneration) return
    const drafts = draftSnapshot(targets.value.map(item => item.relative_path))
    const replacements = replaceFrom.value.trim() ? [{ from: replaceFrom.value.trim(), to: replaceTo.value.trim() }] : []
    const data = await datasetApi.batch({
      root: root.value,
      images: targets.value.map((item) => item.relative_path),
      expected_hashes: Object.fromEntries(targets.value.map((item) => [item.relative_path, item.caption_sha256 ?? null])),
      append: splitTags(append.value),
      append_position: appendPosition.value,
      remove: splitTags(remove.value),
      replace: replacements,
      clean: clean.value,
      sort: sort.value,
      underscore_to_space: underscoreToSpace.value,
      strip_escape_chars: stripEscapeChars.value,
    })
    if (request !== scanGeneration) return
    apply(data.items, drafts)
    await refreshHistory()
    if (request !== scanGeneration) return
    ElMessage.success(t("datasetEditor.batch.done", { n: data.changed }))
    rightPanelMode.value = "caption"
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      await refreshHistory().catch(() => undefined)
      ElMessage.error(error instanceof Error ? error.message : t("datasetEditor.batch.fail"))
    }
  } finally {
    mutationBusy.value = false
  }
}

async function deleteTargets() {
  if (!managedName.value || !targets.value.length) return
  const request = scanGeneration
  try {
    await ElMessageBox.confirm(
      t("datasetEditor.batch.deleteConfirm", { n: targets.value.length }),
      { type: "warning" },
    )
  } catch {
    return
  }
  if (request !== scanGeneration) return
  try {
    const data = await datasetsApi.deleteFiles(managedName.value, targets.value.map((item) => item.relative_path))
    if (request !== scanGeneration) return
    ElMessage.success(t("datasetEditor.batch.deleteDone", { n: data.deleted.length }))
    if (data.missing.length) ElMessage.warning(t("datasetEditor.batch.deleteMissing", { n: data.missing.length }))
    await scan()
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t("datasetEditor.batch.deleteFail"))
  }
}

async function changeHistory(kind: "undo" | "redo") {
  if (mutationBusy.value) return
  const request = scanGeneration
  const drafts = draftSnapshot(items.value.map(item => item.relative_path))
  mutationBusy.value = true
  try {
    const data = await datasetApi[kind](root.value)
    if (request !== scanGeneration) return
    apply(data.items, drafts)
    await refreshHistory()
    if (request !== scanGeneration) return
    ElMessage.success(
      data.changed
        ? kind === "undo"
          ? t("datasetEditor.historyMsg.undone")
          : t("datasetEditor.historyMsg.redone")
        : t("datasetEditor.historyMsg.none"),
    )
  } catch (error) {
    await refreshHistory().catch(() => undefined)
    ElMessage.error(error instanceof Error ? error.message : t("datasetEditor.historyMsg.fail"))
  } finally {
    mutationBusy.value = false
  }
}

function selectWorkingScope() {
  if (workingScopeFullySelected.value) selectedPaths.value = new Set()
  else selectedPaths.value = new Set(filtered.value.map((item) => item.relative_path))
  selectMenuOpen.value = false
}

function selectEntireDataset() {
  selectedPaths.value = new Set(items.value.map((item) => item.relative_path))
  selectMenuOpen.value = false
}

function selectCurrentPageOnly() {
  selectedPaths.value = new Set(paged.value.map((item) => item.relative_path))
  selectMenuOpen.value = false
}

function clearSelection() {
  selectedPaths.value = new Set()
  selectMenuOpen.value = false
}

function clearAllFilters() {
  category.value = ""
  query.value = ""
  clearTags()
  tagFilter.excludeInput = ""
  tagFilter.logic = "and"
}

watch([category, query, pageSize], () => {
  page.value = 1
  localStorage.setItem(PAGE_SIZE_KEY, String(pageSize.value))
})
watch(caption, () => {
  if (!restoringCaption) {
    if (captionHydrated && root.value && selected.value) {
      const key = editKey(selected.value)
      captionEdits.set(key, { version: (captionEdits.get(key)?.version ?? 0) + 1, text: caption.value })
    }
    rememberCurrentDraft()
  }
}, { flush: "sync" })
watch(allDatasetTagSignature, () => {
  scheduleTranslationRefresh()
})
watch([showTranslations, translationProvider, category, query, page, rightPanelMode], () => {
  editorSession.rememberPreferences()
})
watch(() => [tagFilter.logic, tagFilter.selectedTags.size, tagFilter.excludeInput], () => {
  page.value = 1
  editorSession.rememberPreferences()
})
watch(() => [tagFilter.search, tagFilter.searchMode, tagFilter.sortBy, tagFilter.order], () => {
  editorSession.rememberPreferences()
})
watch(pageCount, (count) => {
  if (page.value > count) page.value = count
})
onActivated(() => window.addEventListener("keydown", onPreviewKeydown))
onActivated(async () => {
  editorActive = true
  const lifecycle = editorLifecycleGeneration
  translationReadinessLoaded.value = false
  await loadTranslationReadiness(true)
  if (!editorActive || lifecycle !== editorLifecycleGeneration) return
  const queryPath = route?.query.path
  if (typeof queryPath === "string" && queryPath.trim() && queryPath !== path.value) {
    path.value = queryPath
    void scan()
  } else if (path.value.trim()) {
    void scan()
  }
})
onDeactivated(() => {
  invalidateCaptionSettings()
  editorActive = false
  editorLifecycleGeneration += 1
  translationConfigGeneration += 1
  translationSettingsLoading.value = false
  rememberCurrentDraft()
  cancelCaptionTranslation()
  cancelTranslations()
  window.removeEventListener("keydown", onPreviewKeydown)
  previewOpen.value = false
  selectMenuOpen.value = false
  historyOpen.value = false
  translationSettingsOpen.value = false
  profileEditorOpen.value = false
  restoreTranslationSettings()
})
onUnmounted(() => {
  invalidateCaptionSettings()
  editorActive = false
  editorLifecycleGeneration += 1
  translationConfigGeneration += 1
  cancelCaptionTranslation()
  scanGeneration++
  dictionaryPollDisposed = true
  cancelTranslations()
  window.removeEventListener("keydown", onPreviewKeydown)
  closeDatasetMenu()
  if (translationSettingsPoll) clearTimeout(translationSettingsPoll)
  if (translationRefreshTimer) clearTimeout(translationRefreshTimer)
})
</script>

<template>
  <div class="dataset-page" :class="{ 'tool-panel-open': panelOpen }">
    <div class="dataset-workspace">
      <header class="dataset-toolbar">
        <div class="dataset-toolbar-top">
          <label class="dataset-toolbar-label" for="editor-dataset-path">{{ t("datasetEditor.pathLabel") }}</label>
          <span class="dataset-toolbar-controls">
            <input id="editor-dataset-path" v-model="path" class="dataset-direct-path" :disabled="loading" :placeholder="t('datasetEditor.toolbar.pathPlaceholder')" @keyup.enter="!loading && scan()" />
            <div class="dataset-split" :class="{ open: datasetMenuOpen }">
              <button data-testid="scan-action" type="button" class="dataset-tool-entry dataset-split-main" :class="{ 'is-primary': !root }" :disabled="loading" @click="runScannerAction">{{ scannerLabel }}</button>
              <button
                type="button"
                class="dataset-tool-entry dataset-split-caret"
                :class="{ 'is-primary': !root }"
                :disabled="loading"
                :aria-label="t('datasetEditor.datasetMenu')"
                :title="t('datasetEditor.datasetMenu')"
                :aria-expanded="datasetMenuOpen"
                @click="toggleDatasetMenu"
              >▼</button>
              <div v-if="datasetMenuOpen" class="dataset-split-menu" role="menu">
                <button type="button" role="menuitem" @click="onDatasetMenuAction('pick')">{{ t("datasetManage.selectDataset") }}</button>
                <button type="button" role="menuitem" :disabled="!root" @click="onDatasetMenuAction('unload')">{{ t("datasetManage.unload") }}</button>
              </div>
            </div>
            <ManagedDatasetPicker v-model:open="pickerOpen" hide-button :disabled="loading" :loaded="Boolean(root)" :initial-path="path" @select="selectManagedPath" />
            <span v-if="loading" role="status">{{ t("datasetEditor.scanning") }}</span>
          </span>
          <label class="dataset-toolbar-inline dataset-toolbar-search">
            <span>{{ t("datasetEditor.toolbar.searchLabel") }}</span>
            <el-input v-model="query" :placeholder="t('datasetEditor.filter.queryPlaceholder')" :disabled="!root" />
          </label>
        </div>
        <div class="dataset-toolbar-bottom">
          <label class="dataset-toolbar-inline dataset-toolbar-folder">
            <span>{{ t("datasetEditor.toolbar.folderLabel") }}</span>
            <el-select v-model="category" :disabled="!root" :aria-label="t('datasetEditor.toolbar.folderLabel')">
              <el-option value="" :label="t('datasetEditor.toolbar.folderAll', { n: totalImageCount || 0 })" />
              <el-option v-for="item in categories" :key="`tb-${item.value || '__root__'}`" :value="item.value" :label="`${item.name} (${item.count})`" />
            </el-select>
          </label>
          <div class="dataset-toolbar-actions">
          <button
            type="button"
            class="dataset-tool-entry"
            :class="{ active: rightPanelMode === 'filter', hot: hasWorkingFilter }"
            :disabled="!root"
            @click="openRightPanel('filter')"
          >
            {{ t("datasetEditor.filter.toggle") }}
            <small v-if="hasWorkingFilter">{{ t("datasetEditor.filter.activeBadge") }}</small>
          </button>
          <button
            type="button"
            class="dataset-tool-entry dataset-batch-entry"
            :class="{ active: rightPanelMode === 'batch' || selectedPaths.size > 0 }"
            :disabled="!root || !batchTagEditingAllowed"
            @click="openRightPanel('batch')"
          >
            {{ t("datasetEditor.batch.toolbar", { n: selectedPaths.size }) }}
          </button>
          <ElDropdown trigger="click" @command="onToolCommand">
            <button type="button" class="dataset-tool-entry dataset-tool-more" :disabled="!root" :aria-label="t('datasetEditor.gallery.more')" :title="t('datasetEditor.gallery.more')"><Setting /></button>
            <template #dropdown>
              <ElDropdownMenu>
                <ElDropdownItem command="translation">{{ t("datasetEditor.caption.translationSettings") }}</ElDropdownItem>
                <ElDropdownItem command="undo" :disabled="!sessionHistory.can_undo" divided>{{ t("datasetEditor.gallery.undo") }}</ElDropdownItem>
                <ElDropdownItem command="redo" :disabled="!sessionHistory.can_redo">{{ t("datasetEditor.gallery.redo") }}</ElDropdownItem>
                <ElDropdownItem command="history" :disabled="!root">{{ t("datasetEditor.gallery.history") }}</ElDropdownItem>
              </ElDropdownMenu>
            </template>
          </ElDropdown>
          </div>
        </div>
      </header>

      <main class="dataset-gallery">
        <header class="dataset-gallery-bar">
          <strong>{{ selectedPaths.size
            ? t("datasetEditor.gallery.count", { filtered: filtered.length, total: items.length, selected: selectedPaths.size })
            : t("datasetEditor.gallery.countPlain", { filtered: filtered.length, total: items.length }) }}</strong>
          <span v-if="root && items.length && !selectedPaths.size" class="dataset-gallery-hint">{{ selected ? t("datasetEditor.gallery.shiftHint") : t("datasetEditor.gallery.pickHint") }}</span>
          <div class="dataset-select-scope" :class="{ open: selectMenuOpen }">
            <button
              type="button"
              class="dataset-select-main"
              :class="{ active: workingScopeFullySelected }"
              :disabled="!root || !filtered.length"
              @click="selectWorkingScope"
            >
              {{ selectAllLabel }}
            </button>
            <button
              type="button"
              class="dataset-select-caret"
              :disabled="!root"
              :aria-label="t('datasetEditor.gallery.selectMenuAria')"
              :aria-expanded="selectMenuOpen"
              @click="selectMenuOpen = !selectMenuOpen"
            >
              ▼
            </button>
            <div v-if="selectMenuOpen" class="dataset-select-menu" role="menu">
              <button type="button" role="menuitem" :disabled="!items.length" @click="selectEntireDataset">
                {{ t("datasetEditor.gallery.selectEntire", { n: totalImageCount }) }}
              </button>
              <button type="button" role="menuitem" :disabled="!filtered.length" @click="selectWorkingScope">
                {{ t("datasetEditor.gallery.selectFiltered", { n: workingScopeCount }) }}
              </button>
              <button type="button" role="menuitem" :disabled="!paged.length" @click="selectCurrentPageOnly">
                {{ t("datasetEditor.gallery.selectPage", { n: paged.length }) }}
              </button>
              <button type="button" role="menuitem" :disabled="!selectedPaths.size" @click="clearSelection">
                {{ t("datasetEditor.gallery.clearSelection") }}
              </button>
            </div>
          </div>
        </header>
        <div v-if="!root" class="dataset-empty">
          <strong>{{ t("datasetEditor.gallery.emptyTitle") }}</strong>
          <span>{{ t("datasetEditor.gallery.emptyHint") }}</span>
        </div>
        <div v-else class="image-grid">
          <button
            v-for="item in paged"
            :key="item.relative_path"
            type="button"
            :class="{ active: selected === item.relative_path, checked: selectedPaths.has(item.relative_path) }"
            :title="t('datasetEditor.gallery.dblClickHint', { name: item.name })"
            @click="choose(item, $event)"
            @dblclick="openLightbox(item)"
          >
            <span
              class="image-grid-check"
              :class="{ checked: selectedPaths.has(item.relative_path) }"
              role="checkbox"
              :aria-checked="selectedPaths.has(item.relative_path)"
              :aria-label="t('datasetEditor.gallery.toggleSelect', { name: item.name })"
              :title="t('datasetEditor.gallery.toggleSelect', { name: item.name })"
              @click.stop="toggleChecked(item, $event)"
            ><i v-if="selectedPaths.has(item.relative_path)">✓</i></span>
            <img :src="item.thumb_url" :alt="item.name" loading="lazy">
            <span>{{ item.name }}</span>
          </button>
        </div>
        <footer class="dataset-pager">
          <button type="button" :disabled="page === 1" @click="page = 1">{{ t("datasetEditor.pager.first") }}</button>
          <button type="button" :disabled="page === 1" @click="page--">{{ t("datasetEditor.pager.prev") }}</button>
          <span>{{ page }} / {{ pageCount }}</span>
          <button type="button" :disabled="page === pageCount" @click="page++">{{ t("datasetEditor.pager.next") }}</button>
          <button type="button" :disabled="page === pageCount" @click="page = pageCount">{{ t("datasetEditor.pager.last") }}</button>
          <el-select v-model="pageSize" class="dataset-page-size" :aria-label="t('datasetEditor.pager.perPage', { size: pageSize })">
            <el-option v-for="size in [24, 48, 96, 192]" :key="size" :value="size" :label="t('datasetEditor.pager.perPage', { size })" />
          </el-select>
        </footer>
      </main>
    </div>

    <aside
      class="dataset-tool-panel"
      :class="[`is-${rightPanelMode}`, { glass: rightPanelMode !== 'caption' }]"
      :aria-label="panelTitle"
    >
      <header class="dataset-tool-panel-header">
        <strong>{{ panelTitle }}</strong>
        <button
          type="button"
          class="dataset-tool-panel-close"
          :aria-label="t('datasetEditor.filter.close')"
          @click="closePanel"
        >
          ×
        </button>
      </header>

      <div v-if="rightPanelMode === 'caption'" class="dataset-tool-panel-body caption-panel">
        <div v-if="current">
          <div class="caption-head">
            <img
              class="caption-preview"
              :src="current.thumb_url + '&size=512'"
              :alt="current.name"
              :title="t('datasetEditor.caption.previewTip')"
              @click="previewOpen = true"
            >
            <span class="caption-head-text">
              <span class="caption-filename" :title="current.relative_path">{{ current.name }}</span>
              <small class="caption-preview-hint">{{ t("datasetEditor.caption.previewTip") }}</small>
            </span>
          </div>
          <div v-if="managedName" class="caption-file-actions">
            <a :href="datasetFileUrl(managedName, current.relative_path)" download>{{ t("datasetEditor.caption.downloadImage") }}</a>
            <a
              v-if="current.caption_exists"
              :href="datasetFileUrl(managedName, current.relative_path.replace(/\.[^.]+$/, '.txt'))"
              download
            >{{ t("datasetEditor.caption.downloadCaption") }}</a>
          </div>
          <TagTranslationControls
            v-if="tagEditingAllowed"
            :enabled="showTranslations"
            :available="translationAvailable"
            :unavailable-hint="translationUnavailableHint"
            :loading="translationsLoading"
            :error="translationsError"
            :progress-completed="translationProgress.completed"
            :progress-total="translationProgress.total"
            :progress-unresolved="translationUnresolved"
            @update:enabled="setTranslationsEnabled"
            @open-settings="openTranslationSettings"
          />
          <section v-else class="natural-caption-translation">
            <div class="natural-translation-controls">
              <label>{{ t('datasetEditor.caption.naturalTranslation') }} <el-switch v-model="showTranslations" :aria-label="t('datasetEditor.caption.naturalTranslation')" /></label>
              <el-button class="caption-translation-settings-action" @click="openTranslationSettings">{{ t('datasetEditor.caption.translationSettings') }}</el-button>
              <el-button v-if="showTranslations" :disabled="captionTranslation.loading.value" @click="captionTranslation.translate(caption)">{{ t('datasetEditor.caption.retryNaturalTranslation') }}</el-button>
            </div>
            <p v-if="showTranslations && captionTranslation.loading.value" role="status">{{ t('datasetEditor.caption.naturalTranslating') }}</p>
            <p v-if="showTranslations && captionTranslation.error.value" role="alert">{{ captionTranslation.error.value }}</p>
            <div v-if="showTranslations && captionTranslation.text.value" class="natural-caption-translated" aria-live="polite">
              <small v-if="captionTranslation.alreadyChinese.value">{{ t('datasetEditor.caption.alreadyChinese') }}</small>
              <p>{{ captionTranslation.text.value }}</p>
            </div>
          </section>
          <p v-if="!tagEditingAllowed" class="caption-format-warning">{{ t("datasetEditor.caption.naturalCaptionReadOnly", { format: captionFormat }) }}</p>
          <div v-if="captionFormat === 'unknown' && current.caption_exists" class="caption-format-confirmation">
            <p>{{ t('datasetEditor.caption.unknownFormatHint') }}</p>
            <el-button class="caption-confirm-tag" :disabled="mutationBusy" @click="confirmCaptionFormat('tag')">{{ t('datasetEditor.caption.confirmTag') }}</el-button>
            <el-button class="caption-confirm-natural" :disabled="mutationBusy" @click="confirmCaptionFormat('natural')">{{ t('datasetEditor.caption.confirmNatural') }}</el-button>
          </div>
          <div v-if="tagEditingAllowed" class="caption-mode" role="group" :aria-label="t('datasetEditor.caption.modeAria')">
            <button type="button" :class="{ active: captionMode === 'tags' }" :aria-pressed="captionMode === 'tags'" @click="captionMode = 'tags'">{{ t("datasetEditor.caption.modeTags") }}</button>
            <button type="button" :class="{ active: captionMode === 'raw' }" :aria-pressed="captionMode === 'raw'" @click="captionMode = 'raw'">{{ t("datasetEditor.caption.modeRaw") }}</button>
          </div>
          <template v-if="tagEditingAllowed && captionMode === 'tags'">
          <div class="caption-chips" @dragover="onChipDragOver">
            <span
              v-for="(tag, index) in captionTags"
              :key="`${index}:${tag}`"
              class="chip"
              :class="{ dragging: dragTagIndex === index }"
              draggable="true"
              :title="t('datasetEditor.caption.dragTip')"
              @dragstart="onChipDragStart(index, $event)"
              @drop="onChipDrop(index, $event)"
              @dragend="onChipDragEnd"
            >
              <span class="caption-tag-text">{{ tag }}</span>
              <small v-if="showTranslations && translationFor(tag, translationProvider)" class="caption-tag-translation">{{ translationFor(tag, translationProvider) }}</small>
              <button type="button" :aria-label="t('datasetEditor.caption.removeAria', { tag })" @click="removeCaptionTag(tag)" @mousedown.stop>×</button>
            </span>
          </div>
          <div class="chip-add">
            <el-input v-model="newCaptionTag" :placeholder="t('datasetEditor.caption.addPlaceholder')" @keyup.enter="addCaptionTag" />
            <button type="button" @click="addCaptionTag">{{ t("datasetEditor.caption.add") }}</button>
          </div>
          <small class="caption-drag-hint">{{ t("datasetEditor.caption.dragHint") }}</small>
          </template>
          <div v-else class="caption-editor">
            <el-input v-model="caption" type="textarea" :autosize="{ minRows: 4, maxRows: 24 }" :aria-label="t('datasetEditor.caption.modeRaw')" />
            <small class="caption-count">{{ t("datasetEditor.caption.chars", { n: caption.length }) }}</small>
          </div>
          <el-button v-if="caption !== current.caption" class="caption-restore-disk" @click="restoreDiskCaption">{{ t('datasetEditor.caption.restoreDisk') }}</el-button>
          <button type="button" class="primary-action" :disabled="mutationBusy" @click="save">{{ t("datasetEditor.caption.save") }}</button>
        </div>
        <p v-else>{{ t("datasetEditor.caption.empty") }}</p>
      </div>

      <div v-else-if="rightPanelMode === 'filter'" class="dataset-tool-panel-body dataset-filter-body">
        <label>
          {{ t("datasetEditor.queryLabel") }}
          <el-input v-model="query" :placeholder="t('datasetEditor.filter.queryPlaceholder')" />
        </label>
        <label>
          {{ t("datasetEditor.categoryLabel") }}
          <el-select v-model="category">
            <el-option value="" :label="`${t('datasetEditor.allCategories')} (${totalImageCount})`" />
            <el-option v-for="item in categories" :key="item.value || '__root__'" :value="item.value" :label="`${item.name} (${item.count})`" />
          </el-select>
        </label>
        <TagFilterPanel
          :tags="visibleTagList"
          :selected-tags="tagFilter.selectedTags"
          :logic="tagFilter.logic"
          :search="tagFilter.search"
          :search-mode="tagFilter.searchMode"
          :sort-by="tagFilter.sortBy"
          :order="tagFilter.order"
          :exclude-input="tagFilter.excludeInput"
          :filtered-count="filtered.length"
          :show-select-all="false"
          :translation-enabled="showTranslations"
          :translation-provider="translationProvider"
          @update:logic="tagFilter.logic = $event"
          @update:search="tagFilter.search = $event"
          @update:search-mode="tagFilter.searchMode = $event"
          @update:sort-by="tagFilter.sortBy = $event"
          @update:order="tagFilter.order = $event"
          @update:exclude-input="tagFilter.excludeInput = $event"
          @toggle-tag="toggleTag"
          @clear="clearTags"
        />
        <div class="dataset-tool-panel-footer">
          <button type="button" class="dataset-tool-secondary" :disabled="!hasWorkingFilter" @click="clearAllFilters">
            {{ t("datasetEditor.filter.clearAll") }}
          </button>
          <button type="button" class="primary-action" @click="closeToolPanel">{{ t("datasetEditor.filter.done") }}</button>
        </div>
      </div>

      <div v-else class="dataset-tool-panel-body batch-body">
        <p class="dataset-batch-summary">
          {{
            selectedPaths.size
              ? t("datasetEditor.batch.selected", { n: selectedPaths.size })
              : t("datasetEditor.batch.filtered", { n: filtered.length })
          }}
        </p>
        <el-input v-model="append" :placeholder="t('datasetEditor.batch.appendPlaceholder')" />
        <el-select v-model="appendPosition" :aria-label="t('datasetEditor.batch.position')">
          <el-option value="back" :label="t('datasetEditor.batch.positionBack')" />
          <el-option value="front" :label="t('datasetEditor.batch.positionFront')" />
        </el-select>
        <el-input v-model="remove" :placeholder="t('datasetEditor.batch.removePlaceholder')" />
        <div class="replace-row">
          <el-input v-model="replaceFrom" :placeholder="t('datasetEditor.batch.replaceFrom')" />
          <el-input v-model="replaceTo" :placeholder="t('datasetEditor.batch.replaceTo')" />
        </div>
        <label>{{ t("datasetEditor.batch.clean") }}<el-switch v-model="clean" :aria-label="t('datasetEditor.batch.clean')" /></label>
        <label>{{ t("datasetEditor.batch.underscore") }}<el-switch v-model="underscoreToSpace" :aria-label="t('datasetEditor.batch.underscore')" /></label>
        <label>{{ t("datasetEditor.batch.stripEscape") }}<el-switch v-model="stripEscapeChars" :aria-label="t('datasetEditor.batch.stripEscape')" /></label>
        <label>{{ t("datasetEditor.batch.sort") }}<el-switch v-model="sort" :aria-label="t('datasetEditor.batch.sort')" /></label>
        <div class="dataset-tool-panel-footer">
          <button
            v-if="managedName"
            type="button"
            class="danger-action"
            :disabled="!targets.length"
            @click="deleteTargets"
          >
            {{ t("datasetEditor.batch.deleteFiles", { n: targets.length }) }}
          </button>
          <button type="button" class="dataset-tool-secondary" @click="closeToolPanel">{{ t("datasetEditor.batch.cancel") }}</button>
          <button type="button" class="primary-action" :disabled="mutationBusy || !targets.length" @click="batch">
            {{ t("datasetEditor.batch.applyTo", { n: targets.length }) }}
          </button>
        </div>
      </div>
    </aside>
  </div>

  <div
    v-if="previewOpen && current"
    class="dataset-lightbox"
    role="dialog"
    :aria-label="t('datasetEditor.caption.previewAria')"
    @click="previewOpen = false"
  >
    <img :src="current.image_url" :alt="current.name">
  </div>

  <TagTranslationSettingsDialog
    :model-value="translationSettingsOpen && !profileEditorOpen"
    :loading="translationSettingsLoading"
    :error="translationSettingsError"
    :provider="translationProvider"
    :content-type="tagEditingAllowed ? 'tag' : 'natural'"
    :caption-settings="captionSettings"
    :caption-settings-loaded="captionSettingsLoaded"
    :caption-settings-loading="captionSettingsLoading"
    :caption-settings-saving="captionSettingsSaving"
    :caption-settings-error="captionSettingsError"
    :llm-mode="llmMode"
    :dictionary="dictionaryStatus"
    :dictionary-busy="dictionaryBusy"
    :remote-configured="remoteProfileConfigured"
    :shared-local-ready="sharedLocalTextReady"
    @update:model-value="onTranslationSettingsModelChange"
    @update:provider="setTranslationProvider"
    @update:llm-mode="onLlmModeChange"
    @manage-llm="profileEditorOpen = true"
    @go-to-llm-page="goToLlmPage"
    @save-caption-settings="saveCaptionTranslationSettings"
    @reload-caption-settings="loadCaptionTranslationSettings"
    @check-dictionary="checkDictionary"
    @update-dictionary="updateDictionary"
    @retry-dictionary="retryDictionary"
    @cancel-dictionary="cancelDictionary"
  />

  <LlmSettingsDialog v-model="profileEditorOpen" capability="text" @saved="refreshTranslationSettings" />

  <el-dialog v-model="historyOpen" :title="t('datasetEditor.historyDialog.title')" width="min(820px, 94vw)">
    <div class="dataset-history">
      <article v-for="change in sessionHistory.changes" :key="`${change.label}-${change.items[0]?.image}`">
        <header>
          <strong>{{ change.label }}</strong>
          <span>{{ t("datasetEditor.historyDialog.count", { n: change.count }) }}</span>
        </header>
        <details>
          <summary>{{ t("datasetEditor.historyDialog.detail") }}</summary>
          <div v-for="item in change.items" :key="item.image">
            <code>{{ item.image }}</code>
            <del>{{ item.before || t("datasetEditor.historyDialog.noCaption") }}</del>
            <ins>{{ item.after || t("datasetEditor.historyDialog.noCaption") }}</ins>
          </div>
        </details>
      </article>
      <p v-if="!sessionHistory.changes.length">{{ t("datasetEditor.historyDialog.empty") }}</p>
    </div>
  </el-dialog>

</template>
