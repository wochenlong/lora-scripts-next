<script setup lang="ts">
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, reactive, ref, watch } from "vue"
import { ElMessage, ElMessageBox, ElSelect, ElOption, ElOptionGroup } from "element-plus"
import { Setting, Close, RefreshLeft } from "@element-plus/icons-vue"
import { storeToRefs } from "pinia"
import { useI18n } from "vue-i18n"
import { useRoute } from "vue-router"
import { useTaggerStore } from "../stores/tagger"
import { llmApi, type CaptionPromptPreset, type LocalVisionStatus } from "../api/llm"
import { taggerApi, tagJobRequest, type CaptionJobRequest, type TaggerModel, type TaggerRequest, type CaptionRollbackResult } from "../api/tagger"
import PathPickerDialog from "../components/PathPickerDialog.vue"
import LlmSettingsDialog from "../components/LlmSettingsDialog.vue"
import CaptionJobProgress from "../components/CaptionJobProgress.vue"
import CaptionPromptEditor from "../components/CaptionPromptEditor.vue"
import ManagedVisionModel from "../components/ManagedVisionModel.vue"
import ManagedDatasetPicker from "../components/dataset/ManagedDatasetPicker.vue"
import { useLlmProfiles } from "../composables/useLlmProfiles"
import { useTaggerJob } from "../composables/useTaggerJob"
import { useServerPathPick } from "../composables/useServerPathPick"
import { builtinCaptionPreset, captionBuiltins, englishCaptionPrompt } from "../dataset/captionPrompts"

const models = ["wd14-convnextv2-v2", "wd-convnext-v3", "wd-swinv2-v3", "wd-vit-v3", "wd14-swinv2-v2", "wd14-vit-v2", "wd14-moat-v2", "wd-eva02-large-tagger-v3", "wd-vit-large-tagger-v3", "cl_tagger_1_01"]
const form = reactive<TaggerRequest>({ path: "", interrogator_model: models[0], threshold: .35, character_threshold: .6, add_rating_tag: false, add_model_tag: false, additional_tags: "", exclude_tags: "", escape_tag: true, batch_input_recursive: false, batch_output_action_on_conflict: "copy", replace_underscore: true, replace_underscore_excludes: "0_0, (o)_(o), +_+, +_-, ._., <o>_<o>, <|>_<|>, =_=, >_<, 3_3, 6_9, >_o, @_@, ^_^, o_o, u_u, x_x, |_|, ||_||" })
const captionForm = reactive<CaptionJobRequest>({ path: "", mode: "natural", recursive: false, profile_id: undefined, prompt: englishCaptionPrompt, language: "en", conflict_action: "ignore", max_tokens: 512, temperature: 0, allow_local_fallback: false })
form.batch_output_action_on_conflict = "ignore"
const runtime = ref<"local" | "api">("local")
const catalog = ref<TaggerModel[]>([])
const selectedModelId = ref(models[0])
const selectedModel = computed(() => catalog.value.find(model => model.id === selectedModelId.value))
const method = ref<"tag" | "natural">("tag")
const mode = computed(() => method.value)
const parametersOpen = ref(false)
const parameterTab = ref("model")
const availableModels = computed(() => catalog.value.filter(model => model.runtime === runtime.value && model.output === mode.value && (model.output === "tag" || model.capabilities.includes("vision"))))
const modelGroups = computed(() => [...new Set(availableModels.value.map(model => model.family))].map(name => ({ name, models: availableModels.value.filter(model => model.family === name) })))
const apiAvailable = computed(() => mode.value === "natural" && catalog.value.some(model => model.runtime === "api" && model.output === "natural" && model.capabilities.includes("vision")))
const controlsLocked = computed(() => catalogLoading.value || busy.value || captionBusy.value || previewBusy.value || presetSaving.value)
const presetLanguageSupported = computed(() => selectedModel.value?.languages.includes(captionForm.language) || selectedModel.value?.languages.includes("*"))
const modelReady = computed(() => selectedModel.value?.ready && (mode.value === "tag" || presetLanguageSupported.value))
const catalogLoading = ref(false)
type PromptState = Pick<CaptionJobRequest, "prompt" | "language" | "max_caption_length"> & { system_prompt: string; name: string }
const modelDrafts = new Map<string, { tag: TaggerRequest; caption: CaptionJobRequest; presetId: string; presetName: string; systemPrompt: string; committed: PromptState }>()
const store = useTaggerStore()
const { status, error, submitting, busy } = storeToRefs(store)
const { t } = useI18n()
const route = useRoute()
const llmProfiles = useLlmProfiles("vision", computed(() => captionForm.language))
const captionJob = useTaggerJob()
const captionStatus = captionJob.status
const captionError = captionJob.error
const captionSubmitting = captionJob.submitting
const captionBusy = captionJob.busy
const historyJobId = ref("")
const maintenanceBusy = ref(false)
const maintenanceResult = ref<CaptionRollbackResult | null>(null)

