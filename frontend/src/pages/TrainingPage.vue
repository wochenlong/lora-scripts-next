<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { ElMessage, ElMessageBox } from "element-plus"
import { useI18n } from "vue-i18n"
import { parse, stringify } from "smol-toml"
import DynamicSchemaForm from "../components/DynamicSchemaForm.vue"
import SectionToc from "../components/SectionToc.vue"
import { schemasApi } from "../api/schemas"
import { trainingApi, type TrainingPreset, type TrainingStart } from "../api/training"
import { cloneFormModel, createDefaultModel, isFieldActive, serializeModel, validateModel, type AdaptedSchema, type FormField, type FormModel } from "../schema/adapter"
import { loadTrainingSchema } from "../schema/loader"
import { buildTrainingConfig, checkTrainingConfig, hydrateImportedConfig } from "../training/params"
import { moduleForTrainType } from "../training/modules"
import { useTasksStore } from "../stores/tasks"

interface HistoryRow { time: string; name?: string; value: FormModel }

const props = withDefaults(defineProps<{ title: string; area: string; schemaName: string; bare?: boolean; fieldDefaults?: FormModel; storageKey?: string; legacyStorageKey?: string }>(), { bare: false, fieldDefaults: undefined, storageKey: undefined, legacyStorageKey: undefined })
const router = useRouter()
const { t } = useI18n()
const schema = ref<AdaptedSchema>()
const model = ref<FormModel>({})
const loading = ref(true)
const error = ref("")
const errors = ref<Record<string, string>>({})
const submitting = ref(false)
const historyOpen = ref(false)
const tasksStore = useTasksStore()
const currentRunning = computed(() => tasksStore.runningTasks.at(-1))
let tasksTimer: number | undefined

function readPreviewCollapsed(): boolean {
  try {
    const parsed = JSON.parse(localStorage.getItem("ui-configs") || "{}")
    return Boolean(parsed && typeof parsed === "object" && parsed.training_preview_collapsed)
  } catch { return false }
}

function persistPreviewCollapsed(collapsed: boolean) {
  try {
    const parsed = JSON.parse(localStorage.getItem("ui-configs") || "{}")
    const configs = parsed && typeof parsed === "object" ? parsed : {}
    localStorage.setItem("ui-configs", JSON.stringify({ ...configs, training_preview_collapsed: collapsed }))
  } catch {}
}
const presetsOpen = ref(false)
const history = ref<HistoryRow[]>([])
const presets = ref<TrainingPreset[]>([])
const presetsLoading = ref(false)
const started = ref<TrainingStart>()
const previewCollapsed = ref(readPreviewCollapsed())
const importInput = ref<HTMLInputElement>()
const rawConfig = computed(() => schema.value ? serializeModel(schema.value, model.value) : {})
const output = computed(() => buildTrainingConfig(rawConfig.value, props.schemaName))
const diagnostics = computed(() => checkTrainingConfig(output.value))
const outputText = computed(() => stringify(output.value))
const filteredPresets = computed(() => presets.value.filter((item) => !item.metadata.train_type || item.metadata.train_type === props.schemaName))
const tocSections = computed(() => {
  if (!schema.value) return []
  const selected = new Map<string, FormField>()
  for (const section of schema.value.sections) {
    for (const field of section.fields) {
      if (isFieldActive(field, model.value)) selected.set(field.key, field)
    }
  }
  return schema.value.sections.filter((section) => section.fields.some((field) => !field.hidden && selected.get(field.key) === field)).map((section) => ({ id: section.id, title: section.title }))
})
const trainLogHref = computed(() => started.value ? `${started.value.train_log_path || "/train-log"}?${started.value.train_log_query || `task_id=${encodeURIComponent(started.value.task_id)}`}` : "")

function storageId() { return props.storageKey || props.schemaName }
function autosaveKey() { return `configs-${storageId()}-autosave` }
function historyKey() { return `configs-${storageId()}` }

