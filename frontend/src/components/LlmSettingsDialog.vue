<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { ElDialog } from "element-plus"
import { useI18n } from "vue-i18n"
import { isVerifiedProfile, llmApi, type LlmConfig, type LlmProfile, type LocalVisionStatus } from "../api/llm"
import ManagedVisionModel from "./ManagedVisionModel.vue"

const props = defineProps<{ modelValue: boolean; capability: "text" | "vision"; imagePath?: string; embedded?: boolean }>()
const emit = defineEmits<{ "update:modelValue": [value: boolean]; saved: [config: LlmConfig] }>()
const { t } = useI18n()
const draft = ref<LlmConfig>({ version: 5, profiles: [], routes: {}, prompt_presets: [], cache: {} })
const committed = ref("")
const loading = ref(false)
const loaded = ref(false)
const saving = ref(false)
const testing = ref("")
const error = ref("")
const result = ref("")
let generation = 0
const local = ref<LocalVisionStatus>({ state: "missing", installed: false, downloaded_bytes: 0, total_bytes: 0 })
const localBusy = ref(false)
let localTimer: ReturnType<typeof setInterval> | undefined
let localRequest: AbortController | undefined

function stopMonitoring() {
  if (localTimer !== undefined) clearInterval(localTimer)
  localTimer = undefined
  localRequest?.abort()
  localRequest = undefined
}

async function loadLocal(revision: number) {
  if (localRequest || revision !== generation) return
  const request = new AbortController()
  localRequest = request
  try {
    const value = await llmApi.localVisionStatus(request.signal)
    if (revision === generation) local.value = value
  } catch (caught) {
    if (!request.signal.aborted && revision === generation) error.value = caught instanceof Error ? caught.message : String(caught)
  } finally {
    if (localRequest === request) localRequest = undefined
  }
}

async function manageLocal(action: "setup" | "start" | "stop" | "cancel") {
  if (localBusy.value) return
  localBusy.value = true
  error.value = ""
  const revision = generation
  try {
    const status = await llmApi.localVisionAction(action)
    if (revision !== generation) return
    local.value = status
    if (!loaded.value) return
    const config = await llmApi.config()
    if (revision !== generation) return
    // Runtime actions own managed assets only; preserve all unsaved user inputs.
    const assetId = local.value.model_id || "qwen3.5-2b-local"
    const managed = config.profiles.filter(profile => profile.source === "managed-local" && profile.asset_id === assetId)
    draft.value.profiles = [...draft.value.profiles.filter(profile => !(profile.source === "managed-local" && profile.asset_id === assetId)), ...managed]
    draft.value.revision = config.revision
    const baseline = JSON.parse(committed.value) as LlmConfig
    baseline.profiles = [...baseline.profiles.filter(profile => !(profile.source === "managed-local" && profile.asset_id === assetId)), ...managed]
    baseline.revision = config.revision
    committed.value = JSON.stringify(baseline)
    emit("saved", config)
  } catch (caught) {
    if (revision === generation) error.value = caught instanceof Error ? caught.message : String(caught)
  } finally {
    localBusy.value = false
  }
}

onBeforeUnmount(() => { generation += 1; stopMonitoring() })

const profiles = computed(() => [...draft.value.profiles].sort((a, b) => Number(b.source === "remote") - Number(a.source === "remote")))
const dirty = computed(() => JSON.stringify(draft.value) !== committed.value)
const textProfiles = computed(() => profiles.value.filter(profile => isVerifiedProfile(profile, "text")))
const visionProfiles = computed(() => profiles.value.filter(profile => isVerifiedProfile(profile, "vision")))
const managedProfile = computed(() => profiles.value.find(profile => profile.source === "managed-local" && profile.asset_id === (local.value.model_id || "qwen3.5-2b-local")))
const editableProfiles = computed(() => profiles.value.filter(profile => profile !== managedProfile.value))

function normalize(config: LlmConfig): LlmConfig {
  return { ...JSON.parse(JSON.stringify(config)), cache: { translation: true, caption: true, ...config.cache }, local_fallback_enabled: config.local_fallback_enabled ?? true }
}

watch(() => props.modelValue, async open => {
  const revision = ++generation
  stopMonitoring()
  loaded.value = false
  error.value = ""
  result.value = ""
  if (!open) {
    draft.value = { version: 5, profiles: [], routes: {}, prompt_presets: [], cache: {} }
    return
  }
  loading.value = true
  void loadLocal(revision)
  localTimer = setInterval(() => { void loadLocal(revision) }, 1200)
  try {
    const config = await llmApi.config()
    if (revision !== generation) return
    draft.value = normalize(config)
    committed.value = JSON.stringify(draft.value)
    loaded.value = true
  } catch (caught) {
    if (revision === generation) error.value = caught instanceof Error ? caught.message : String(caught)
  } finally {
    if (revision === generation) loading.value = false
  }
}, { immediate: true })

