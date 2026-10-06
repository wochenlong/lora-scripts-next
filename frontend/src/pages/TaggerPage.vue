<script setup lang="ts">
import { computed, onActivated, onBeforeUnmount, onDeactivated, reactive, ref, watch } from "vue"
import { ElMessage } from "element-plus"
import { storeToRefs } from "pinia"
import { useI18n } from "vue-i18n"
import { useRoute } from "vue-router"
import { useTaggerStore } from "../stores/tagger"
import { llmApi, type LlmConfig } from "../api/llm"
import { taggerApi, type CaptionJobRequest, type CaptionJobStatus, type CaptionMode, type TaggerRequest } from "../api/tagger"
import PathPickerDialog from "../components/PathPickerDialog.vue"
import { useServerPathPick } from "../composables/useServerPathPick"

const models = ["wd14-convnextv2-v2", "wd-convnext-v3", "wd-swinv2-v3", "wd-vit-v3", "wd14-swinv2-v2", "wd14-vit-v2", "wd14-moat-v2", "wd-eva02-large-tagger-v3", "wd-vit-large-tagger-v3", "cl_tagger_1_01"]
const form = reactive<TaggerRequest>({ path: "", interrogator_model: models[0], threshold: .35, character_threshold: .6, add_rating_tag: false, add_model_tag: false, additional_tags: "", exclude_tags: "", escape_tag: true, batch_input_recursive: false, batch_output_action_on_conflict: "copy", replace_underscore: true, download_endpoint: "", replace_underscore_excludes: "0_0, (o)_(o), +_+, +_-, ._., <o>_<o>, <|>_<|>, =_=, >_<, 3_3, 6_9, >_o, @_@, ^_^, o_o, u_u, x_x, |_|, ||_||" })
const captionForm = reactive<CaptionJobRequest>({ path: "", mode: "natural", recursive: false, profile_id: undefined, prompt: '请用{{language}}（zh-CN 使用简体中文）描述图片中的主要可见内容，只返回 JSON 对象，字段必须为 caption 和 language；language 必须是 "{{language}}"，不要输出 Markdown。', language: "zh-CN", layout: "tags_then_caption", conflict_action: "copy", interrogator_model: models[0], download_endpoint: "", threshold: .35, character_threshold: .6, add_rating_tag: false, add_model_tag: false, additional_tags: "", exclude_tags: "", escape_tag: true, replace_underscore: true, replace_underscore_excludes: form.replace_underscore_excludes })
const mode = ref<CaptionMode>("tag")
const store = useTaggerStore()
const { status, error, submitting, busy } = storeToRefs(store)
const { t } = useI18n()
const route = useRoute()
const llmConfig = ref<LlmConfig>({ version: 5, profiles: [], routes: {}, prompt_presets: [], cache: { translation: true, caption: true } })
const captionStatus = ref<CaptionJobStatus>({ job_id: null, phase: "idle", mode: null, message: "", current: 0, total: 0, filename: "", succeeded: 0, failed: 0, cancelled: 0, errors: [], updated_at: 0 })
const captionError = ref("")
const previewImagePath = ref("")
const previewResult = ref("")
const llmLoading = ref(false)
const captionSubmitting = ref(false)
const profileEditorOpen = ref(false)
const profileSaving = ref(false)
const profileDraft = reactive({ id: "vision-profile", name: "视觉 Profile", endpoint: "", model: "", source: "remote" as "remote" | "local-endpoint", api_key: "", languages: "zh-CN,en" })
let timer: number | undefined

const visionProfiles = computed(() => llmConfig.value.profiles.filter(profile => profile.enabled && profile.ready && profile.capabilities.includes("vision")))
const captionBusy = computed(() => ["pending", "captioning", "cancelling"].includes(captionStatus.value.phase))
const captionPercent = computed(() => captionStatus.value.total ? Math.round(captionStatus.value.current / captionStatus.value.total * 100) : 0)
const downloadPercent = computed(() => status.value.download.percent || (status.value.download.total ? Math.round(status.value.download.current / status.value.download.total * 100) : 0))
const taggingPercent = computed(() => status.value.tagging.total ? Math.round(status.value.tagging.current / status.value.tagging.total * 100) : 0)

async function loadLlmProfiles() {
  if (llmLoading.value) return
  llmLoading.value = true
  try {
    llmConfig.value = await llmApi.profiles()
    if (!captionForm.profile_id && visionProfiles.value.length) captionForm.profile_id = visionProfiles.value[0].id
  } catch (caught) {
    captionError.value = caught instanceof Error ? caught.message : String(caught)
  } finally {
    llmLoading.value = false
  }
}