// One-time migration: modules split from a shared schema (e.g. SD 1.5/SDXL from
// lora-master) inherit the legacy schema's drafts/history on their heir side.
function migrateLegacyStorage() {
  if (!props.legacyStorageKey || props.legacyStorageKey === storageId()) return
  for (const suffix of ["", "-autosave"]) {
    const legacyKey = `configs-${props.legacyStorageKey}${suffix}`
    const currentKey = `configs-${storageId()}${suffix}`
    const legacyValue = localStorage.getItem(legacyKey)
    if (legacyValue !== null && localStorage.getItem(currentKey) === null) {
      localStorage.setItem(currentKey, legacyValue)
    }
  }
}

function loadHistory() {
  try { history.value = JSON.parse(localStorage.getItem(historyKey()) || "[]") }
  catch { history.value = [] }
}

async function applyImportedConfig(config: FormModel, successMessage?: string) {
  const result = await trainingApi.validateImport(props.schemaName, config)
  if (result.result === "reject") throw new Error(result.errors?.join("\n") || result.message || t("training.importMsg.reject"))
  if (result.result === "redirect" && result.target_path) {
    await ElMessageBox.confirm(result.message || t("training.importMsg.mismatchConfirm"), t("training.importMsg.mismatchTitle"), { confirmButtonText: t("training.importMsg.jump"), cancelButtonText: t("training.importMsg.cancel"), type: "warning" })
    sessionStorage.setItem("mikazuki-pending-import", JSON.stringify(result.config || config))
    // 后端 target_path 基于旧 IA（sd/sdxl 都指向 master 页），优先按 config 的
    // model_train_type 精确落到拆分后的模块，查不到再走后端路径。
    const targetModule = moduleForTrainType((result.config || config).model_train_type)
    if (targetModule) await router.push({ path: "/training", query: { model: targetModule.model, engine: targetModule.engine, target: targetModule.target } })
    else await router.push(result.target_path)
    return
  }
  model.value = { ...createDefaultModel(schema.value!), ...hydrateImportedConfig(result.config || config) }
  if (result.notice) ElMessage.info(result.notice)
  ElMessage.success(successMessage ?? t("training.importMsg.imported"))
}

function readCarryOver(): FormModel {
  try {
    const parsed = JSON.parse(sessionStorage.getItem("mikazuki-carry-over") || "null")
    return parsed && typeof parsed === "object" ? parsed as FormModel : {}
  } catch { return {} }
}

async function load() {
  loading.value = true
  error.value = ""
  try {
    const loaded = await loadTrainingSchema(props.schemaName)
    const defaults = { ...createDefaultModel(loaded), ...props.fieldDefaults }
    const carry = readCarryOver()
    sessionStorage.removeItem("mikazuki-carry-over")
    const carried: FormModel = {}
    for (const [key, value] of Object.entries(carry)) {
      if (key in defaults && !(props.fieldDefaults && key in props.fieldDefaults)) carried[key] = value
    }
    const base = { ...defaults, ...carried }
    try {
      const saved = JSON.parse(localStorage.getItem(autosaveKey()) || "null")
      model.value = saved && typeof saved === "object" ? { ...base, ...saved } : base
    } catch { model.value = base }
    const cards = await schemasApi.graphicCards()
    if (cards.length > 1) {
      const options = cards.map((card, index) => typeof card === "object" ? (card.value ?? card.label ?? index) : card)
      const field: FormField = { key: "gpu_ids", type: "array", role: "select", description: t("training.gpu.fieldDescription"), options, conditions: [] }
      loaded.sections.push({ id: "gpu-settings", title: t("training.gpu.sectionTitle"), fields: [field] })
    }
    schema.value = loaded
    const pending = sessionStorage.getItem("mikazuki-pending-import")
    if (pending) {
      sessionStorage.removeItem("mikazuki-pending-import")
      await applyImportedConfig(JSON.parse(pending), t("training.importMsg.importedRedirect"))
    }
  } catch (reason) { error.value = reason instanceof Error ? reason.message : t("training.schemaLoadFail") }
  finally { loading.value = false }
}