async function maintainHistory(action: "rollback" | "delete") {
  const jobId = captionJob.report.value?.job_id
  if (!jobId || maintenanceBusy.value || captionBusy.value) return
  try {
    await ElMessageBox.confirm(t(action === "rollback" ? "tagger.caption.rollbackConfirm" : "tagger.caption.deleteHistoryConfirm"), { type: "warning" })
  } catch { return }
  maintenanceBusy.value = true
  maintenanceResult.value = null
  try {
    if (action === "rollback") {
      maintenanceResult.value = await taggerApi.captionRollback(jobId)
      await captionJob.loadReport(jobId)
    } else {
      await taggerApi.captionDeleteHistory(jobId)
      captionJob.report.value = null
      historyJobId.value = ""
    }
    await captionJob.loadHistory()
    await captionJob.refresh()
  } catch (caught) {
    ElMessage.error(caught instanceof Error ? caught.message : t("tagger.caption.maintenanceFailed"))
  } finally { maintenanceBusy.value = false }
}
const previewImagePath = ref("")
const previewResult = ref("")
const profileEditorOpen = ref(false)
const localVision = ref<LocalVisionStatus>({ state: "missing", installed: false, downloaded_bytes: 0, total_bytes: 0 })
const localVisionBusy = ref(false)
const previewBusy = ref(false)
const presetId = ref(captionBuiltins[0].id)
const presetName = ref(captionBuiltins[0].name)
const presetSaving = ref(false)
const captionPresets = ref<CaptionPromptPreset[]>([])
const presetRevision = ref("")
const defaultPresetId = ref<string | null>(null)
const legacyImported = ref(false)
const legacyPresetCount = computed(() => legacyImported.value ? 0 : llmProfiles.config.value.prompt_presets.length)
const defaultPrompt = captionForm.prompt
const builtinPresets = captionBuiltins
const captionDetail = computed(() => {
  const builtin = builtinPresets.find(preset => preset.template === captionForm.prompt && preset.system_prompt === selectedSystemPrompt.value && preset.language === captionForm.language)
  return builtin ? (builtin.id.endsWith("-brief") ? "brief" : "detailed") : "custom"
})
const selectedSystemPrompt = ref(builtinPresets[0].system_prompt || "")
captionForm.max_caption_length = 2000
const committedPrompt = ref<PromptState>({ prompt: captionForm.prompt, language: captionForm.language, max_caption_length: captionForm.max_caption_length, system_prompt: selectedSystemPrompt.value, name: presetName.value })
let timer: number | undefined

const downloadPercent = computed(() => status.value.download.percent || (status.value.download.total ? Math.round(status.value.download.current / status.value.download.total * 100) : 0))

watch([() => status.value.phase, () => captionStatus.value.phase], async (next, previous) => {
  const active = ["downloading", "tagging", "captioning", "pending", "cancelling"]
  if (!previous.some(phase => active.includes(phase)) || next.some(phase => active.includes(phase))) return
  const generation = refreshGeneration
  try {
    const document = await taggerApi.models()
    if (generation === refreshGeneration) catalog.value = document.models
  } catch { /* Status remains usable when catalog refresh is unavailable. */ }
})

function selectModel(identifier: string) {
  const next = catalog.value.find(model => model.id === identifier)
  if (!next) return
  modelDrafts.set(selectedModelId.value, { tag: { ...form }, caption: { ...captionForm }, presetId: presetId.value, presetName: presetName.value, systemPrompt: selectedSystemPrompt.value, committed: { ...committedPrompt.value } })
  const path = form.path
  const draft = modelDrafts.get(identifier)
  if (draft) {
    if (next.output === "tag") Object.assign(form, draft.tag, { path })
    else {
      Object.assign(captionForm, draft.caption, { path })
      presetId.value = draft.presetId
      presetName.value = draft.presetName
      selectedSystemPrompt.value = draft.systemPrompt
      committedPrompt.value = { ...draft.committed }
    }
  }
  selectedModelId.value = identifier
  method.value = next.output
  if (next.output === "natural" && parameterTab.value === "tags") parameterTab.value = "model"
  runtime.value = next.runtime
  if (next.output === "tag") form.interrogator_model = next.id
  else captionForm.profile_id = next.profile_id || undefined
  previewResult.value = ""
}

function selectRuntime(next: "local" | "api") {
  if (next === "api" && !apiAvailable.value) return
  const selected = catalog.value.find(model => model.runtime === next && model.output === mode.value && model.id === selectedModelId.value)
    || catalog.value.find(model => model.runtime === next && model.output === mode.value && model.ready)
    || catalog.value.find(model => model.runtime === next && model.output === mode.value)
  if (selected) selectModel(selected.id)
}

function selectMethod(next: "tag" | "natural") {
  if (controlsLocked.value || next === mode.value) return
  const candidates = catalog.value.filter(model => model.output === next && (next === "tag" || model.capabilities.includes("vision")))
  // Natural-language default follows the shared remote-first policy.
  const selected = candidates.find(model => model.runtime === "api" && model.ready)
    || candidates.find(model => model.runtime === "local" && model.ready)
    || candidates.find(model => model.runtime === "api") || candidates[0]
  if (selected) selectModel(selected.id)
}

function availabilityLabel(model: TaggerModel) {
  if (status.value.model === model.id && status.value.phase === "downloading") return t("tagger.downloadMeter")
  if (model.output === "tag") return t(model.downloaded ? "tagger.workspace.downloaded" : "tagger.workspace.toDownload")
  return t(model.ready ? "tagger.models.ready" : model.downloaded ? "tagger.models.downloaded" : "tagger.models.notReady")
}