async function saveVisionProfile() {
  if (!profileDraft.endpoint.trim() || !profileDraft.model.trim()) {
    ElMessage.error(t("tagger.caption.profileFieldsRequired"))
    return
  }
  profileSaving.value = true
  try {
    const profile = {
      id: profileDraft.id.trim() || "vision-profile",
      name: profileDraft.name.trim() || profileDraft.id.trim() || "Vision profile",
      endpoint: profileDraft.endpoint.trim(),
      model: profileDraft.model.trim(),
      source: profileDraft.source,
      capabilities: ["text", "vision"],
      languages: profileDraft.languages.split(",").map(item => item.trim()).filter(Boolean),
      api_key: profileDraft.api_key,
      enabled: true,
      ready: true,
    }
    const profiles = llmConfig.value.profiles.filter(item => item.id !== profile.id).map(item => ({ ...item, api_key: item.api_key || "********" }))
    llmConfig.value = await llmApi.saveConfig({ profiles: [...profiles, profile], routes: { ...llmConfig.value.routes, caption: profile.id } })
    captionForm.profile_id = profile.id
    profileEditorOpen.value = false
    profileDraft.api_key = ""
    ElMessage.success(t("tagger.caption.profileSaved"))
  } catch (caught) {
    ElMessage.error(caught instanceof Error ? caught.message : String(caught))
  } finally {
    profileSaving.value = false
  }
}

function syncCaptionPath() {
  captionForm.path = form.path
  captionForm.interrogator_model = form.interrogator_model
  captionForm.download_endpoint = form.download_endpoint
  captionForm.threshold = form.threshold
  captionForm.character_threshold = form.character_threshold
  captionForm.additional_tags = form.additional_tags
  captionForm.exclude_tags = form.exclude_tags
  captionForm.replace_underscore = form.replace_underscore
  captionForm.replace_underscore_excludes = form.replace_underscore_excludes
  captionForm.escape_tag = form.escape_tag
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
  if (!captionForm.path.trim()) return ElMessage.error(t("tagger.msg.pathRequired"))
  if (!captionForm.profile_id) return ElMessage.error(t("tagger.caption.profileRequired"))
  if (!captionForm.prompt.trim()) return ElMessage.error(t("tagger.caption.promptRequired"))
  captionSubmitting.value = true
  captionError.value = ""
  try {
    captionStatus.value = await taggerApi.captionStart({ ...captionForm, path: captionForm.path.replaceAll("\\", "/") })
    ElMessage.success(t("tagger.caption.submitted"))
  } catch (caught) {
    captionError.value = caught instanceof Error ? caught.message : String(caught)
    ElMessage.error(captionError.value)
  } finally {
    captionSubmitting.value = false
  }
}

async function previewCaption() {
  syncCaptionPath()
  if (!previewImagePath.value.trim()) return ElMessage.error(t("tagger.caption.previewPathRequired"))
  if (!captionForm.profile_id) return ElMessage.error(t("tagger.caption.profileRequired"))
  try {
    const result = await taggerApi.captionPreview({ ...captionForm, image_path: previewImagePath.value })
    previewResult.value = result.caption
  } catch (caught) {
    captionError.value = caught instanceof Error ? caught.message : String(caught)
    ElMessage.error(captionError.value)
  }
}