function close() {
  if (saving.value || testing.value || localBusy.value) return
  generation += 1
  stopMonitoring()
  draft.value = { version: 5, profiles: [], routes: {}, prompt_presets: [], cache: {} }
  emit("update:modelValue", false)
}

function add() {
  draft.value.profiles.push({ id: `profile-${Date.now()}`, name: t("llm.newProfile"), endpoint: "", model: "",
    source: "remote", capabilities: ["text", "vision"],
    languages: ["zh-CN", "en"], api_key: "", enabled: true, ready: false })
}

function languages(profile: LlmProfile, event: Event) {
  profile.languages = (event.target as HTMLInputElement).value.split(",").map(item => item.trim()).filter(Boolean)
}

function setReasoning(profile: LlmProfile, event: Event) {
  profile.metadata = { ...profile.metadata, reasoning_effort: (event.target as HTMLInputElement).value }
}

function reset() {
  draft.value = JSON.parse(committed.value)
  error.value = ""
  result.value = ""
}

async function save() {
  if (!loaded.value) return
  if (draft.value.profiles.some(profile => !profile.name.trim() || !profile.endpoint.trim() || !profile.model.trim() || !profile.capabilities.length || !profile.languages.length)) {
    error.value = t("llm.fieldsRequired")
    return
  }
  saving.value = true
  error.value = ""
  try {
    // Save only fields this editor owns. Concurrent preset edits stay intact.
    const config = await llmApi.saveConfig({ revision: draft.value.revision, profiles: draft.value.profiles, routes: draft.value.routes, cache: draft.value.cache, local_fallback_enabled: draft.value.local_fallback_enabled })
    draft.value = normalize(config)
    committed.value = JSON.stringify(draft.value)
    result.value = t("settings.api.saved")
    emit("saved", config)
    saving.value = false
    if (!props.embedded) close()
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : String(caught)
  } finally {
    saving.value = false
  }
}

async function test(profile: LlmProfile) {
  testing.value = profile.id
  error.value = ""
  result.value = ""
  try {
    await llmApi.connectionTest({ profile_id: profile.id })
    const config = await llmApi.config()
    draft.value = normalize(config)
    committed.value = JSON.stringify(draft.value)
    emit("saved", config)
    const capabilities = config.profiles.find(item => item.id === profile.id)?.verified_capabilities || []
    result.value = t("llm.testCapabilitiesPassed", { name: profile.name, capabilities: capabilities.map(value => t('llm.' + value)).join('、') })
    if (!capabilities.includes("vision")) result.value += ` ${t("llm.visionUnavailable")}`
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : String(caught)
  } finally {
    testing.value = ""
  }
}
</script>

