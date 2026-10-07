<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { ElDialog } from "element-plus"
import { useI18n } from "vue-i18n"
import { llmApi, type LlmConfig, type LlmProfile, type LocalVisionStatus } from "../api/llm"
import ManagedVisionModel from "./ManagedVisionModel.vue"

const props = defineProps<{ modelValue: boolean; capability: "text" | "vision"; imagePath?: string }>()
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
const testImage = ref("")
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
    const config = await llmApi.config()
    if (revision !== generation) return
    // Runtime actions own managed assets only; preserve all unsaved user inputs.
    const managed = config.profiles.filter(profile => profile.asset_id === "qwen3-vl-2b-local")
    draft.value.profiles = [...draft.value.profiles.filter(profile => profile.asset_id !== "qwen3-vl-2b-local"), ...managed]
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
const textProfiles = computed(() => profiles.value.filter(profile => profile.enabled && profile.capabilities.includes("text")))
const visionProfiles = computed(() => profiles.value.filter(profile => profile.enabled && profile.capabilities.includes("vision")))

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
  testImage.value = props.imagePath || ""
  try {
    const config = await llmApi.config()
    if (revision !== generation) return
    draft.value = JSON.parse(JSON.stringify(config))
    draft.value.cache = { translation: true, caption: true, ...config.cache }
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
    source: "remote", capabilities: props.capability === "vision" ? ["text", "vision"] : ["text"],
    languages: ["zh-CN", "en"], api_key: "", enabled: true, ready: true })
}

function setCapability(profile: LlmProfile, value: string, selected: boolean) {
  profile.capabilities = selected ? [...new Set([...profile.capabilities, value])] : profile.capabilities.filter(item => item !== value)
}

function languages(profile: LlmProfile, event: Event) {
  profile.languages = (event.target as HTMLInputElement).value.split(",").map(item => item.trim()).filter(Boolean)
}

function setTranslationOption(profile: LlmProfile, key: "translation_system_prompt" | "reasoning_effort", event: Event) {
  profile.metadata = { ...profile.metadata, [key]: (event.target as HTMLInputElement).value }
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
    const config = await llmApi.saveConfig({ profiles: draft.value.profiles, routes: draft.value.routes, cache: draft.value.cache })
    draft.value = JSON.parse(JSON.stringify(config))
    draft.value.cache = { translation: true, caption: true, ...config.cache }
    committed.value = JSON.stringify(draft.value)
    emit("saved", config)
    saving.value = false
    close()
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
    await llmApi.connectionTest({ capability: props.capability, profile_id: profile.id,
      ...(props.capability === "vision" ? { image_path: testImage.value } : {}) })
    result.value = t("llm.testPassed", { name: profile.name })
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : String(caught)
  } finally {
    testing.value = ""
  }
}
</script>