function restoreParameters() {
  if (mode.value === "natural") {
    captionForm.max_tokens = 512
    captionForm.temperature = 0
    captionForm.conflict_action = "ignore"
    captionForm.recursive = false
    // A custom prompt is restored only through the editor's explicit controls.
    return
  }
  Object.assign(form, { threshold: .35, character_threshold: .6, additional_tags: "", exclude_tags: "",
    batch_output_action_on_conflict: "ignore", batch_input_recursive: false, replace_underscore: true,
    escape_tag: true, add_rating_tag: false, add_model_tag: false })
}

async function selectPreset(identifier: string) {
  if (captionForm.prompt !== committedPrompt.value.prompt || captionForm.language !== committedPrompt.value.language || captionForm.max_caption_length !== committedPrompt.value.max_caption_length || selectedSystemPrompt.value !== committedPrompt.value.system_prompt || presetName.value !== committedPrompt.value.name) {
    try {
      await ElMessageBox.confirm(t("tagger.caption.unsavedPrompt"), { confirmButtonText: t("tagger.caption.discardChanges"), cancelButtonText: t("tagger.caption.keepEditing"), type: "warning" })
    } catch { return }
  }
  presetId.value = identifier
  const preset = [...builtinPresets, ...captionPresets.value].find(item => item.id === identifier)
  if (!preset?.template || !preset.language) return
  captionForm.prompt = preset.template
  captionForm.language = preset.language
  captionForm.max_caption_length = preset.max_length || 2000
  presetName.value = preset.name || ""
  selectedSystemPrompt.value = preset.system_prompt || ""
  committedPrompt.value = { prompt: preset.template, language: preset.language, max_caption_length: captionForm.max_caption_length, system_prompt: selectedSystemPrompt.value, name: presetName.value }
}

function restorePrompt() {
  const saved = committedPrompt.value
  Object.assign(captionForm, { prompt: saved.prompt, language: saved.language, max_caption_length: saved.max_caption_length })
  selectedSystemPrompt.value = saved.system_prompt
  presetName.value = saved.name
}

async function refreshPromptPresets() {
  if (presetSaving.value) return
  presetSaving.value = true
  try {
    const saved = await llmApi.promptPresets()
    captionPresets.value = saved.presets
    presetRevision.value = saved.revision
    defaultPresetId.value = saved.settings.default_caption_preset_id || null
    legacyImported.value = saved.settings.legacy_imported === true
  } catch (caught) {
    ElMessage.error(caught instanceof Error ? caught.message : String(caught))
  } finally { presetSaving.value = false }
}

async function importLegacyPresets() {
  if (presetSaving.value) return
  try { await ElMessageBox.confirm(t('tagger.caption.importLegacyConfirm'), { type: "warning" }) }
  catch { return }
  presetSaving.value = true
  try {
    const saved = await llmApi.importLegacyPromptPresets(presetRevision.value)
    captionPresets.value = saved.presets
    presetRevision.value = saved.revision
    defaultPresetId.value = saved.settings.default_caption_preset_id || null
    legacyImported.value = saved.settings.legacy_imported === true
    ElMessage.success(t('tagger.caption.legacyImported'))
  } catch (caught) {
    ElMessage.error(caught instanceof Error ? caught.message : String(caught))
  } finally { presetSaving.value = false }
}

async function savePreset(remove = false, saveAs = false) {
  if (!remove && !validCaptionLimit()) return ElMessage.error(t("tagger.caption.maxLengthRequired"))
  if (!remove && (!presetName.value.trim() || !captionForm.prompt.trim())) return ElMessage.error(t("tagger.caption.presetRequired"))
  presetSaving.value = true
  try {
    const identifier = (!saveAs && captionPresets.value.some(item => item.id === presetId.value) ? presetId.value : "") || `caption-${Date.now()}`
    const presets = captionPresets.value.filter(item => item.id !== identifier)
    if (!remove) presets.push({ id: identifier, kind: "caption_prompt", name: presetName.value.trim(), template: captionForm.prompt, system_prompt: selectedSystemPrompt.value, output_format: "plain_text", language: captionForm.language, max_length: captionForm.max_caption_length || 2000, model_capabilities: ["vision", "caption"], revision: "" })
    const saved = await llmApi.savePromptPresets({ presets, settings: { default_caption_preset_id: remove ? (defaultPresetId.value === identifier ? null : defaultPresetId.value) : identifier }, revision: presetRevision.value })
    captionPresets.value = saved.presets
    presetRevision.value = saved.revision
    defaultPresetId.value = saved.settings.default_caption_preset_id || null
    presetId.value = remove ? "" : identifier
    const savedPreset = saved.presets.find(item => item.id === identifier)
    if (savedPreset) committedPrompt.value = { prompt: savedPreset.template, language: savedPreset.language, max_caption_length: savedPreset.max_length, system_prompt: savedPreset.system_prompt || "", name: savedPreset.name }
    ElMessage.success(t("tagger.caption.presetSaved"))
  } catch (caught) {
    ElMessage.error(caught instanceof Error ? caught.message : String(caught))
  } finally {
    presetSaving.value = false
  }
}