function validate() {
  if (!schema.value) return false
  errors.value = validateModel(schema.value, model.value)
  const messages = [...Object.values(errors.value), ...diagnostics.value.errors]
  if (messages.length) { ElMessage.error(messages[0]); return false }
  if (diagnostics.value.warnings.length) ElMessage.warning(diagnostics.value.warnings[0])
  else ElMessage.success(t("training.validatePassed"))
  return true
}

function saveHistory() {
  const row: HistoryRow = { time: new Date().toLocaleString(), value: cloneFormModel(model.value) }
  if (typeof model.value.output_name === "string") row.name = model.value.output_name
  history.value.push(row)
  localStorage.setItem(historyKey(), JSON.stringify(history.value))
  ElMessage.success(t("training.historyDialog.saved"))
}

function deleteHistory(index: number) {
  history.value.splice(index, 1)
  localStorage.setItem(historyKey(), JSON.stringify(history.value))
}

async function openPresets() {
  presetsOpen.value = true
  if (presets.value.length) return
  presetsLoading.value = true
  try { presets.value = await trainingApi.presets() }
  catch (reason) { ElMessage.error(reason instanceof Error ? reason.message : t("training.presetsDialog.loadFail")) }
  finally { presetsLoading.value = false }
}

function applyPreset(preset: TrainingPreset) {
  model.value = { ...model.value, ...preset.data }
  presetsOpen.value = false
  ElMessage.success(t("training.presetsDialog.applied", { name: preset.metadata.name }))
}

async function importFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ""
  if (!file) return
  try {
    const text = await file.text()
    const config = file.name.toLowerCase().endsWith(".json") ? JSON.parse(text) : parse(text)
    await applyImportedConfig(config as FormModel)
  } catch (reason) {
    if (reason !== "cancel" && reason !== "close") ElMessage.error(reason instanceof Error ? reason.message : t("training.importMsg.fail"))
  }
}

async function exportConfig() {
  if (!validate()) return
  try {
    const normalized = await trainingApi.normalizeExport(props.schemaName, output.value)
    const blob = new Blob([stringify(normalized.config)], { type: "application/toml;charset=utf-8" })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement("a")
    anchor.href = url
    anchor.download = `${String(normalized.config.output_name || props.schemaName)}.toml`
    anchor.click()
    URL.revokeObjectURL(url)
    normalized.warnings.forEach((warning) => ElMessage.warning(warning))
  } catch (reason) { ElMessage.error(reason instanceof Error ? reason.message : t("training.exportFail")) }
}

async function submit() {
  if (!validate() || submitting.value) return
  try {
    await ElMessageBox.confirm(t("training.submitConfirm.message"), t("training.submitConfirm.title"), { confirmButtonText: t("training.submitConfirm.confirm"), cancelButtonText: t("training.submitConfirm.cancel"), type: "warning" })
    submitting.value = true
    if (props.schemaName === "anima-lora-fast") {
      const preflight = await trainingApi.animaFastPreflight(output.value)
      if (!preflight.ok) throw new Error(preflight.errors?.join("\n") || t("training.submitConfirm.preflightFail"))
      preflight.warnings?.forEach((warning) => ElMessage.warning(warning))
    }
    if (props.schemaName === "krea2-lora") {
      const preflight = await trainingApi.musubiPreflight(output.value)
      if (!preflight.ok) throw new Error(preflight.errors?.join("\n") || t("training.submitConfirm.preflightFail"))
      preflight.warnings?.forEach((warning) => ElMessage.warning(warning))
    }
    started.value = await trainingApi.run(output.value)
    tasksStore.refresh({ silent: true })
    saveHistory()
    ElMessage.success(t("training.submitConfirm.started", { id: started.value.task_id }))
  } catch (reason) {
    if (reason !== "cancel" && reason !== "close") ElMessage.error(reason instanceof Error ? reason.message : t("training.submitConfirm.fail"))
  } finally { submitting.value = false }
}

