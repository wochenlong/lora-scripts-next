<script setup lang="ts">
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, reactive, ref, watch } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { storeToRefs } from "pinia"
import { useI18n } from "vue-i18n"
import { useRoute } from "vue-router"
import { useTaggerStore } from "../stores/tagger"
import { llmApi, type CaptionPromptPreset, type LocalVisionStatus } from "../api/llm"
import { taggerApi, type CaptionJobRequest, type TaggerModel, type TaggerRequest, type CaptionRollbackResult } from "../api/tagger"
import PathPickerDialog from "../components/PathPickerDialog.vue"
import LlmSettingsDialog from "../components/LlmSettingsDialog.vue"
import CaptionJobProgress from "../components/CaptionJobProgress.vue"
import CaptionPromptEditor from "../components/CaptionPromptEditor.vue"
import ManagedVisionModel from "../components/ManagedVisionModel.vue"
import TaggerModelSelector from "../components/TaggerModelSelector.vue"
import { useLlmProfiles } from "../composables/useLlmProfiles"
import { useTaggerJob } from "../composables/useTaggerJob"
import { useServerPathPick } from "../composables/useServerPathPick"

const models = ["wd14-convnextv2-v2", "wd-convnext-v3", "wd-swinv2-v3", "wd-vit-v3", "wd14-swinv2-v2", "wd14-vit-v2", "wd14-moat-v2", "wd-eva02-large-tagger-v3", "wd-vit-large-tagger-v3", "cl_tagger_1_01"]
const form = reactive<TaggerRequest>({ path: "", interrogator_model: models[0], threshold: .35, character_threshold: .6, add_rating_tag: false, add_model_tag: false, additional_tags: "", exclude_tags: "", escape_tag: true, batch_input_recursive: false, batch_output_action_on_conflict: "copy", replace_underscore: true, download_endpoint: "", replace_underscore_excludes: "0_0, (o)_(o), +_+, +_-, ._., <o>_<o>, <|>_<|>, =_=, >_<, 3_3, 6_9, >_o, @_@, ^_^, o_o, u_u, x_x, |_|, ||_||" })
const captionForm = reactive<CaptionJobRequest>({ path: "", mode: "natural", recursive: false, profile_id: undefined, prompt: '请用{{language}}（zh-CN 使用简体中文）描述图片中的主要可见内容，只返回 JSON 对象，字段必须为 caption 和 language；language 必须是 "{{language}}"，不要输出 Markdown。', language: "zh-CN", conflict_action: "ignore", max_tokens: 512, temperature: 0, allow_local_fallback: false })
form.batch_output_action_on_conflict = "ignore"
const runtime = ref<"local" | "api">("local")
const catalog = ref<TaggerModel[]>([])
const selectedModelId = ref(models[0])
const selectedModel = computed(() => catalog.value.find(model => model.id === selectedModelId.value))
const mode = computed(() => selectedModel.value?.output || "tag")
const availableModels = computed(() => catalog.value.filter(model => model.runtime === runtime.value))
const apiAvailable = computed(() => catalog.value.some(model => model.runtime === "api" && model.ready))
const modelReady = computed(() => selectedModel.value?.ready && (mode.value === "tag" || selectedModel.value.languages.includes(captionForm.language) || selectedModel.value.languages.includes("*")))
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
const presetId = ref("")
const presetName = ref("")
const presetSaving = ref(false)
const captionPresets = ref<CaptionPromptPreset[]>([])
const presetRevision = ref("")
const defaultPresetId = ref<string | null>(null)
const legacyImported = ref(false)
const legacyPresetCount = computed(() => legacyImported.value ? 0 : llmProfiles.config.value.prompt_presets.length)
const defaultPrompt = captionForm.prompt
const builtinPresets: CaptionPromptPreset[] = [{ id: "builtin-caption-zh", kind: "caption_prompt", name: "客观描述 / Visible facts", template: defaultPrompt, system_prompt: "只描述可见主体、动作、环境和构图，不臆测身份或不可见事实。", output_format: "plain_text", language: "zh-CN", max_length: 2000, model_capabilities: ["vision", "caption"], revision: "builtin-v1" }]
const selectedSystemPrompt = ref(builtinPresets[0].system_prompt || "")
captionForm.max_caption_length = 2000
const committedPrompt = ref<PromptState>({ prompt: captionForm.prompt, language: captionForm.language, max_caption_length: captionForm.max_caption_length, system_prompt: selectedSystemPrompt.value, name: "" })
let timer: number | undefined

