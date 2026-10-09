<script setup lang="ts">
import { computed, onActivated, onBeforeUnmount, onDeactivated, reactive, ref, watch } from "vue"
import { ElMessage, ElSelect, ElOption, ElOptionGroup } from "element-plus"
import { Setting, Close, RefreshLeft } from "@element-plus/icons-vue"
import { storeToRefs } from "pinia"
import { useI18n } from "vue-i18n"
import { useRoute } from "vue-router"
import { useTaggerStore } from "../stores/tagger"
import { taggerApi, type TaggerRequest } from "../api/tagger"
import ManagedDatasetPicker from "../components/dataset/ManagedDatasetPicker.vue"

const models = [
  "wd14-convnextv2-v2",
  "wd-convnext-v3",
  "wd-swinv2-v3",
  "wd-vit-v3",
  "wd14-swinv2-v2",
  "wd14-vit-v2",
  "wd14-moat-v2",
  "wd-eva02-large-tagger-v3",
  "wd-vit-large-tagger-v3",
  "cl_tagger_1_01",
]
const form = reactive<TaggerRequest>({
  path: "",
  interrogator_model: models[0],
  threshold: 0.35,
  character_threshold: 0.6,
  add_rating_tag: false,
  add_model_tag: false,
  additional_tags: "",
  exclude_tags: "",
  escape_tag: true,
  batch_input_recursive: false,
  batch_output_action_on_conflict: "ignore",
  replace_underscore: true,
  replace_underscore_excludes:
    "0_0, (o)_(o), +_+, +_-, ._., <o>_<o>, <|>_<|>, =_=, >_<, 3_3, 6_9, >_o, @_@, ^_^, o_o, u_u, x_x, |_|, ||_||",
})
const store = useTaggerStore()
const { status, error, submitting, busy } = storeToRefs(store)
const { t } = useI18n()
const route = useRoute()
const parametersOpen = ref(false)
const parameterTab = ref("model")
const CAPTION_TEMPLATES_KEY = "nt.tagger.captionTemplates"
const defaultCaptionPrompt = t("tagger.workspace.defaultPrompt")
const captionPrompt = ref(defaultCaptionPrompt)
const captionTemplate = ref("default")
const captionTemplates = ref<Record<string, string>>({})
function readCaptionTemplates() {
  try {
    const value = JSON.parse(localStorage.getItem(CAPTION_TEMPLATES_KEY) || "{}")
    captionTemplates.value = value && typeof value === "object" && !Array.isArray(value) ? value : {}
  } catch {
    captionTemplates.value = {}
  }
}
readCaptionTemplates()
function loadCaptionTemplate() {
  captionPrompt.value = captionTemplate.value === "default"
    ? defaultCaptionPrompt
    : captionTemplates.value[captionTemplate.value] || defaultCaptionPrompt
}
function saveCaptionTemplate() {
  const key = `custom-${Date.now()}`
  captionTemplates.value = { ...captionTemplates.value, [key]: captionPrompt.value }
  localStorage.setItem(CAPTION_TEMPLATES_KEY, JSON.stringify(captionTemplates.value))
  captionTemplate.value = key
  ElMessage.success(t("tagger.msg.templateSaved"))
}
function updateCaptionTemplate() {
  if (captionTemplate.value === "default") return
  captionTemplates.value = { ...captionTemplates.value, [captionTemplate.value]: captionPrompt.value }
  localStorage.setItem(CAPTION_TEMPLATES_KEY, JSON.stringify(captionTemplates.value))
  ElMessage.success(t("tagger.msg.templateUpdated"))
}
function deleteCaptionTemplate() {
  if (captionTemplate.value === "default") return
  const next = { ...captionTemplates.value }
  delete next[captionTemplate.value]
  captionTemplates.value = next
  localStorage.setItem(CAPTION_TEMPLATES_KEY, JSON.stringify(next))
  resetCaptionPrompt()
  ElMessage.success(t("tagger.msg.templateDeleted"))
}
function resetCaptionPrompt() {
  captionTemplate.value = "default"
  captionPrompt.value = defaultCaptionPrompt
}
const modelAvailability = ref<Record<string, boolean>>({})
const availabilityError = ref(false)
async function refreshModels() {
  try {
    const entries = await taggerApi.models()
    modelAvailability.value = Object.fromEntries(entries.map(entry => [entry.id, entry.downloaded]))
    availabilityError.value = false
  } catch {
    modelAvailability.value = {}
    availabilityError.value = true
  }
}
function availabilityLabel(model: string) {
  if (status.value.model === model && status.value.phase === "downloading") return t("tagger.downloadMeter")
  const value = modelAvailability.value[model]
  return t(value === true ? "tagger.workspace.downloaded" : value === false ? "tagger.workspace.toDownload" : "tagger.workspace.unknown")
}
watch(() => status.value.phase, (phase, oldPhase) => {
  if (phase !== oldPhase && oldPhase === "downloading") void refreshModels()
})
function restoreParameters() {
  Object.assign(form, {
    threshold: 0.35, character_threshold: 0.6, additional_tags: "", exclude_tags: "",
    batch_output_action_on_conflict: "ignore", batch_input_recursive: false,
    replace_underscore: true, escape_tag: true, add_rating_tag: false, add_model_tag: false,
  })
}
const modelGroups = [
  { name: "WD", models: models.filter(model => model.startsWith("wd")) },
  { name: "CL", models: models.filter(model => model.startsWith("cl")) },
]
const downloadPercent = computed(
  () =>
    status.value.download.percent ||
    (status.value.download.total ? Math.round((status.value.download.current / status.value.download.total) * 100) : 0),
)
const taggingPercent = computed(() =>
  status.value.tagging.total ? Math.round((status.value.tagging.current / status.value.tagging.total) * 100) : 0,
)
let timer: number | undefined
async function start() {
  if (!form.path.trim()) return ElMessage.error(t("tagger.msg.pathRequired"))
  try {
    await store.start({ ...form, path: form.path.replaceAll("\\", "/") })
    ElMessage.success(t("tagger.msg.submitted"))
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : t("tagger.msg.submitFail"))
  }
}
async function invoke(kind: "prefetch" | "cancel" | "reset") {
  try {
    if (kind === "prefetch") await store.prefetch(form.interrogator_model)
    else await store[kind]()
    ElMessage.success(
      kind === "cancel" ? t("tagger.msg.cancelRequested") : kind === "reset" ? t("tagger.msg.resetDone") : t("tagger.msg.prefetchStarted"),
    )
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : t("tagger.msg.actionFail"))
  }
}
function stopPolling() {
  window.clearInterval(timer)
  timer = undefined
}
onActivated(() => {
  const queryPath = route?.query.path
  if (typeof queryPath === "string" && queryPath.trim()) form.path = queryPath
  void store.refresh()
  void refreshModels()
  readCaptionTemplates()
  stopPolling()
  timer = window.setInterval(store.refresh, 1200)
})
onDeactivated(stopPolling)
onBeforeUnmount(stopPolling)
</script>