async function resetConfig() {
  if (!schema.value) return
  try {
    await ElMessageBox.confirm(t("training.actions.resetConfirm"), t("training.resetDialog.title"), { confirmButtonText: t("training.actions.reset"), cancelButtonText: t("training.resetDialog.cancel"), type: "warning" })
  } catch { return }
  localStorage.removeItem(autosaveKey())
  model.value = { ...createDefaultModel(schema.value), ...props.fieldDefaults }
  ElMessage.success(t("training.actions.resetDone"))
}

async function copyToml() {
  try {
    await navigator.clipboard.writeText(outputText.value)
    ElMessage.success(t("training.preview.copied"))
  } catch { ElMessage.error(t("training.preview.copyFail")) }
}

function openImport() { importInput.value?.click() }

async function stopTraining() {
  const task = currentRunning.value
  if (!task) return
  try {
    await ElMessageBox.confirm(t("tasks.terminate.confirm", { id: task.id }), t("tasks.terminate.title"), { confirmButtonText: t("tasks.terminate.confirmButton"), cancelButtonText: t("tasks.terminate.cancel"), type: "warning" })
    await tasksStore.terminate(task.id)
    ElMessage.success(t("tasks.terminate.success"))
  } catch (reason) {
    if (reason !== "cancel" && reason !== "close") ElMessage.error(reason instanceof Error ? reason.message : t("tasks.terminate.fail"))
  }
}

watch(() => props.schemaName, () => { started.value = undefined; loadHistory(); load() })
watch(model, (value) => localStorage.setItem(autosaveKey(), JSON.stringify(value)), { deep: true })
watch(previewCollapsed, (value) => persistPreviewCollapsed(value))
onMounted(() => { migrateLegacyStorage(); loadHistory(); load(); tasksStore.refresh(); tasksTimer = window.setInterval(() => tasksStore.refresh({ silent: true }), 2000) })
onBeforeUnmount(() => { window.clearInterval(tasksTimer); localStorage.setItem(autosaveKey(), JSON.stringify(model.value)); sessionStorage.setItem("mikazuki-carry-over", JSON.stringify(model.value)) })
</script>