async function loadLlmProfiles() {
  const revision = refreshGeneration
  await llmProfiles.load()
  if (llmProfiles.error.value) { captionError.value = llmProfiles.error.value; return }
  try {
    const promptDocument = await llmApi.promptPresets()
    if (revision === refreshGeneration) {
      captionPresets.value = promptDocument.presets
      presetRevision.value = promptDocument.revision
      defaultPresetId.value = promptDocument.settings.default_caption_preset_id || null
      legacyImported.value = promptDocument.settings.legacy_imported === true
      const defaultId = promptDocument.settings.default_caption_preset_id
      if ((!presetId.value || presetId.value.startsWith("builtin-caption-")) && defaultId && captionForm.prompt === defaultPrompt) await selectPreset(defaultId)
    }
    const local = await llmApi.localVisionStatus()
    if (revision === refreshGeneration) localVision.value = local
    const modelDocument = await taggerApi.models()
    if (revision === refreshGeneration) {
      catalog.value = modelDocument.models
      const selected = catalog.value.find(model => model.id === selectedModelId.value)
      if (selected?.output === "natural") captionForm.profile_id = selected.profile_id || undefined
      if (!selected) selectRuntime("local")
    }
  } catch (caught) { captionError.value = caught instanceof Error ? caught.message : String(caught) }
}

async function manageLocalVision(action: "setup" | "start" | "stop" | "cancel") {
  localVisionBusy.value = true
  try {
    localVision.value = await llmApi.localVisionAction(action)
    await loadLlmProfiles()
  } catch (caught) {
    ElMessage.error(caught instanceof Error ? caught.message : String(caught))
  } finally {
    localVisionBusy.value = false
  }
}

function syncCaptionPath() {
  captionForm.prompt_id = captionPresets.value.some(item => item.id === presetId.value) ? presetId.value : undefined
  captionForm.system_prompt = selectedSystemPrompt.value
  captionForm.path = form.path
  captionForm.model_id = selectedModelId.value
  captionForm.runtime = runtime.value
}

function validCaptionLimit() {
  const maximum = captionForm.max_caption_length ?? 2000
  return Number.isInteger(maximum) && maximum >= 1 && maximum <= 2000
}

async function start() {
  if (!form.path.trim()) return ElMessage.error(t("tagger.msg.pathRequired"))
  try {
    await captionJob.start(tagJobRequest(form))
    ElMessage.success(t("tagger.msg.submitted"))
  } catch (caught) {
    ElMessage.error(caught instanceof Error ? caught.message : t("tagger.msg.submitFail"))
  }
}

async function startCaption() {
  syncCaptionPath()
  if (!validCaptionLimit()) return ElMessage.error(t("tagger.caption.maxLengthRequired"))
  if (!captionForm.path.trim()) return ElMessage.error(t("tagger.msg.pathRequired"))
  if (!captionForm.profile_id) return ElMessage.error(t("tagger.caption.profileRequired"))
  if (!captionForm.prompt.trim()) return ElMessage.error(t("tagger.caption.promptRequired"))
  captionError.value = ""
  try {
    await captionJob.start({ ...captionForm, path: captionForm.path.replaceAll("\\", "/") })
    ElMessage.success(t("tagger.caption.submitted"))
  } catch (caught) {
    captionError.value = caught instanceof Error ? caught.message : String(caught)
    ElMessage.error(captionError.value)
  } finally {
    captionSubmitting.value = false
  }
}

async function previewCaption() {
  if (previewBusy.value) return
  syncCaptionPath()
  if (mode.value !== "tag" && !validCaptionLimit()) return ElMessage.error(t("tagger.caption.maxLengthRequired"))
  if (!previewImagePath.value.trim()) return ElMessage.error(t("tagger.caption.previewPathRequired"))
  if (mode.value !== "tag" && !captionForm.profile_id) return ElMessage.error(t("tagger.caption.profileRequired"))
  previewBusy.value = true
  try {
    const result = await taggerApi.captionPreview({ ...(mode.value === "tag" ? tagJobRequest(form) : captionForm), image_path: previewImagePath.value })
    previewResult.value = result.caption
  } catch (caught) {
    captionError.value = caught instanceof Error ? caught.message : String(caught)
    ElMessage.error(captionError.value)
  } finally {
    previewBusy.value = false
  }
}

async function captionAction(kind: "cancel" | "retry") {
  try {
    if (kind === "cancel") await captionJob.cancel()
    else await captionJob.retry()
    await captionJob.loadHistory()
  } catch (caught) {
    captionError.value = caught instanceof Error ? caught.message : String(caught)
    ElMessage.error(captionError.value)
  }
}

async function invoke(kind: "prefetch" | "cancel" | "reset") {
  try {
    if (kind === "prefetch") await store.prefetch(form.interrogator_model)
    else await store[kind]()
    ElMessage.success(kind === "cancel" ? t("tagger.msg.cancelRequested") : kind === "reset" ? t("tagger.msg.resetDone") : t("tagger.msg.prefetchStarted"))
  } catch (caught) {
    ElMessage.error(caught instanceof Error ? caught.message : t("tagger.msg.actionFail"))
  }
}