<template>
  <div class="tagger-page" :class="{ 'parameters-open': parametersOpen }">
    <section class="tagger-form">
      <header>
        <h1>{{ t("datasetManage.openTagger") }}</h1>
        <button class="tagger-settings-button tagger-settings-label" data-testid="parameter-toggle" :aria-label="t('tagger.workspace.parameters')" :title="t('tagger.workspace.parameters')" :aria-expanded="parametersOpen" aria-controls="tagger-parameters" @click="parametersOpen = !parametersOpen"><Setting />{{ t("tagger.workspace.settings") }}</button>
      </header>
      <div class="tagger-grid">
        <label class="tagger-dataset-path"
          >{{ t("tagger.pathLabel")
          }}<span class="path-row"
            ><input v-model="form.path" :disabled="busy" placeholder="/data/datasets/images" /><ManagedDatasetPicker :disabled="busy" :initial-path="form.path" :loaded="Boolean(form.path)" @select="form.path = $event" /></span
          ></label>
      </div>
      <div class="tagger-choice-row">
        <span>{{ t("tagger.workspace.method") }}</span>
        <div class="tagger-segments"><button class="selected" aria-pressed="true">Tag</button><button disabled>{{ t("tagger.workspace.caption") }}</button></div>
      </div>
      <div class="tagger-choice-row">
        <span>{{ t("tagger.workspace.source") }}</span>
        <div class="tagger-segments"><button class="selected" aria-pressed="true">{{ t("tagger.workspace.local") }}</button><button disabled>API</button></div>
      </div>
      <div class="tagger-model-row">
        <label class="tagger-model-field"><span>{{ t("tagger.modelLabel") }}</span>
          <ElSelect v-model="form.interrogator_model" filterable :disabled="busy" :aria-label="t('tagger.modelLabel')" data-testid="model-select">
            <ElOptionGroup v-for="group in modelGroups" :key="group.name" :label="group.name">
              <ElOption v-for="model in group.models" :key="model" :label="model" :value="model"><span>{{ model }}</span><small class="tagger-option-state">{{ availabilityLabel(model) }}</small></ElOption>
            </ElOptionGroup>
          </ElSelect>
        </label>
        <span class="tagger-model-state" :class="{ ready: modelAvailability[form.interrogator_model] === true }">{{ availabilityLabel(form.interrogator_model) }}</span>
        <button v-if="availabilityError" class="secondary-action" @click="refreshModels">{{ t("datasetManage.retry") }}</button>
        <span v-if="status.phase === 'downloading'">{{ t("tagger.downloadMeter") }} {{ downloadPercent }}% · {{ status.download.filename }}</span>
      </div>
      <div class="tagger-choice-row">
        <label for="tagger-conflict">{{ t("tagger.conflictLabel") }}</label>
        <select id="tagger-conflict" v-model="form.batch_output_action_on_conflict" :disabled="busy" class="tagger-conflict-select">
          <option value="ignore">{{ t("tagger.conflict.ignore") }}</option>
          <option value="copy">{{ t("tagger.conflict.copy") }}</option>
          <option value="prepend">{{ t("tagger.conflict.prepend") }}</option>
        </select>
      </div>
      <section class="tagger-run">
        <p>{{ t("tagger.conflictLabel") }}: {{ t(`tagger.conflict.${form.batch_output_action_on_conflict}`) }}</p>
        <button v-if="busy" class="danger-action tagger-start" :disabled="submitting" @click="invoke('cancel')">{{ t("tagger.cancel") }}</button>
        <button v-else class="primary-action tagger-start" :disabled="submitting" @click="start">{{ t("tagger.start") }}</button>
        <div class="tagger-run-status" aria-live="polite">
          <p>{{ status.message || t("tagger.idle") }}</p>
          <p v-if="error" role="alert">{{ error }}</p>
          <div v-if="busy || status.tagging.total" class="meter">
            <header><span>{{ t("tagger.taggingMeter") }}</span><b>{{ taggingPercent }}%</b></header>
            <div><i :style="{ width: `${taggingPercent}%` }" /></div>
            <small>{{ status.tagging.current }} / {{ status.tagging.total }} {{ status.tagging.filename }}</small>
          </div>
        </div>
        <div class="tagger-actions">
          <button class="secondary-action" :disabled="submitting || busy" @click="invoke('reset')">{{ t("tagger.reset") }}</button>
        </div>
      </section>
    </section>
    <button v-if="parametersOpen" class="tagger-panel-backdrop" :aria-label="t('tagger.workspace.close')" @click="parametersOpen = false" />
    <aside v-show="parametersOpen" id="tagger-parameters" class="tagger-parameters" :aria-label="t('tagger.workspace.parameters')" @keydown.esc="parametersOpen = false">
      <header><h2>{{ t("tagger.workspace.parameters") }}</h2><button class="tagger-settings-button" data-testid="parameter-close" :aria-label="t('tagger.workspace.close')" @click="parametersOpen = false"><Close /></button></header>
      <div class="tagger-panel-model"><span>{{ form.interrogator_model }}</span><button class="tagger-restore" :disabled="busy" @click="restoreParameters"><RefreshLeft />{{ t("tagger.workspace.restore") }}</button></div>
      <div class="tagger-panel-tabs" role="tablist">
        <button v-for="tab in ['model', 'tags', 'advanced']" :key="tab" :data-testid="`tab-${tab}`" role="tab" :aria-selected="parameterTab === tab" @click="parameterTab = tab">{{ t(`tagger.workspace.tab_${tab}`) }}</button>
      </div>
      <fieldset :disabled="busy">
      <div v-show="parameterTab === 'model'">
      <h2>{{ t("tagger.workspace.parameters") }}</h2>
      <div class="tagger-grid">
        <label>{{ t("tagger.thresholdLabel") }}<input v-model.number="form.threshold" type="number" min="0" max="1" step="0.05" /></label
        ><label
          >{{ t("tagger.characterThresholdLabel")
          }}<input v-model.number="form.character_threshold" type="number" min="0" max="1" step="0.05" /></label
        >
      </div>
      <dl class="tagger-model-info"><dt>{{ t("tagger.modelLabel") }}</dt><dd>{{ form.interrogator_model }}</dd><dt>{{ t("tagger.workspace.source") }}</dt><dd>{{ t("tagger.workspace.local") }}</dd><dt>{{ t("tagger.downloadMeter") }}</dt><dd>{{ availabilityLabel(form.interrogator_model) }}</dd></dl>
      </div>
      <div v-show="parameterTab === 'tags'">
      <div class="tagger-grid">
        <label>{{ t("tagger.additionalTagsLabel") }}<input v-model="form.additional_tags" /></label
        ><label>{{ t("tagger.excludeTagsLabel") }}<input v-model="form.exclude_tags" /></label
        >
      </div>
      <div class="check-row">
        <label><input v-model="form.batch_input_recursive" type="checkbox" />{{ t("tagger.recursive") }}</label
        ><label><input v-model="form.replace_underscore" type="checkbox" />{{ t("tagger.replaceUnderscore") }}</label
        ><label><input v-model="form.escape_tag" type="checkbox" />{{ t("tagger.escapeTag") }}</label
        ><label><input v-model="form.add_rating_tag" type="checkbox" />{{ t("tagger.addRatingTag") }}</label
        ><label><input v-model="form.add_model_tag" type="checkbox" />{{ t("tagger.addModelTag") }}</label>
      </div>
      </div>
      <div v-show="parameterTab === 'advanced'">
      <details class="tagger-future">
        <summary>{{ t("tagger.workspace.caption") }}</summary>
        <fieldset>
          <div class="tagger-grid">
            <label>{{ t("tagger.workspace.template") }}<select v-model="captionTemplate" data-testid="caption-template-select"><option value="default">{{ t("tagger.workspace.defaultTemplate") }}</option><option v-for="(_, key) in captionTemplates" :key="key" :value="key">{{ t("tagger.workspace.customTemplate") }}</option></select></label>
            <label>{{ t("tagger.workspace.language") }}<select><option>English</option><option>中文</option></select></label>
            <label class="tagger-dataset-path">{{ t("tagger.workspace.prompt") }}<textarea v-model="captionPrompt" data-testid="caption-prompt" rows="4" /></label>
          </div>
          <div class="tagger-actions">
            <button data-testid="caption-load" type="button" class="secondary-action" @click="loadCaptionTemplate">{{ t("tagger.workspace.load") }}</button>
            <button data-testid="caption-save-template" type="button" class="secondary-action" @click="saveCaptionTemplate">{{ t("tagger.workspace.saveAsTemplate") }}</button>
            <button data-testid="caption-update-template" type="button" class="secondary-action" :disabled="captionTemplate === 'default'" @click="updateCaptionTemplate">{{ t("tagger.workspace.updateTemplate") }}</button>
            <button data-testid="caption-delete-template" type="button" class="danger-action" :disabled="captionTemplate === 'default'" @click="deleteCaptionTemplate">{{ t("tagger.workspace.deleteTemplate") }}</button>
            <button data-testid="caption-reset" type="button" class="secondary-action" @click="resetCaptionPrompt">{{ t("tagger.workspace.reset") }}</button>
          </div>
        </fieldset>
      </details>
      </div>
      </fieldset>
    </aside>
  </div>
</template>
