<script setup lang="ts">
import { computed, onActivated, onDeactivated, onUnmounted, ref, watch } from "vue"
import { ElDropdown, ElDropdownItem, ElDropdownMenu, ElInput, ElOption, ElSelect, ElSwitch, ElMessage, ElMessageBox } from "element-plus"
import { Setting } from "@element-plus/icons-vue"
import { useI18n } from "vue-i18n"
import { useRoute, useRouter } from "vue-router"
import { datasetApi, type ChangedItem, type DatasetItem, type LocalModelStatus, type LlmProfile, type TagDictionaryStatus } from "../api/dataset"
import { datasetFileUrl, datasetsApi } from "../api/datasets"
import TagFilterPanel from "../components/dataset/TagFilterPanel.vue"
import TagTranslationControls from "../components/dataset/TagTranslationControls.vue"
import TagTranslationSettingsDialog from "../components/dataset/TagTranslationSettingsDialog.vue"
import ManagedDatasetPicker from "../components/dataset/ManagedDatasetPicker.vue"
import { useDatasetTagFilter } from "../composables/useDatasetTagFilter"
import { addTagToCaption, moveCaptionTag, removeTagFromCaption, splitCaptionTags } from "../dataset/caption"
import { useTagTranslations } from "../composables/useTagTranslations"
import { useDatasetEditorSession } from "../composables/useDatasetEditorSession"

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
/** 标签编辑 = chips; 自由编辑 = raw caption text. */
const captionMode = ref<"tags" | "raw">("tags")
const translationProvider = editorSession.translationProvider
const { loading: translationsLoading, error: translationsError, progress: translationProgress, unresolved: translationUnresolved, resolve: resolveTranslations, translationFor, clearExternalCache, cancelCurrent: cancelTranslations } = useTagTranslations()
const translationSettingsOpen = ref(false)
const translationSettingsLoading = ref(false)
const translationSettingsSaving = ref(false)
const translationSettingsError = ref("")
const translationReadinessLoaded = ref(false)
const llmProfiles = ref<LlmProfile[]>([])
const activeRemoteId = ref("default")
const llmMode = ref<"remote" | "local">("remote")
const committedLlmProfiles = ref<LlmProfile[]>([])
const committedActiveRemoteId = ref("default")
const committedLlmMode = ref<"remote" | "local">("remote")
const translationCacheCount = ref(0)
const translationCacheClearing = ref(false)
const dictionaryStatus = ref<TagDictionaryStatus>({ state: "missing", installed: false, row_count: 0, size_bytes: 0, error: null })
const dictionaryBusy = ref(false)
const localModelStatus = ref<LocalModelStatus>({ state: "missing", model_id: "", model_filename: "", model_url: "", model_path: "", installed: false, size_bytes: 0, downloaded_bytes: 0, total_bytes: 0, runtime_path: "", endpoint: "internal://dataset-translation", port: 0, error: null })
const localModelBusy = ref(false)
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
const captionTags = computed(() => splitCaptionTags(caption.value))
const allDatasetTags = computed(() => {
  const unique = new Set<string>(tags.value.map((item) => item.tag))
  items.value.forEach((item) => {
    item.tags.forEach((tag) => unique.add(tag))
    const draft = root.value ? editorSession.getDraft(root.value, item.relative_path) : undefined
    splitCaptionTags(draft ?? item.caption).forEach((tag) => unique.add(tag))
  })
  return [...unique]
})
const allDatasetTagSignature = computed(() => [...allDatasetTags.value].sort().join("\u0000"))
const filterTagCounts = computed(() => {
  const counts = new Map<string, number>()
  items.value.forEach((item) => {
    const draft = root.value ? editorSession.getDraft(root.value, item.relative_path) : undefined
    const sourceTags = draft === undefined ? item.tags : splitCaptionTags(draft)
    sourceTags.forEach((tag) => counts.set(tag, (counts.get(tag) || 0) + 1))
  })
  return [...counts].map(([tag, count]) => ({ tag, count })).sort((a, b) => b.count - a.count || a.tag.localeCompare(b.tag))
})
const filterItems = computed(() => items.value.map((item) => {
  const draft = root.value ? editorSession.getDraft(root.value, item.relative_path) : undefined
  return draft === undefined ? item : { ...item, tags: splitCaptionTags(draft) }
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

async function translateWholeDataset(localOnly = false) {
  if (!translationReadinessLoaded.value) await loadTranslationReadiness()
  if (!translationAvailable.value) {
    showTranslations.value = false
    cancelTranslations()
    ElMessage.warning(translationUnavailableHint.value)
    return
  }
  if (!allDatasetTags.value.length) return
  await resolveTranslations(allDatasetTags.value, translationProvider.value, "zh-CN", localOnly)
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
  if (!translationAvailable.value) {
    // 翻译是刚需：首次打开就用默认方式（Danbooru 词库）自动补齐。
    ElMessage.info(t("datasetEditor.caption.translationDownloading"))
    void startDefaultDictionaryDownload()
    return
  }
  if (translationProvider.value === "llm") {
    void ensureLlmReady().then((ready) => {
      if (ready && showTranslations.value && translationProvider.value === "llm") void translateWholeDataset()
    })
    return
  }
  void translateWholeDataset()
}

const dictionaryDownloading = ref(false)

/** Wait for the auto-started dictionary download, then translate. */
async function startDefaultDictionaryDownload() {
  if (dictionaryDownloading.value) return
  dictionaryDownloading.value = true
  try {
    await datasetApi.updateTagDictionary(false)
    for (let attempt = 0; attempt < 240; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 1500))
      if (!showTranslations.value) return
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

async function loadTranslationSettings(force = false) {
  if (translationSettingsLoading.value || (!force && llmProfiles.value.length)) return
  translationSettingsLoading.value = true
  translationSettingsError.value = ""
  try {
    const config = await datasetApi.tagTranslationConfig()
    llmProfiles.value = config.remote_profiles?.length
      ? config.remote_profiles
      : [{ ...config.deepseek, id: "default", name: t("datasetEditor.caption.translationProfileNew") }]
    activeRemoteId.value = config.active_remote_id || llmProfiles.value[0]?.id || "default"
    llmMode.value = config.llm_mode || (config.local?.enabled ? "local" : "remote")
    snapshotTranslationSettings()
  } catch (caught) {
    translationSettingsError.value = caught instanceof Error ? caught.message : String(caught)
  } finally {
    translationSettingsLoading.value = false
  }
}

async function loadTranslationReadiness() {
  await Promise.all([loadTranslationSettings(), loadDictionaryStatus(), loadLocalModelStatus()])
  translationReadinessLoaded.value = true
  if (!translationAvailable.value && showTranslations.value) {
    showTranslations.value = false
    cancelTranslations()
  }
}

async function saveTranslationSettings() {
  translationSettingsSaving.value = true
  translationSettingsError.value = ""
  try {
    await datasetApi.saveTagTranslationConfig({
      llm_mode: llmMode.value,
      active_remote_id: activeRemoteId.value,
      remote_profiles: llmProfiles.value,
      local: { enabled: llmMode.value === "local" },
    })
    snapshotTranslationSettings()
    clearExternalCache()
    if (showTranslations.value) void refreshTranslationsAfterSettingsChange()
  } catch (caught) {
    translationSettingsError.value = caught instanceof Error ? caught.message : String(caught)
    restoreTranslationSettings()
  } finally {
    translationSettingsSaving.value = false
  }
}

async function refreshTranslationsAfterSettingsChange() {
  if (!showTranslations.value) return
  if (translationProvider.value === "llm") {
    const ready = await ensureLlmReady()
    if (!ready || !showTranslations.value || translationProvider.value !== "llm") return
  }
  await translateWholeDataset()
}

const activeRemoteProfile = computed(() => llmProfiles.value.find((profile) => profile.id === activeRemoteId.value))
const remoteProfileConfigured = computed(() => {
  const profile = activeRemoteProfile.value
  if (!profile) return false
  const endpoint = profile.endpoint.trim().toLowerCase()
  return Boolean(profile.api_key_configured || /^http:\/\/(127\.0\.0\.1|localhost|\[::1\])(?::\d+)?\//.test(endpoint))
})
const localTranslationReady = computed(() => localModelStatus.value.state === "running")
const translationAvailable = computed(() => Boolean(dictionaryStatus.value.installed || remoteProfileConfigured.value || localTranslationReady.value))
const translationUnavailableHint = computed(() => t("datasetEditor.caption.translationUnavailable"))

async function ensureLlmReady() {
  await Promise.all([loadTranslationSettings(true), loadLocalModelStatus()])
  const ready = llmMode.value === "local" ? localModelStatus.value.state === "running" : remoteProfileConfigured.value
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
    loadTranslationSettings(true),
    loadTranslationCacheStatus(),
    loadDictionaryStatus(),
    loadLocalModelStatus(),
  ])
  translationReadinessLoaded.value = true
}

function onTranslationSettingsModelChange(value: boolean) {
  translationSettingsOpen.value = value
  if (!value) restoreTranslationSettings()
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
  try { localModelStatus.value = await datasetApi.localModelStatus() }
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

async function setupLocalModel() {
  localModelBusy.value = true
  try { localModelStatus.value = await datasetApi.setupLocalModel(); scheduleTranslationSettingsPoll() }
  catch (caught) { localModelStatus.value = { ...localModelStatus.value, state: "error", error: caught instanceof Error ? caught.message : String(caught) } }
  finally { localModelBusy.value = false }
}

async function cancelLocalModel() {
  localModelBusy.value = true
  try { localModelStatus.value = await datasetApi.cancelLocalModel() }
  catch (caught) { localModelStatus.value = { ...localModelStatus.value, state: "error", error: caught instanceof Error ? caught.message : String(caught) } }
  finally { localModelBusy.value = false }
}

async function startLocalModel() {
  localModelBusy.value = true
  try { localModelStatus.value = await datasetApi.startLocalModel() }
  catch (caught) { translationSettingsError.value = caught instanceof Error ? caught.message : String(caught) }
  finally { localModelBusy.value = false }
}

async function stopLocalModel() {
  localModelBusy.value = true
  try { localModelStatus.value = await datasetApi.stopLocalModel() }
  catch (caught) { translationSettingsError.value = caught instanceof Error ? caught.message : String(caught) }
  finally { localModelBusy.value = false }
}

async function clearTranslationCacheFromSettings() {
  translationCacheClearing.value = true
  try {
    await datasetApi.clearTagTranslationCache()
    clearExternalCache()
    translationCacheCount.value = 0
    if (showTranslations.value) void refreshTranslationsAfterSettingsChange()
  } catch (caught) {
    translationSettingsError.value = caught instanceof Error ? caught.message : String(caught)
  } finally {
    translationCacheClearing.value = false
  }
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
  const next = addTagToCaption(caption.value, newCaptionTag.value)
  if (next !== caption.value) caption.value = next
  newCaptionTag.value = ""
}

function removeCaptionTag(tag: string) {
  caption.value = removeTagFromCaption(caption.value, tag)
}

const dragTagIndex = ref<number | null>(null)

function onChipDragStart(index: number, event: DragEvent) {
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
  const from = dragTagIndex.value
  dragTagIndex.value = null
  if (from == null || from === toIndex) return
  caption.value = moveCaptionTag(caption.value, from, toIndex)
}

function onChipDragEnd() {
  dragTagIndex.value = null
}

let restoringCaption = false

function rememberCurrentDraft() {
  if (!captionHydrated || !root.value || !selected.value) return
  const item = items.value.find((candidate) => candidate.relative_path === selected.value)
  if (!item) return
  if (caption.value === item.caption) editorSession.clearDraft(root.value, selected.value)
  else editorSession.setDraft(root.value, selected.value, caption.value)
}

function choose(item: DatasetItem, event?: MouseEvent) {
  // Shift/Ctrl/Cmd click is a batch-selection gesture, not an editor switch.
  if (event && (event.shiftKey || event.ctrlKey || event.metaKey)) {
    toggleChecked(item, event)
    return
  }
  rememberCurrentDraft()
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

function apply(changes: ChangedItem[]) {
  const map = new Map(changes.map((item) => [item.image, item]))
  editorSession.clearDrafts(root.value, changes.map((item) => item.image))
  items.value = items.value.map((item) => {
    const change = map.get(item.relative_path)
    return change ? { ...item, caption: change.caption, tags: change.tags, caption_exists: change.caption_exists } : item
  })
  if (current.value) caption.value = current.value.caption
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
    if (restoredItem) choose(restoredItem)
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
  if (!current.value) return
  const request = scanGeneration
  try {
    const saved = await datasetApi.save(root.value, current.value.relative_path, caption.value)
    if (request !== scanGeneration) return
    apply([saved])
    await refreshHistory()
    if (request !== scanGeneration) return
    ElMessage.success(t("datasetEditor.caption.saved"))
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t("datasetEditor.caption.saveFail"))
  }
}

function splitTags(value: string) {
  return value.split(/[,，\n]/).map((item) => item.trim()).filter(Boolean)
}

async function batch() {
  if (!targets.value.length) return
  const request = scanGeneration
  try {
    await ElMessageBox.confirm(
      t("datasetEditor.batch.confirm", { n: targets.value.length }),
      selectedPaths.value.size ? t("datasetEditor.batch.confirmSelected") : t("datasetEditor.batch.confirmFiltered"),
    )
    if (request !== scanGeneration) return
    const replacements = replaceFrom.value.trim() ? [{ from: replaceFrom.value.trim(), to: replaceTo.value.trim() }] : []
    const data = await datasetApi.batch({
      root: root.value,
      images: targets.value.map((item) => item.relative_path),
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
    apply(data.items)
    await refreshHistory()
    if (request !== scanGeneration) return
    ElMessage.success(t("datasetEditor.batch.done", { n: data.changed }))
    rightPanelMode.value = "caption"
  } catch (error) {
    if (error !== "cancel" && error !== "close") ElMessage.error(error instanceof Error ? error.message : t("datasetEditor.batch.fail"))
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
  const request = scanGeneration
  try {
    const data = await datasetApi[kind](root.value)
    if (request !== scanGeneration) return
    apply(data.items)
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
    ElMessage.error(error instanceof Error ? error.message : t("datasetEditor.historyMsg.fail"))
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
  if (!restoringCaption) rememberCurrentDraft()
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
onActivated(() => {
  void loadTranslationReadiness()
  const queryPath = route?.query.path
  if (typeof queryPath === "string" && queryPath.trim() && queryPath !== path.value) {
    path.value = queryPath
    void scan()
  } else if (!items.value.length && path.value.trim()) {
    void scan()
  }
})
onDeactivated(() => {
  window.removeEventListener("keydown", onPreviewKeydown)
  previewOpen.value = false
  selectMenuOpen.value = false
  historyOpen.value = false
})
onUnmounted(() => {
  scanGeneration++
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
            :disabled="!root"
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
            @click="choose(item, $event)"
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
          <img
            class="caption-preview"
            :src="current.thumb_url + '&size=512'"
            :alt="current.name"
            :title="t('datasetEditor.caption.previewTip')"
            @click="previewOpen = true"
          >
          <span class="caption-filename" :title="current.relative_path">{{ current.name }}</span>
          <div v-if="managedName" class="caption-file-actions">
            <a :href="datasetFileUrl(managedName, current.relative_path)" download>{{ t("datasetEditor.caption.downloadImage") }}</a>
            <a
              v-if="current.caption_exists"
              :href="datasetFileUrl(managedName, current.relative_path.replace(/\.[^.]+$/, '.txt'))"
              download
            >{{ t("datasetEditor.caption.downloadCaption") }}</a>
          </div>
          <TagTranslationControls
            :enabled="showTranslations"
            :available="translationAvailable"
            :unavailable-hint="translationUnavailableHint"
            :loading="translationsLoading"
            :error="translationsError"
            :progress-completed="translationProgress.completed"
            :progress-total="translationProgress.total"
            :progress-unresolved="translationUnresolved"
            @update:enabled="setTranslationsEnabled"
          />
          <div class="caption-mode" role="group" :aria-label="t('datasetEditor.caption.modeAria')">
            <button type="button" :class="{ active: captionMode === 'tags' }" :aria-pressed="captionMode === 'tags'" @click="captionMode = 'tags'">{{ t("datasetEditor.caption.modeTags") }}</button>
            <button type="button" :class="{ active: captionMode === 'raw' }" :aria-pressed="captionMode === 'raw'" @click="captionMode = 'raw'">{{ t("datasetEditor.caption.modeRaw") }}</button>
          </div>
          <template v-if="captionMode === 'tags'">
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
            <span class="chip-add">
              <el-input v-model="newCaptionTag" :placeholder="t('datasetEditor.caption.addPlaceholder')" @keyup.enter="addCaptionTag" />
              <button type="button" @click="addCaptionTag">{{ t("datasetEditor.caption.add") }}</button>
            </span>
          </div>
          <small class="caption-drag-hint">{{ t("datasetEditor.caption.dragHint") }}</small>
          <details class="caption-raw">
            <summary>{{ t("datasetEditor.caption.rawToggle") }}</summary>
            <div class="caption-editor">
              <el-input v-model="caption" type="textarea" :rows="8" :aria-label="t('datasetEditor.caption.rawToggle')" />
              <small class="caption-count">{{ t("datasetEditor.caption.chars", { n: caption.length }) }}</small>
            </div>
          </details>
          </template>
          <div v-else class="caption-editor">
            <el-input v-model="caption" type="textarea" :rows="12" :aria-label="t('datasetEditor.caption.modeRaw')" />
            <small class="caption-count">{{ t("datasetEditor.caption.chars", { n: caption.length }) }}</small>
          </div>
          <button type="button" class="primary-action" @click="save">{{ t("datasetEditor.caption.save") }}</button>
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
          <button type="button" class="primary-action" :disabled="!targets.length" @click="batch">
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
    :model-value="translationSettingsOpen"
    :loading="translationSettingsLoading"
    :saving="translationSettingsSaving"
    :error="translationSettingsError"
    :provider="translationProvider"
    :profiles="llmProfiles"
    :active-remote-id="activeRemoteId"
    :llm-mode="llmMode"
    :cache-count="translationCacheCount"
    :clearing-cache="translationCacheClearing"
    :dictionary="dictionaryStatus"
    :dictionary-busy="dictionaryBusy"
    :local-model="localModelStatus"
    :local-model-busy="localModelBusy"
    :remote-configured="remoteProfileConfigured"
    @update:model-value="onTranslationSettingsModelChange"
    @update:profiles="llmProfiles = $event"
    @update:provider="setTranslationProvider"
    @update:active-remote-id="activeRemoteId = $event"
    @update:llm-mode="llmMode = $event"
    @save="saveTranslationSettings"
    @clear-cache="clearTranslationCacheFromSettings"
    @check-dictionary="checkDictionary"
    @update-dictionary="updateDictionary"
    @retry-dictionary="retryDictionary"
    @cancel-dictionary="cancelDictionary"
    @setup-local-model="setupLocalModel"
    @cancel-local-model="cancelLocalModel"
    @start-local-model="startLocalModel"
    @stop-local-model="stopLocalModel"
    @use-remote-mode="llmMode = 'remote'"
  />

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