const picking = ref(false)
const { open: pathPickerOpen, mode: pathPickerMode, initialPath: pathPickerInitial, nameFilter: pathPickerFilter, pick: pickServerPath, onConfirm: onPathConfirm, onCancel: onPathCancel } = useServerPathPick()
async function browsePreview() {
  picking.value = true
  try {
    const path = await pickServerPath({ mode: "file", initialPath: previewImagePath.value || form.path })
    if (path) previewImagePath.value = path
  } catch (caught) {
    ElMessage.error(caught instanceof Error ? caught.message : t("schemaForm.pickFail"))
  } finally {
    picking.value = false
  }
}

function stopPolling() {
  window.clearInterval(timer)
  timer = undefined
  captionJob.deactivate()
  llmProfiles.invalidate()
}

let refreshing = false
let refreshGeneration = 0
async function refresh() {
  if (refreshing) return
  refreshing = true
  const revision = refreshGeneration
  try {
    await store.refresh()
    await captionJob.refresh()
    if (mode.value !== "tag") {
      const local = await llmApi.localVisionStatus()
      if (revision === refreshGeneration) localVision.value = local
    }
  } catch (caught) {
    if (revision === refreshGeneration) captionError.value = caught instanceof Error ? caught.message : t("tagger.msg.statusFail")
  } finally { refreshing = false }
}

onActivated(() => {
  const queryPath = route?.query.path
  if (typeof queryPath === "string" && queryPath.trim()) {
    form.path = queryPath
    captionForm.path = queryPath
  }
  stopPolling()
  refreshGeneration += 1
  captionJob.activate()
  void refresh()
  const requestedJob = route?.query.job_id
  const generation = refreshGeneration
  void initialiseCatalog().then(async () => {
    if (generation !== refreshGeneration || typeof requestedJob !== "string" || !requestedJob) return
    await captionJob.loadReport(requestedJob)
    if (generation !== refreshGeneration || !captionJob.report.value) return
    const snapshot = captionJob.report.value.snapshot
    const output = snapshot.mode === "tag" ? "tag" : "natural"
    const model = catalog.value.find(item => item.id === snapshot.model_id && item.output === output)
      || catalog.value.find(item => item.output === output)
    if (model) selectModel(model.id)
    historyJobId.value = requestedJob
    await captionJob.loadHistory()
  })
  void captionJob.loadHistory()
  timer = window.setInterval(refresh, 1200)
})
let catalogOperation: Promise<void> | undefined
let catalogGeneration = -1
function initialiseCatalog() {
  if (catalogOperation && catalogGeneration === refreshGeneration) return catalogOperation
  catalogGeneration = refreshGeneration
  catalogLoading.value = true
  const operation = loadLlmProfiles().finally(() => { if (catalogOperation === operation) { catalogOperation = undefined; catalogLoading.value = false } })
  catalogOperation = operation
  return catalogOperation
}
onMounted(() => { queueMicrotask(() => {
  // KeepAlive activation starts polling; standalone mounts still load state.
  if (timer === undefined) {
    captionJob.activate()
    void refresh()
    void captionJob.loadHistory()
  }
  void initialiseCatalog()
}) })
onDeactivated(() => { refreshGeneration += 1; stopPolling() })
onBeforeUnmount(() => { refreshGeneration += 1; stopPolling() })
</script>