const downloadPercent = computed(() => status.value.download.percent || (status.value.download.total ? Math.round(status.value.download.current / status.value.download.total * 100) : 0))
const taggingPercent = computed(() => status.value.tagging.total ? Math.round(status.value.tagging.current / status.value.tagging.total * 100) : 0)

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
  runtime.value = next.runtime
  if (next.output === "tag") form.interrogator_model = next.id
  else captionForm.profile_id = next.profile_id || undefined
  previewResult.value = ""
}

function selectRuntime(next: "local" | "api") {
  if (next === "api" && !apiAvailable.value) return
  const selected = catalog.value.find(model => model.runtime === next && model.id === selectedModelId.value)
    || catalog.value.find(model => model.runtime === next && model.ready)
    || catalog.value.find(model => model.runtime === next)
  if (selected) selectModel(selected.id)
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
      if (!presetId.value && defaultId && captionForm.prompt === defaultPrompt) await selectPreset(defaultId)
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
    await store.start({ ...form, path: form.path.replaceAll("\\", "/") })
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
  if (!validCaptionLimit()) return ElMessage.error(t("tagger.caption.maxLengthRequired"))
  if (!previewImagePath.value.trim()) return ElMessage.error(t("tagger.caption.previewPathRequired"))
  if (!captionForm.profile_id) return ElMessage.error(t("tagger.caption.profileRequired"))
  previewBusy.value = true
  try {
    const result = await taggerApi.captionPreview({ ...captionForm, image_path: previewImagePath.value })
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
    if (kind === "prefetch") await store.prefetch(form.interrogator_model, form.download_endpoint)
    else await store[kind]()
    ElMessage.success(kind === "cancel" ? t("tagger.msg.cancelRequested") : kind === "reset" ? t("tagger.msg.resetDone") : t("tagger.msg.prefetchStarted"))
  } catch (caught) {
    ElMessage.error(caught instanceof Error ? caught.message : t("tagger.msg.actionFail"))
  }
}

watch(mode, value => {
  if (value !== "tag") {
    captionJob.activate()
    void captionJob.refresh()
    void captionJob.loadHistory()
  } else captionJob.deactivate()
})