async function captionAction(kind: "cancel" | "retry") {
  try {
    captionStatus.value = kind === "cancel" ? await taggerApi.captionCancel() : await taggerApi.captionRetryFailed()
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
  captionForm.mode = value === "tag" ? "natural" : value
  if (value !== "tag") void loadLlmProfiles()
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
}

async function refresh() {
  if (mode.value === "tag") await store.refresh()
  else {
    try {
      captionStatus.value = await taggerApi.captionStatus()
      captionError.value = ""
    } catch (caught) {
      captionError.value = caught instanceof Error ? caught.message : t("tagger.msg.statusFail")
    }
  }
}

onActivated(() => {
  const queryPath = route?.query.path
  if (typeof queryPath === "string" && queryPath.trim()) {
    form.path = queryPath
    captionForm.path = queryPath
  }
  void refresh()
  if (mode.value !== "tag") void loadLlmProfiles()
  stopPolling()
  timer = window.setInterval(refresh, 1200)
})
onDeactivated(stopPolling)
onBeforeUnmount(stopPolling)
</script>

<template>
  <div class="tagger-page">
    <section class="tagger-form">
      <header>
        <span class="eyebrow">DATASET TAGGER</span>
        <h1>{{ t("tagger.title") }}</h1>
        <p>{{ t("tagger.subtitle") }}</p>
      </header>
      <div class="tagger-mode-tabs" role="tablist">
        <button type="button" :class="{ active: mode === 'tag' }" @click="mode = 'tag'">{{ t("tagger.modeTag") }}</button>
        <button type="button" :class="{ active: mode === 'natural' }" @click="mode = 'natural'">{{ t("tagger.modeNatural") }}</button>
        <button type="button" :class="{ active: mode === 'combined' }" @click="mode = 'combined'">{{ t("tagger.modeCombined") }}</button>
      </div>
      <div class="tagger-grid">
        <label>{{ t("tagger.pathLabel") }}<span class="path-row"><input v-model="form.path" placeholder="/data/datasets/images" /><button :disabled="picking" @click.prevent="browsePath">{{ t("schemaForm.browse") }}</button></span></label>
        <label>{{ t("tagger.modelLabel") }}<select v-model="form.interrogator_model"><option v-for="model in models" :key="model">{{ model }}</option></select></label>
        <template v-if="mode === 'tag'">
          <label>{{ t("tagger.thresholdLabel") }}<input v-model.number="form.threshold" type="number" min="0" max="1" step="0.05" /></label>
          <label>{{ t("tagger.characterThresholdLabel") }}<input v-model.number="form.character_threshold" type="number" min="0" max="1" step="0.05" /></label>
          <label>{{ t("tagger.additionalTagsLabel") }}<input v-model="form.additional_tags" /></label>
          <label>{{ t("tagger.excludeTagsLabel") }}<input v-model="form.exclude_tags" /></label>
          <label>{{ t("tagger.endpointLabel") }}<input v-model="form.download_endpoint" :placeholder="t('tagger.endpointPlaceholder')" /></label>
          <label>{{ t("tagger.conflictLabel") }}<select v-model="form.batch_output_action_on_conflict"><option value="ignore">{{ t("tagger.conflict.ignore") }}</option><option value="copy">{{ t("tagger.conflict.copy") }}</option><option value="prepend">{{ t("tagger.conflict.prepend") }}</option><option value="append">{{ t("tagger.conflict.append") }}</option></select></label>
        </template>
        <template v-else>
          <label>{{ t("tagger.caption.profile") }}<select v-model="captionForm.profile_id" :disabled="llmLoading"><option v-for="profile in visionProfiles" :key="profile.id" :value="profile.id">{{ profile.name }} · {{ profile.source === 'remote' ? t("tagger.caption.remote") : t("tagger.caption.local") }}</option></select><button type="button" class="inline-config-button" @click="profileEditorOpen = !profileEditorOpen">{{ t("tagger.caption.manageProfiles") }}</button></label>
          <label>{{ t("tagger.caption.language") }}<select v-model="captionForm.language"><option value="zh-CN">简体中文</option><option value="zh-TW">繁體中文</option><option value="en">English</option><option value="ja">日本語</option></select></label>
          <label class="wide-field">{{ t("tagger.caption.prompt") }}<textarea v-model="captionForm.prompt" rows="4" /></label>
          <label>{{ t("tagger.caption.layout") }}<select v-model="captionForm.layout"><option value="tags_then_caption">{{ t("tagger.caption.layoutTagsFirst") }}</option><option value="caption_then_tags">{{ t("tagger.caption.layoutCaptionFirst") }}</option><option value="caption_only">{{ t("tagger.caption.layoutCaptionOnly") }}</option></select></label>
          <label>{{ t("tagger.caption.conflict") }}<select v-model="captionForm.conflict_action"><option value="ignore">{{ t("tagger.conflict.ignore") }}</option><option value="copy">{{ t("tagger.conflict.copy") }}</option><option value="prepend">{{ t("tagger.conflict.prepend") }}</option><option value="append">{{ t("tagger.conflict.append") }}</option></select></label>
          <label class="wide-field">{{ t("tagger.caption.previewPath") }}<input v-model="previewImagePath" placeholder="/data/datasets/images/example.png" /></label>
          <div class="caption-privacy wide-field">{{ t("tagger.caption.privacy") }}</div>
          <div v-if="profileEditorOpen" class="caption-profile-editor wide-field">
            <label>{{ t("tagger.caption.profileId") }}<input v-model="profileDraft.id" /></label>
            <label>{{ t("tagger.caption.profileName") }}<input v-model="profileDraft.name" /></label>
            <label>{{ t("tagger.caption.profileSource") }}<select v-model="profileDraft.source"><option value="remote">{{ t("tagger.caption.remote") }}</option><option value="local-endpoint">{{ t("tagger.caption.local") }}</option></select></label>
            <label>{{ t("tagger.caption.endpoint") }}<input v-model="profileDraft.endpoint" placeholder="https://.../chat/completions" /></label>
            <label>{{ t("tagger.caption.model") }}<input v-model="profileDraft.model" /></label>
            <label>{{ t("tagger.caption.apiKey") }}<input v-model="profileDraft.api_key" type="password" autocomplete="new-password" /></label>
            <label>{{ t("tagger.caption.languages") }}<input v-model="profileDraft.languages" placeholder="zh-CN,en" /></label>
            <button type="button" class="primary-action" :disabled="profileSaving" @click="saveVisionProfile">{{ t("tagger.caption.saveProfile") }}</button>
          </div>
          <div v-if="previewResult" class="caption-preview wide-field"><strong>{{ t("tagger.caption.previewResult") }}</strong><p>{{ previewResult }}</p></div>
        </template>
      </div>
      <div class="check-row">
        <label v-if="mode === 'tag'"><input v-model="form.batch_input_recursive" type="checkbox" />{{ t("tagger.recursive") }}</label>
        <label v-else><input v-model="captionForm.recursive" type="checkbox" />{{ t("tagger.recursive") }}</label>
        <label><input v-model="form.replace_underscore" type="checkbox" />{{ t("tagger.replaceUnderscore") }}</label>
        <label><input v-model="form.escape_tag" type="checkbox" />{{ t("tagger.escapeTag") }}</label>
        <label><input v-model="form.add_rating_tag" type="checkbox" />{{ t("tagger.addRatingTag") }}</label>
        <label><input v-model="form.add_model_tag" type="checkbox" />{{ t("tagger.addModelTag") }}</label>
      </div>
    </section>
    <aside class="tagger-status">
      <template v-if="mode === 'tag'">
        <span class="task-status">{{ status.phase }}</span><h2>{{ status.message || t("tagger.idle") }}</h2><p v-if="error">{{ error }}</p>
        <div class="meter"><header><span>{{ t("tagger.downloadMeter") }}</span><b>{{ downloadPercent }}%</b></header><div><i :style="{ width: downloadPercent + '%' }" /></div><small>{{ status.download.filename || t("tagger.downloadIdle") }}</small></div>
        <div class="meter"><header><span>{{ t("tagger.taggingMeter") }}</span><b>{{ taggingPercent }}%</b></header><div><i :style="{ width: taggingPercent + '%' }" /></div><small>{{ status.tagging.current }} / {{ status.tagging.total }} {{ status.tagging.filename }}</small></div>
        <div class="tagger-actions"><button v-if="busy" class="danger-action" :disabled="submitting" @click="invoke('cancel')">{{ t("tagger.cancel") }}</button><button v-else class="primary-action" :disabled="submitting" @click="start">{{ t("tagger.start") }}</button><button class="secondary-action" :disabled="submitting || status.phase === 'tagging'" @click="invoke('prefetch')">{{ t("tagger.prefetch") }}</button><button class="secondary-action" :disabled="submitting" @click="invoke('reset')">{{ t("tagger.reset") }}</button></div>
      </template>
      <template v-else>
        <span class="task-status">{{ captionStatus.phase }}</span>
        <h2>{{ captionStatus.message || t("tagger.caption.idle") }}</h2>
        <p v-if="captionError">{{ captionError }}</p>
        <p class="caption-route-hint">{{ t("tagger.caption.remoteFirst") }}</p>
        <div class="meter"><header><span>{{ t("tagger.caption.progress") }}</span><b>{{ captionPercent }}%</b></header><div><i :style="{ width: captionPercent + '%' }" /></div><small>{{ captionStatus.current }} / {{ captionStatus.total }} {{ captionStatus.filename }}</small></div>
        <div v-if="captionStatus.failed" class="caption-failures">{{ t("tagger.caption.failed", { n: captionStatus.failed }) }}</div>
        <div class="tagger-actions"><button v-if="captionBusy" class="danger-action" :disabled="captionSubmitting" @click="captionAction('cancel')">{{ t("tagger.cancel") }}</button><button v-else class="primary-action" :disabled="captionSubmitting || !visionProfiles.length" @click="startCaption">{{ t("tagger.start") }}</button><button v-if="captionStatus.failed" class="secondary-action" :disabled="captionBusy" @click="captionAction('retry')">{{ t("tagger.caption.retryFailed") }}</button><button class="secondary-action" :disabled="captionSubmitting || !previewImagePath" @click="previewCaption">{{ t("tagger.caption.preview") }}</button></div>
      </template>
    </aside>
    <PathPickerDialog v-model="pathPickerOpen" :mode="pathPickerMode" :initial-path="pathPickerInitial" :name-filter="pathPickerFilter" @confirm="onPathConfirm" @cancel="onPathCancel" />
  </div>
</template>