<template>
  <component :is="embedded ? 'div' : ElDialog" :model-value="modelValue" :title="embedded ? undefined : t('llm.title')" width="min(800px, 96vw)" :close-on-click-modal="false" :before-close="close" @update:model-value="(value: boolean) => { if (!value) close() }">
    <div class="llm-settings">
      <p>{{ t("llm.sharedHint") }}</p>
      <p>{{ t("llm.keyHint") }}</p>
      <p v-if="loading" role="status">{{ t("llm.loading") }}</p>
      <p v-if="error" role="alert" class="llm-error">{{ error }}</p>
      <p v-if="result" role="status">{{ result }}</p>
      <fieldset :disabled="!loaded || loading || saving || Boolean(testing) || localBusy">
        <details class="llm-advanced-settings">
          <summary>{{ t("llm.advancedSettings") }}</summary>
          <div class="llm-advanced-fields">
            <label><input v-model="draft.cache.translation" type="checkbox" class="llm-translation-cache" />{{ t("llm.translationCache") }}</label>
            <label><input v-model="draft.cache.caption" type="checkbox" class="llm-caption-cache" />{{ t("llm.captionCache") }}</label>
            <label><input v-model="draft.local_fallback_enabled" type="checkbox" class="llm-local-fallback" />{{ t("llm.localFallback") }}</label>
          </div>
        </details>
        <label>{{ t("llm.translationRoute") }}<select v-model="draft.routes.translation"><option value="">{{ t("llm.auto") }}</option><option v-for="profile in textProfiles" :key="profile.id" :value="profile.id">{{ profile.name }}</option></select></label>
        <label>{{ t("llm.captionRoute") }}<select v-model="draft.routes.caption"><option value="">{{ t("llm.auto") }}</option><option v-for="profile in visionProfiles" :key="profile.id" :value="profile.id">{{ profile.name }}</option></select></label>
        <p v-if="dirty">{{ t("llm.saveBeforeTest") }}</p>
        <details class="llm-profile-card llm-managed-profile" :data-profile-id="managedProfile?.id">
          <summary><strong>{{ managedProfile?.name || t("tagger.caption.localRuntimeTitle") }}</strong><label class="llm-profile-enabled" @click.stop><input v-if="managedProfile" v-model="managedProfile.enabled" type="checkbox" /><input v-else type="checkbox" disabled />{{ t("llm.enabled") }}</label></summary>
          <ManagedVisionModel :status="local" :busy="localBusy" :locked="!loaded || loading || saving || Boolean(testing)" @action="manageLocal" />
        </details>
        <details v-for="profile in editableProfiles" :key="profile.id" class="llm-profile-card" :data-profile-id="profile.id">
          <summary><strong>{{ profile.name || profile.id }}</strong><label class="llm-profile-enabled" @click.stop><input v-model="profile.enabled" type="checkbox" />{{ t("llm.enabled") }}</label></summary>
          <div class="llm-profile-fields">
            <label>{{ t("llm.name") }}<input v-model="profile.name" class="llm-profile-name" /></label>
            <label>{{ t("llm.source") }}<select v-model="profile.source" :disabled="profile.source === 'managed-local'"><option value="remote">{{ t("llm.remote") }}</option><option value="local-endpoint">{{ t("llm.local") }}</option><option v-if="profile.source === 'managed-local'" value="managed-local">{{ t("llm.managed") }}</option></select></label>
            <label>{{ t("llm.endpoint") }}<input v-model="profile.endpoint" :disabled="profile.source === 'managed-local'" placeholder="https://…/chat/completions" /></label>
            <label>{{ t("llm.model") }}<input v-model="profile.model" :disabled="profile.source === 'managed-local'" /></label>
            <label>{{ t("llm.key") }}<input v-model="profile.api_key" type="password" autocomplete="new-password" :disabled="profile.source === 'managed-local'" /></label>
            <label>{{ t("llm.languages") }}<input :value="profile.languages.join(',')" @input="languages(profile, $event)" /></label>
            <label v-if="profile.capabilities.includes('text')">{{ t("llm.reasoning") }}<select class="llm-reasoning" :value="String(profile.metadata?.reasoning_effort ?? 'disabled')" :disabled="profile.source === 'managed-local'" @change="setReasoning(profile, $event)"><option value="disabled">{{ t("llm.reasoningDisabled") }}</option><option value="high">{{ t("llm.reasoningHigh") }}</option><option value="max">{{ t("llm.reasoningMax") }}</option></select></label>
          </div>
          <p v-if="profile.verified_capabilities?.length" class="llm-detected-capabilities">{{ t("llm.capabilitiesDetected", { capabilities: profile.verified_capabilities.map(value => t('llm.' + value)).join('、') }) }}</p>
          <div class="llm-profile-actions">
            <button type="button" :disabled="dirty || !profile.enabled" @click="test(profile)">{{ t("llm.test") }}</button>
            <button type="button" :disabled="profile.source === 'managed-local'" @click="draft.profiles = draft.profiles.filter(item => item.id !== profile.id)">{{ t("llm.remove") }}</button>
          </div>
        </details>
        <button type="button" class="llm-add-profile" @click="add">{{ t("llm.add") }}</button>
      </fieldset>
    </div>
    <div v-if="embedded" class="form-actions"><button type="button" class="primary-action llm-save" :disabled="!loaded || loading || saving || Boolean(testing) || localBusy" @click="save">{{ t("llm.save") }}</button><button type="button" class="secondary-action" :disabled="!loaded || loading || saving || Boolean(testing) || localBusy" @click="reset">{{ t("settings.api.reset") }}</button></div>
    <template v-if="!embedded" #footer><button type="button" class="llm-cancel" :disabled="saving || Boolean(testing) || localBusy" @click="close">{{ t("llm.cancel") }}</button><button type="button" class="primary-action llm-save" :disabled="!loaded || loading || saving || Boolean(testing) || localBusy" @click="save">{{ t("llm.save") }}</button></template>
  </component>
</template>