<template>
  <div class="training-layout schema-training-layout" :class="{ bare, 'preview-docked': previewCollapsed }">
    <section class="form-canvas" :class="{ 'with-schema-toc': tocSections.length > 1 }">
      <div class="schema-form-shell" :class="{ 'has-toc': tocSections.length > 1 }">
        <SectionToc v-if="tocSections.length > 1" :sections="tocSections" />
        <div class="schema-form-binder">
          <div v-if="!bare" class="section-heading"><span>{{ area }}</span><h1>{{ title }}</h1><p>{{ t("training.intro") }}</p></div>
          <input ref="importInput" class="visually-hidden" type="file" accept=".toml,.json" @change="importFile">
          <slot name="form-top" />
          <div v-if="loading" class="schema-state"><strong>{{ t("training.loadingSchema") }}</strong><span>{{ t("training.loadingSchemaHint") }}</span></div>
          <div v-else-if="error" class="schema-state schema-error"><strong>{{ t("training.schemaError") }}</strong><span>{{ error }}</span><button @click="load">{{ t("training.retry") }}</button></div>
          <DynamicSchemaForm v-else-if="schema" v-model="model" :schema="schema" :errors="errors" />
        </div>
      </div>
    </section>
    <aside class="control-panel" :class="{ collapsed: previewCollapsed }">
      <div class="panel-rail">
        <button class="rail-handle" @click="previewCollapsed = false">
          <span class="rail-arrow" aria-hidden="true">←</span>
          <span v-if="diagnostics.errors.length || diagnostics.warnings.length" class="rail-alert" :class="{ error: diagnostics.errors.length > 0 }"></span>
          <span class="rail-label">{{ t("training.preview.railTitle") }}</span>
          <b>{{ t("training.preview.count", { n: Object.keys(output).length }) }}</b>
        </button>
        <button class="primary-action rail-submit" :disabled="!schema || submitting || diagnostics.errors.length > 0" @click="submit">{{ submitting ? t("training.railSubmitting") : t("training.railStart") }}</button>
        <button class="danger-action rail-stop" :disabled="!currentRunning || Boolean(tasksStore.terminatingId)" @click="stopTraining">{{ t("training.railStop") }}</button>
      </div>
      <div class="panel-full">
        <div v-if="!bare" class="panel-copy"><span class="eyebrow">TRAINING CONTROL</span><h2>{{ title }}</h2><p>{{ t("training.panelHint") }}</p></div>
        <div v-if="diagnostics.errors.length || diagnostics.warnings.length" class="param-diagnostics"><p v-for="item in diagnostics.errors" :key="item" class="error">{{ item }}</p><p v-for="item in diagnostics.warnings" :key="item">{{ item }}</p></div>
        <div v-if="started" class="started-task"><strong>{{ t("training.startedTask") }}</strong><code>{{ started.task_id }}</code><a :href="trainLogHref" target="_blank" rel="noreferrer">{{ t("training.openLog") }}</a><RouterLink to="/tasks">{{ t("training.viewTasks") }}</RouterLink></div>
        <section class="preview-panel" :class="{ collapsed: previewCollapsed }"><header><span>{{ t("training.preview.panelTitle") }}</span><b>{{ t("training.preview.count", { n: Object.keys(output).length }) }}</b><span class="preview-actions"><button class="preview-collapse" :title="previewCollapsed ? t('training.preview.expand') : t('training.preview.collapse')" :aria-label="previewCollapsed ? t('training.preview.expand') : t('training.preview.collapse')" @click="previewCollapsed = !previewCollapsed">{{ previewCollapsed ? "←" : "→" }}</button><button @click="copyToml">{{ t("training.preview.copy") }}</button></span></header><pre v-show="!previewCollapsed">{{ outputText }}</pre></section>
        <div class="panel-actions"><button @click="openPresets">{{ t("training.toolbar.presets") }}</button><button @click="saveHistory">{{ t("training.toolbar.save") }}</button><button @click="openImport">{{ t("training.toolbar.import") }}</button><button @click="historyOpen = true">{{ t("training.toolbar.history") }}</button><button @click="exportConfig">{{ t("training.toolbar.export") }}</button><button @click="resetConfig">{{ t("training.toolbar.reset") }}</button></div>
        <button class="secondary-action schema-validate" :disabled="!schema" @click="validate">{{ t("training.validate") }}</button>
        <div class="submit-row"><button class="primary-action train-submit" :disabled="!schema || submitting || diagnostics.errors.length > 0" @click="submit">{{ submitting ? t("training.submitting") : t("training.start") }}</button><button class="danger-action stop-training" :disabled="!currentRunning || Boolean(tasksStore.terminatingId)" @click="stopTraining">{{ tasksStore.terminatingId ? t("tasks.detail.stopping") : t("training.stop") }}</button></div>
      </div>
    </aside>
  </div>

  <el-dialog v-model="historyOpen" :title="t('training.historyDialog.title')" width="min(760px, 92vw)"><div class="config-list"><article v-for="(row, index) in history" :key="`${row.time}-${index}`"><div><strong>{{ row.name || t('training.historyDialog.unnamed') }}</strong><span>{{ row.time }}</span></div><button @click="model = { ...createDefaultModel(schema!), ...row.value }; historyOpen = false">{{ t("training.historyDialog.use") }}</button><button class="danger" @click="deleteHistory(index)">{{ t("training.historyDialog.delete") }}</button></article><p v-if="!history.length">{{ t("training.historyDialog.empty") }}</p></div></el-dialog>
  <el-dialog v-model="presetsOpen" :title="t('training.presetsDialog.title')" width="min(760px, 92vw)"><div v-loading="presetsLoading" class="config-list"><article v-for="preset in filteredPresets" :key="preset.metadata.name"><div><strong>{{ preset.metadata.name }}</strong><span>{{ preset.metadata.description || `${preset.metadata.author || ''} ${preset.metadata.version || ''}` }}</span></div><button @click="applyPreset(preset)">{{ t("training.presetsDialog.apply") }}</button></article><p v-if="!presetsLoading && !filteredPresets.length">{{ t("training.presetsDialog.empty") }}</p></div></el-dialog>
</template>