const picking = ref(false)
const { open: pathPickerOpen, mode: pathPickerMode, initialPath: pathPickerInitial, nameFilter: pathPickerFilter, pick: pickServerPath, onConfirm: onPathConfirm, onCancel: onPathCancel } = useServerPathPick()
async function browsePath() {
  picking.value = true
  try {
    const path = await pickServerPath({ mode: "folder", initialPath: form.path })
    if (path) form.path = path
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
    if (mode.value !== "tag") {
      await captionJob.refresh()
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
    const model = catalog.value.find(item => item.id === snapshot.model_id && item.output === "natural")
      || catalog.value.find(item => item.output === "natural")
    if (model) selectModel(model.id)
    historyJobId.value = requestedJob
    await captionJob.loadHistory()
  })
  if (mode.value !== "tag") void captionJob.loadHistory()
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
onMounted(() => { queueMicrotask(() => { void initialiseCatalog() }) })
onDeactivated(() => { refreshGeneration += 1; stopPolling() })
onBeforeUnmount(() => { refreshGeneration += 1; stopPolling() })
</script>

<template>
  <div class="tagger-page">
    <section class="tagger-form">
      <header>
        <span class="eyebrow">DATASET TAGGER</span>
        <h1>{{ t("tagger.title") }}</h1>
        <p>{{ t("tagger.subtitle") }}</p>
      </header>
      <div class="tagger-grid">
        <label class="wide-field">{{ t("tagger.pathLabel") }}<span class="path-row"><input v-model="form.path" placeholder="/data/datasets/images" /><button :disabled="picking" @click.prevent="browsePath">{{ t("schemaForm.browse") }}</button></span></label>
        <div class="tagger-mode-tabs wide-field" role="group" :aria-label="t('tagger.models.runtime')">
          <button type="button" :class="{ active: runtime === 'local' }" :disabled="catalogLoading || busy || captionBusy || presetSaving" @click="selectRuntime('local')">{{ t('tagger.models.local') }}</button>
          <button v-if="apiAvailable" type="button" :class="{ active: runtime === 'api' }" :disabled="catalogLoading || busy || captionBusy || presetSaving" @click="selectRuntime('api')">{{ t('tagger.models.api') }}</button>
          <button type="button" class="inline-config-button" @click="profileEditorOpen = true">{{ t('tagger.caption.manageProfiles') }}</button>
        </div>
        <p v-if="catalogLoading" class="wide-field" role="status">{{ t('tagger.models.loading') }}</p>
        <p v-if="mode === 'tag' && captionError" class="wide-field" role="alert">{{ captionError }}</p>
        <TaggerModelSelector :models="availableModels" :selected="selectedModelId" :disabled="catalogLoading || busy || captionBusy || previewBusy || presetSaving" @select="selectModel" />
        <p v-if="selectedModel" class="wide-field">{{ t('tagger.models.output') }}: {{ mode === 'tag' ? t('tagger.modeTag') : t('tagger.modeNatural') }} · {{ selectedModel.ready ? t('tagger.models.ready') : t('tagger.models.notReady') }}</p>
        <template v-if="mode !== 'natural'">
          <label>{{ t("tagger.thresholdLabel") }}<input v-model.number="form.threshold" type="number" min="0" max="1" step="0.05" /></label>
          <label>{{ t("tagger.characterThresholdLabel") }}<input v-model.number="form.character_threshold" type="number" min="0" max="1" step="0.05" /></label>
          <label>{{ t("tagger.additionalTagsLabel") }}<input v-model="form.additional_tags" /></label>
          <label>{{ t("tagger.excludeTagsLabel") }}<input v-model="form.exclude_tags" /></label>
          <details class="tagger-advanced wide-field"><summary>{{ t('tagger.models.advanced') }}</summary><label>{{ t("tagger.endpointLabel") }}<input v-model="form.download_endpoint" :placeholder="t('tagger.endpointPlaceholder')" /></label></details>
          <label v-if="mode === 'tag'">{{ t("tagger.conflictLabel") }}<select v-model="form.batch_output_action_on_conflict"><option value="ignore">{{ t("tagger.conflict.ignore") }}</option><option value="copy">{{ t("tagger.conflict.copy") }}</option><option value="prepend">{{ t("tagger.conflict.prepend") }}</option><option value="append">{{ t("tagger.conflict.append") }}</option></select></label>
        </template>
        <template v-if="mode !== 'tag'">
          <label>{{ t("tagger.caption.language") }}<select v-model="captionForm.language" :disabled="presetSaving"><option value="zh-CN">简体中文</option><option value="zh-TW">繁體中文</option><option value="en">English</option><option value="ja">日本語</option></select></label>
          <label>{{ t('tagger.models.maxTokens') }}<input v-model.number="captionForm.max_tokens" type="number" min="1" max="8192" /></label>
          <label>{{ t('tagger.models.temperature') }}<input v-model.number="captionForm.temperature" type="number" min="0" max="2" step="0.1" /></label>
          <CaptionPromptEditor v-model:preset-id="presetId" v-model:name="presetName" v-model:prompt="captionForm.prompt" v-model:system-prompt="selectedSystemPrompt" v-model:maximum="captionForm.max_caption_length" :presets="captionPresets" :builtins="builtinPresets" :saving="presetSaving" :legacy-count="legacyPresetCount" @select="selectPreset" @save="savePreset()" @save-as="savePreset(false, true)" @restore-default="selectPreset('builtin-caption-zh')" @restore="restorePrompt" @remove="savePreset(true)" @import-legacy="importLegacyPresets" @refresh="refreshPromptPresets" />
          <label>{{ t("tagger.caption.conflict") }}<select v-model="captionForm.conflict_action"><option value="ignore">{{ t("tagger.conflict.ignore") }}</option><option value="copy">{{ t("tagger.conflict.copy") }}</option></select></label>
          <label class="wide-field">{{ t("tagger.caption.previewPath") }}<input v-model="previewImagePath" placeholder="/data/datasets/images/example.png" /></label>
          <div class="caption-privacy wide-field">{{ t("tagger.caption.privacy") }}</div>
          <ManagedVisionModel v-if="selectedModel?.profile_id === 'qwen3-vl-2b-local'" :status="localVision" :busy="localVisionBusy" :locked="captionBusy || previewBusy" @action="manageLocalVision" />

          <div v-if="previewResult" class="caption-preview wide-field"><strong>{{ t("tagger.caption.previewResult") }}</strong><p>{{ previewResult }}</p></div>
        </template>
      </div>
      <div class="check-row">
        <label v-if="mode === 'tag'"><input v-model="form.batch_input_recursive" type="checkbox" />{{ t("tagger.recursive") }}</label>
        <label v-else><input v-model="captionForm.recursive" type="checkbox" />{{ t("tagger.recursive") }}</label>
        <label v-if="mode !== 'tag'"><input v-model="captionForm.allow_local_fallback" type="checkbox" />{{ t("tagger.caption.enableLocalFallback") }}</label>
        <label v-if="mode !== 'natural'"><input v-model="form.replace_underscore" type="checkbox" />{{ t("tagger.replaceUnderscore") }}</label>
        <label v-if="mode !== 'natural'"><input v-model="form.escape_tag" type="checkbox" />{{ t("tagger.escapeTag") }}</label>
        <label v-if="mode !== 'natural'"><input v-model="form.add_rating_tag" type="checkbox" />{{ t("tagger.addRatingTag") }}</label>
        <label v-if="mode !== 'natural'"><input v-model="form.add_model_tag" type="checkbox" />{{ t("tagger.addModelTag") }}</label>
      </div>
    </section>
    <aside class="tagger-status" :class="{ 'caption-status-panel': mode !== 'tag' }">
      <template v-if="mode === 'tag'">
        <span class="task-status">{{ status.phase }}</span><h2>{{ status.message || t("tagger.idle") }}</h2><p v-if="error">{{ error }}</p>
        <div class="meter"><header><span>{{ t("tagger.downloadMeter") }}</span><b>{{ downloadPercent }}%</b></header><div><i :style="{ width: downloadPercent + '%' }" /></div><small>{{ status.download.filename || t("tagger.downloadIdle") }}</small></div>
        <div class="meter"><header><span>{{ t("tagger.taggingMeter") }}</span><b>{{ taggingPercent }}%</b></header><div><i :style="{ width: taggingPercent + '%' }" /></div><small>{{ status.tagging.current }} / {{ status.tagging.total }} {{ status.tagging.filename }}</small></div>
        <div class="tagger-actions"><button v-if="busy" class="danger-action" :disabled="submitting" @click="invoke('cancel')">{{ t("tagger.cancel") }}</button><button v-else class="primary-action" :disabled="submitting || catalogLoading || !modelReady" @click="start">{{ t("tagger.start") }}</button><button class="secondary-action" :disabled="submitting || status.phase === 'tagging'" @click="invoke('prefetch')">{{ t("tagger.prefetch") }}</button><button class="secondary-action" :disabled="submitting" @click="invoke('reset')">{{ t("tagger.reset") }}</button></div>
      </template>
      <template v-else>
        <span class="task-status">{{ t('tagger.caption.phases.' + captionStatus.phase) }}</span>
        <h2>{{ captionStatus.message || t("tagger.caption.idle") }}</h2>
        <p v-if="captionError">{{ captionError }}</p>
        <p class="caption-route-hint">{{ t("tagger.caption.remoteFirst") }}</p>
        <CaptionJobProgress :status="captionStatus" />
        <div v-if="captionStatus.failed" class="caption-failures">{{ t("tagger.caption.failed", { n: captionStatus.failed }) }}</div>
        <div class="tagger-actions"><button v-if="captionBusy" class="danger-action" :disabled="captionSubmitting" @click="captionAction('cancel')">{{ t("tagger.cancel") }}</button><button v-else class="primary-action" :disabled="captionSubmitting || previewBusy || catalogLoading || !modelReady" @click="startCaption">{{ t("tagger.start") }}</button><button v-if="captionStatus.failed" class="secondary-action" :disabled="captionBusy" @click="captionAction('retry')">{{ t("tagger.caption.retryFailed") }}</button><button class="secondary-action" :disabled="captionSubmitting || previewBusy || captionBusy || catalogLoading || !modelReady || !previewImagePath" @click="previewCaption">{{ t("tagger.caption.preview") }}</button></div>
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
      </template>
    </aside>
    <LlmSettingsDialog v-model="profileEditorOpen" capability="vision" :image-path="previewImagePath" @saved="loadLlmProfiles" />
    <PathPickerDialog v-model="pathPickerOpen" :mode="pathPickerMode" :initial-path="pathPickerInitial" :name-filter="pathPickerFilter" @confirm="onPathConfirm" @cancel="onPathCancel" />
  </div>
</template>