<template>
  <div class="tagger-page" :class="{ 'parameters-open': parametersOpen }">
    <section class="tagger-form">
      <header>
        <h1>{{ t("datasetManage.openTagger") }}</h1>
        <div class="tagger-header-actions">
          <button class="secondary-action" data-testid="reset-status" :disabled="submitting || busy || captionBusy" @click="invoke('reset')">{{ t("tagger.reset") }}</button>
          <button class="tagger-settings-button tagger-settings-label" data-testid="parameter-toggle" :aria-label="t('tagger.workspace.parameters')" :title="t('tagger.workspace.parameters')" :aria-expanded="parametersOpen" aria-controls="tagger-parameters" @click="parametersOpen = !parametersOpen"><Setting />{{ t("tagger.workspace.settings") }}</button>
        </div>
      </header>
      <div class="tagger-grid">
        <label class="tagger-dataset-path">{{ t("tagger.pathLabel") }}<span class="path-row"><input v-model="form.path" :disabled="busy || captionBusy || previewBusy" placeholder="/data/datasets/images" /><ManagedDatasetPicker :disabled="busy || captionBusy || previewBusy" :initial-path="form.path" :loaded="Boolean(form.path)" @select="form.path = $event" /></span></label>
      </div>
      <div class="tagger-choice-row">
        <span>{{ t("tagger.workspace.method") }}</span>
        <div class="tagger-segments"><button :class="{ selected: mode === 'tag' }" :aria-pressed="mode === 'tag'" :disabled="controlsLocked" @click="selectMethod('tag')">Tag</button><button :class="{ selected: mode === 'natural' }" :aria-pressed="mode === 'natural'" :disabled="controlsLocked || !catalog.some(model => model.output === 'natural' && model.capabilities.includes('vision'))" @click="selectMethod('natural')">{{ t("tagger.workspace.caption") }}</button></div>
      </div>
      <div class="tagger-choice-row">
        <span>{{ t("tagger.workspace.source") }}</span>
        <div class="tagger-segments"><button :class="{ selected: runtime === 'local' }" :aria-pressed="runtime === 'local'" :disabled="controlsLocked || !catalog.some(model => model.runtime === 'local' && model.output === mode)" @click="selectRuntime('local')">{{ t("tagger.workspace.local") }}</button><button :class="{ selected: runtime === 'api' }" :aria-pressed="runtime === 'api'" :disabled="controlsLocked || !apiAvailable" @click="selectRuntime('api')">API</button></div>
      </div>
      <div class="tagger-model-row">
        <label class="tagger-model-field"><span>{{ t("tagger.modelLabel") }}</span>
          <ElSelect :model-value="selectedModelId" filterable :disabled="controlsLocked" :aria-label="t('tagger.modelLabel')" data-testid="model-select" @update:model-value="selectModel">
            <ElOptionGroup v-for="group in modelGroups" :key="group.name" :label="group.name"><ElOption v-for="model in group.models" :key="model.id" :label="model.model" :value="model.id"><span>{{ model.model }}</span><small class="tagger-option-state">{{ availabilityLabel(model) }}</small></ElOption></ElOptionGroup>
          </ElSelect>
        </label>
        <span v-if="selectedModel" class="tagger-model-state" :class="{ ready: mode === 'tag' ? selectedModel.downloaded : selectedModel.ready }">{{ availabilityLabel(selectedModel) }}</span>
        <span v-if="catalogLoading" role="status">{{ t("tagger.models.loading") }}</span>
        <button v-if="captionError" class="secondary-action" :disabled="catalogLoading" @click="initialiseCatalog">{{ t("datasetManage.retry") }}</button>
        <span v-if="status.phase === 'downloading'">{{ t("tagger.downloadMeter") }} {{ downloadPercent }}% · {{ status.download.filename }}</span>
        <button type="button" class="inline-config-button" @click="profileEditorOpen = true">{{ t("tagger.caption.manageProfiles") }}</button>
      </div>
      <p v-if="mode === 'natural'" class="caption-route-hint">{{ t("tagger.caption.remoteFirst") }}</p>
      <p v-if="mode === 'natural' && !presetLanguageSupported" class="caption-preset-incompatible" role="alert">{{ t("tagger.caption.unsupportedLanguage") }}</p>
      <ManagedVisionModel v-if="selectedModel?.profile_id === 'qwen3-vl-2b-local'" :status="localVision" :busy="localVisionBusy" :locked="captionBusy || previewBusy" @action="manageLocalVision" />
      <div class="tagger-choice-row">
        <label for="tagger-conflict">{{ t("tagger.conflictLabel") }}</label>
        <select v-if="mode === 'tag'" id="tagger-conflict" v-model="form.batch_output_action_on_conflict" :disabled="controlsLocked" class="tagger-conflict-select"><option value="ignore">{{ t("tagger.conflict.ignore") }}</option><option value="copy">{{ t("tagger.conflict.copy") }}</option><option value="prepend">{{ t("tagger.conflict.prepend") }}</option><option value="append">{{ t("tagger.conflict.append") }}</option></select>
        <select v-else id="tagger-conflict" v-model="captionForm.conflict_action" :disabled="controlsLocked" class="tagger-conflict-select"><option value="ignore">{{ t("tagger.conflict.ignore") }}</option><option value="copy">{{ t("tagger.conflict.copy") }}</option></select>
      </div>
      <div v-if="mode === 'natural'" class="check-row"><label><input v-model="captionForm.allow_local_fallback" type="checkbox" :disabled="captionBusy || previewBusy" />{{ t("tagger.caption.enableLocalFallback") }}</label></div>
      <div class="tagger-grid caption-preview-controls">
        <label class="tagger-dataset-path">{{ t("tagger.caption.previewPath") }}<span class="path-row"><input v-model="previewImagePath" :disabled="previewBusy || captionBusy" placeholder="/data/datasets/images/example.png" /><button type="button" :disabled="picking || previewBusy || captionBusy" @click="browsePreview">{{ t("schemaForm.browse") }}</button></span></label>
        <div v-if="previewResult" class="caption-preview wide-field"><strong>{{ t("tagger.caption.previewResult") }}</strong><p>{{ previewResult }}</p></div>
      </div>
      <section class="tagger-run">
        <p>{{ t("tagger.conflictLabel") }}: {{ t(`tagger.conflict.${mode === 'tag' ? form.batch_output_action_on_conflict : captionForm.conflict_action}`) }}</p>
        <button v-if="busy && !captionBusy" class="danger-action tagger-start" :disabled="submitting" @click="invoke('cancel')">{{ t("tagger.cancel") }}</button>
        <button v-else-if="captionBusy" class="danger-action tagger-start" :disabled="captionSubmitting" @click="captionAction('cancel')">{{ t("tagger.cancel") }}</button>
        <button v-else class="primary-action tagger-start" :disabled="captionSubmitting || submitting || previewBusy || catalogLoading || !modelReady" @click="mode === 'tag' ? start() : startCaption()">{{ t("tagger.start") }}</button>
        <div class="tagger-actions"><button v-if="captionStatus.failed" class="secondary-action" data-testid="retry-failed" :disabled="captionBusy || captionSubmitting || busy" @click="captionAction('retry')">{{ t("tagger.caption.retryFailed") }}</button><button class="secondary-action" :disabled="captionSubmitting || previewBusy || captionBusy || busy || catalogLoading || !modelReady || !previewImagePath" @click="previewCaption">{{ t("tagger.caption.preview") }}</button><button v-if="mode === 'tag'" class="secondary-action" :disabled="submitting || captionBusy || previewBusy || busy" @click="invoke('prefetch')">{{ t("tagger.prefetch") }}</button></div>
        <div class="tagger-run-status" aria-live="polite">
          <template v-if="busy && !captionBusy"><p>{{ status.message || t("tagger.idle") }}</p><p v-if="error" role="alert">{{ error }}</p><div class="meter"><header><span>{{ t("tagger.downloadMeter") }}</span><b>{{ downloadPercent }}%</b></header><div><i :style="{ width: downloadPercent + '%' }" /></div><small>{{ status.download.filename }}</small></div></template>
          <template v-else><p>{{ captionStatus.message || t(mode === 'tag' ? "tagger.idle" : "tagger.caption.idle") }}</p><p v-if="captionError" role="alert">{{ captionError }}</p><CaptionJobProgress :status="captionStatus" /><p v-if="captionStatus.failed">{{ t("tagger.caption.failed", { n: captionStatus.failed }) }}</p></template>
        </div>
        <section class="caption-history">
          <h3>{{ t("tagger.caption.history") }}</h3>
          <button type="button" :disabled="maintenanceBusy || captionJob.historyBusy.value" @click="captionJob.loadHistory">{{ t("tagger.caption.refreshHistory") }}</button>
          <label>{{ t("tagger.caption.selectReport") }}<select v-model="historyJobId" :disabled="maintenanceBusy" @change="captionJob.loadReport(historyJobId)"><option value="">{{ t("tagger.caption.selectReport") }}</option><option v-for="job in captionJob.jobs.value" :key="job.job_id || ''" :value="job.job_id || ''">{{ job.mode }} · {{ job.phase }} · {{ job.succeeded }}/{{ job.total }} · {{ job.job_id?.slice(0, 8) }}</option></select></label>
          <button v-if="captionStatus.job_id" type="button" :disabled="maintenanceBusy || captionJob.reportBusy.value" @click="captionJob.loadReport(captionStatus.job_id!)">{{ t("tagger.caption.currentReport") }}</button>
          <p v-if="captionJob.reportBusy.value" role="status">{{ t("tagger.caption.loadingReport") }}</p>
          <div v-if="captionJob.report.value" class="caption-report" aria-live="polite">
            <strong>{{ captionJob.report.value.job_id }}</strong>
            <p>{{ t("tagger.caption.reportPrivacy") }}</p>
            <div class="caption-maintenance">
              <button type="button" :disabled="maintenanceBusy || captionBusy || captionJob.reportBusy.value" @click="maintainHistory('rollback')">{{ t("tagger.caption.rollback") }}</button>
              <button type="button" :disabled="maintenanceBusy || captionBusy || captionJob.reportBusy.value" @click="maintainHistory('delete')">{{ t("tagger.caption.deleteHistory") }}</button>
            </div>
            <p v-if="maintenanceResult?.job_id === captionJob.report.value.job_id" role="status">{{ t("tagger.caption.rollbackResult", { restored: maintenanceResult.restored, conflicts: maintenanceResult.conflicts, skipped: maintenanceResult.skipped }) }}</p>
            <ul v-if="maintenanceResult?.job_id === captionJob.report.value.job_id"><li v-for="item in maintenanceResult.items" :key="item.filename">{{ item.filename }} · {{ item.status }}<template v-if="item.code"> · {{ item.code }}</template></li></ul>
            <dl v-for="(item, index) in captionJob.report.value.report.items" :key="index"><dt>{{ item.filename }} · {{ item.status }}</dt><dd v-if="item.code || item.error">{{ [item.code, item.error].filter(Boolean).join(' · ') }}</dd><dd v-if="item.profile_id">{{ t("tagger.caption.reportProfile") }}: {{ item.profile_id }} · {{ item.profile_revision }}</dd><dd v-if="item.prompt_revision">{{ t("tagger.caption.reportPrompt") }}: {{ item.prompt_revision }}</dd><dd v-if="item.before_hash || item.after_hash">{{ t("tagger.caption.reportHashes") }}: {{ item.before_hash || '∅' }} → {{ item.after_hash || '∅' }}</dd><dd v-if="item.cached">{{ t("tagger.caption.reportCached") }}</dd></dl>
          </div>
        </section>
      </section>
    </section>
    <button v-if="parametersOpen" class="tagger-panel-backdrop" :aria-label="t('tagger.workspace.close')" @click="parametersOpen = false" />
    <aside v-show="parametersOpen" id="tagger-parameters" class="tagger-parameters" :aria-label="t('tagger.workspace.parameters')" @keydown.esc="parametersOpen = false">
      <header><h2>{{ t("tagger.workspace.parameters") }}</h2><button class="tagger-settings-button" data-testid="parameter-close" :aria-label="t('tagger.workspace.close')" @click="parametersOpen = false"><Close /></button></header>
      <div class="tagger-panel-model"><span>{{ selectedModel?.model || selectedModelId }}</span><button class="tagger-restore" :disabled="controlsLocked" @click="restoreParameters"><RefreshLeft />{{ t("tagger.workspace.restore") }}</button></div>
      <div class="tagger-panel-tabs" role="tablist"><button v-for="tab in (mode === 'tag' ? ['model', 'tags', 'advanced'] : ['model', 'advanced'])" :key="tab" :data-testid="`tab-${tab}`" role="tab" :aria-selected="parameterTab === tab" @click="parameterTab = tab">{{ t(`tagger.workspace.tab_${tab}`) }}</button></div>
      <fieldset :disabled="busy || captionBusy || previewBusy">
        <div v-show="parameterTab === 'model'">
          <h2>{{ t("tagger.workspace.parameters") }}</h2>
          <div v-if="mode === 'tag'" class="tagger-grid"><label>{{ t("tagger.thresholdLabel") }}<input v-model.number="form.threshold" type="number" min="0" max="1" step="0.05" /></label><label>{{ t("tagger.characterThresholdLabel") }}<input v-model.number="form.character_threshold" type="number" min="0" max="1" step="0.05" /></label></div>
          <div v-else class="tagger-grid"><label>{{ t("tagger.models.maxTokens") }}<input v-model.number="captionForm.max_tokens" type="number" min="1" max="8192" /></label><label>{{ t("tagger.models.temperature") }}<input v-model.number="captionForm.temperature" type="number" min="0" max="2" step="0.1" /></label></div>
          <div class="check-row"><label v-if="mode === 'tag'"><input v-model="form.batch_input_recursive" type="checkbox" />{{ t("tagger.recursive") }}</label><label v-else><input v-model="captionForm.recursive" type="checkbox" />{{ t("tagger.recursive") }}</label></div>
          <dl v-if="selectedModel" class="tagger-model-info"><dt>{{ t("tagger.modelLabel") }}</dt><dd>{{ selectedModel.model }}</dd><dt>{{ t("tagger.workspace.source") }}</dt><dd>{{ t(runtime === 'api' ? "tagger.models.api" : "tagger.workspace.local") }}</dd><dt>{{ t("tagger.models.output") }}</dt><dd>{{ t(mode === 'tag' ? "tagger.modeTag" : "tagger.modeNatural") }}</dd></dl>
        </div>
        <div v-if="mode === 'tag'" v-show="parameterTab === 'tags'">
          <div class="tagger-grid"><label>{{ t("tagger.additionalTagsLabel") }}<input v-model="form.additional_tags" /></label><label>{{ t("tagger.excludeTagsLabel") }}<input v-model="form.exclude_tags" /></label></div>
          <div class="check-row"><label><input v-model="form.replace_underscore" type="checkbox" />{{ t("tagger.replaceUnderscore") }}</label><label><input v-model="form.escape_tag" type="checkbox" />{{ t("tagger.escapeTag") }}</label><label><input v-model="form.add_rating_tag" type="checkbox" />{{ t("tagger.addRatingTag") }}</label><label><input v-model="form.add_model_tag" type="checkbox" />{{ t("tagger.addModelTag") }}</label></div>
        </div>
        <div v-show="parameterTab === 'advanced'">
          <div v-if="mode === 'tag'" class="tagger-grid"><label>{{ t("tagger.replaceUnderscore") }}<input v-model="form.replace_underscore_excludes" /></label></div>
          <template v-if="mode === 'natural'">
            <p v-if="captionForm.language === 'en' && /[\u3400-\u9fff]/.test(captionForm.prompt + selectedSystemPrompt)" role="status">{{ t("tagger.caption.englishPromptHint") }}</p>
            <div class="tagger-grid"><CaptionPromptEditor v-model:preset-id="presetId" v-model:name="presetName" v-model:prompt="captionForm.prompt" v-model:system-prompt="selectedSystemPrompt" v-model:maximum="captionForm.max_caption_length" :language="captionForm.language" :presets="captionPresets" :builtins="builtinPresets" :saving="presetSaving" :legacy-count="legacyPresetCount" @select="selectPreset" @save="savePreset()" @save-as="savePreset(false, true)" @restore-default="selectPreset(builtinCaptionPreset(captionForm.language, captionDetail === 'brief' ? 'brief' : 'detailed').id)" @restore="restorePrompt" @remove="savePreset(true)" @import-legacy="importLegacyPresets" @refresh="refreshPromptPresets" /></div>
            <p class="caption-privacy">{{ t("tagger.caption.privacy") }}</p>
          </template>
        </div>
      </fieldset>
    </aside>
    <LlmSettingsDialog v-model="profileEditorOpen" capability="vision" :image-path="previewImagePath" @saved="loadLlmProfiles" />
    <PathPickerDialog v-model="pathPickerOpen" :mode="pathPickerMode" :initial-path="pathPickerInitial" :name-filter="pathPickerFilter" @confirm="onPathConfirm" @cancel="onPathCancel" />
  </div>
</template>