<template>
  <ElDialog :model-value="modelValue" :title="t('llm.title')" width="min(800px, 96vw)" :close-on-click-modal="false" :before-close="close" @update:model-value="value => { if (!value) close() }">
    <div class="llm-settings">
      <p>{{ t("llm.sharedHint") }}</p>
      <p>{{ t("llm.keyHint") }}</p>
      <p v-if="loading" role="status">{{ t("llm.loading") }}</p>
      <p v-if="error" role="alert" class="llm-error">{{ error }}</p>
      <p v-if="result" role="status">{{ result }}</p>
      <ManagedVisionModel :status="local" :busy="localBusy" :locked="!loaded || loading || saving || Boolean(testing)" @action="manageLocal" />
      <fieldset :disabled="!loaded || loading || saving || Boolean(testing) || localBusy">
        <label><input v-model="draft.cache.translation" type="checkbox" />{{ t("llm.translationCache") }}</label>
        <label><input v-model="draft.cache.caption" type="checkbox" />{{ t("llm.captionCache") }}</label>
        <label>{{ t("llm.translationRoute") }}<select v-model="draft.routes.translation"><option value="">{{ t("llm.auto") }}</option><option v-for="profile in textProfiles" :key="profile.id" :value="profile.id">{{ profile.name }}</option></select></label>
        <label>{{ t("llm.captionRoute") }}<select v-model="draft.routes.caption"><option value="">{{ t("llm.auto") }}</option><option v-for="profile in visionProfiles" :key="profile.id" :value="profile.id">{{ profile.name }}</option></select></label>
        <label v-if="capability === 'vision'">{{ t("llm.testImage") }}<input v-model="testImage" class="llm-test-image" /></label>
        <p v-if="dirty">{{ t("llm.saveBeforeTest") }}</p>
        <article v-for="profile in profiles" :key="profile.id" class="llm-profile-card" :data-profile-id="profile.id">
          <header><strong>{{ profile.name || profile.id }}</strong><span>{{ profile.source === 'remote' ? t("llm.remote") : t("llm.local") }}</span></header>
          <div class="llm-profile-fields">
            <label>{{ t("llm.name") }}<input v-model="profile.name" class="llm-profile-name" /></label>
            <label>{{ t("llm.source") }}<select v-model="profile.source" :disabled="profile.source === 'managed-local'"><option value="remote">{{ t("llm.remote") }}</option><option value="local-endpoint">{{ t("llm.local") }}</option><option v-if="profile.source === 'managed-local'" value="managed-local">{{ t("llm.managed") }}</option></select></label>
            <label>{{ t("llm.endpoint") }}<input v-model="profile.endpoint" :disabled="profile.source === 'managed-local'" placeholder="https://…/chat/completions" /></label>
            <label>{{ t("llm.model") }}<input v-model="profile.model" :disabled="profile.source === 'managed-local'" /></label>
            <label>{{ t("llm.key") }}<input v-model="profile.api_key" type="password" autocomplete="new-password" :disabled="profile.source === 'managed-local'" /></label>
            <label>{{ t("llm.languages") }}<input :value="profile.languages.join(',')" @input="languages(profile, $event)" /></label>
            <label v-if="profile.capabilities.includes('text')">{{ t("llm.reasoning") }}<select class="llm-reasoning" :value="String(profile.metadata?.reasoning_effort ?? 'disabled')" :disabled="profile.source === 'managed-local'" @change="setTranslationOption(profile, 'reasoning_effort', $event)"><option value="disabled">{{ t("llm.reasoningDisabled") }}</option><option value="high">{{ t("llm.reasoningHigh") }}</option><option value="max">{{ t("llm.reasoningMax") }}</option></select></label>
          </div>
          <label v-if="profile.capabilities.includes('text')">{{ t("llm.translationPrompt") }}<textarea class="llm-translation-prompt" rows="4" maxlength="20000" :value="String(profile.metadata?.translation_system_prompt ?? '')" @input="setTranslationOption(profile, 'translation_system_prompt', $event)" /></label>
          <div class="llm-capabilities">
            <label><input type="checkbox" :checked="profile.capabilities.includes('text')" :disabled="profile.source === 'managed-local'" @change="setCapability(profile, 'text', ($event.target as HTMLInputElement).checked)" />{{ t("llm.text") }}</label>
            <label><input type="checkbox" :checked="profile.capabilities.includes('vision')" :disabled="profile.source === 'managed-local'" @change="setCapability(profile, 'vision', ($event.target as HTMLInputElement).checked)" />{{ t("llm.vision") }}</label>
            <label><input v-model="profile.enabled" type="checkbox" />{{ t("llm.enabled") }}</label>
          </div>
          <div class="llm-profile-actions">
            <button type="button" :disabled="dirty || !profile.enabled || !profile.ready || !profile.capabilities.includes(capability) || (capability === 'vision' && !testImage)" @click="test(profile)">{{ t("llm.test") }}</button>
            <button type="button" :disabled="profile.source === 'managed-local'" @click="draft.profiles = draft.profiles.filter(item => item.id !== profile.id)">{{ t("llm.remove") }}</button>
          </div>
        </article>
        <button type="button" class="llm-add-profile" @click="add">{{ t("llm.add") }}</button>
      </fieldset>
    </div>
    <template #footer><button type="button" class="llm-cancel" :disabled="saving || Boolean(testing) || localBusy" @click="close">{{ t("llm.cancel") }}</button><button type="button" class="primary-action llm-save" :disabled="!loaded || loading || saving || Boolean(testing) || localBusy" @click="save">{{ t("llm.save") }}</button></template>
  </ElDialog>
</template>
