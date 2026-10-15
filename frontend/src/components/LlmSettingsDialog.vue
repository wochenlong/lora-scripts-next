<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { ElDialog, ElMessageBox } from "element-plus"
import { useI18n } from "vue-i18n"
import { isVerifiedProfile, llmApi, type LlmConfig, type LlmProfile, type LocalVisionStatus } from "../api/llm"
import ManagedVisionModel from "./ManagedVisionModel.vue"
import { useTagTranslations } from "../composables/useTagTranslations"

const props = defineProps<{ modelValue: boolean; embedded?: boolean }>()
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
const configConflict = ref(false)

function applyCachePolicy(config: LlmConfig) {
  useTagTranslations().configureCache(config.cache.translation !== false, config.revision || JSON.stringify(config.profiles))
}

function publishConfig(config: LlmConfig) {
  applyCachePolicy(config)
  emit("saved", config)
}
let generation = 0
const local = ref<LocalVisionStatus>({ state: "missing", installed: false, downloaded_bytes: 0, total_bytes: 0 })
const localBusy = ref(false)
const runtimeConfigBusy = ref(false)
let synchronizedRuntime = ""
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
    if (revision !== generation) return
    local.value = value
    if (value.state !== "running") synchronizedRuntime = ""
    await syncReadyRuntime(revision)
  } catch (caught) {
    if (!request.signal.aborted && revision === generation) error.value = caught instanceof Error ? caught.message : String(caught)
  } finally {
    if (localRequest === request) localRequest = undefined
  }
}

async function refreshRuntimeConfig(revision: number): Promise<boolean> {
  if (!loaded.value || revision !== generation || runtimeConfigBusy.value || saving.value || testing.value) return false
  runtimeConfigBusy.value = true
  try {
    const config = await llmApi.config()
    if (revision !== generation) return false
    const baseline = JSON.parse(committed.value) as LlmConfig
    const latest = normalize(config)
    const merged = mergeRuntimeConfig(baseline, draft.value, latest)
    if (merged.conflict) {
      // Do not attach a new revision to fields still based on an older snapshot.
      // Keep the complete draft until the user explicitly reloads the server copy.
      configConflict.value = true
      error.value = t("llm.runtimeConfigConflict")
    } else {
      draft.value = merged.config
      committed.value = JSON.stringify(latest)
    }
    publishConfig(config)
    return true
  } finally {
    if (revision === generation) runtimeConfigBusy.value = false
  }
}

async function syncReadyRuntime(revision: number) {
  if (local.value.state !== "running" || localBusy.value || revision !== generation) return
  // Setup returns before the background diagnostics register its Profile.
  // Publish that later registration while retaining the user's live draft.
  const key = JSON.stringify([local.value.model_id, local.value.endpoint, local.value.port])
  if (key === synchronizedRuntime) return
  if (await refreshRuntimeConfig(revision) && revision === generation) synchronizedRuntime = key
}

async function manageLocal(action: "setup" | "start" | "stop" | "cancel") {
  if (localBusy.value || runtimeConfigBusy.value) return
  localBusy.value = true
  error.value = ""
  const revision = generation
  try {
    const status = await llmApi.localVisionAction(action)
    if (revision !== generation) return
    local.value = status
    if (await refreshRuntimeConfig(revision) && revision === generation) {
      synchronizedRuntime = status.state === "running" ? JSON.stringify([status.model_id, status.endpoint, status.port]) : ""
    }
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value))
}

function sameValue(left: unknown, right: unknown): boolean {
  if (left === right) return true
  if (Array.isArray(left) && Array.isArray(right)) return left.length === right.length && left.every((value, index) => sameValue(value, right[index]))
  if (isRecord(left) && isRecord(right)) {
    const keys = Object.keys(left)
    return keys.length === Object.keys(right).length && keys.every(key => Object.hasOwn(right, key) && sameValue(left[key], right[key]))
  }
  return false
}

function mergeRuntimeConfig(baseline: LlmConfig, edited: LlmConfig, latest: LlmConfig): { config: LlmConfig; conflict: boolean } {
  let conflict = false
  function merge(base: unknown, local: unknown, server: unknown): unknown {
    if (sameValue(local, base)) return server
    if (sameValue(server, base) || sameValue(local, server)) return local
    if (isRecord(base) && isRecord(local) && isRecord(server)) {
      const value: Record<string, unknown> = {}
      for (const key of new Set([...Object.keys(base), ...Object.keys(local), ...Object.keys(server)])) {
        const merged = merge(base[key], local[key], server[key])
        if (merged !== undefined) value[key] = merged
      }
      return value
    }
    conflict = true
    return local
  }
  const baseProfiles = new Map(baseline.profiles.map(profile => [profile.id, profile]))
  const localProfiles = new Map(edited.profiles.map(profile => [profile.id, profile]))
  const serverProfiles = new Map(latest.profiles.map(profile => [profile.id, profile]))
  const profiles: LlmProfile[] = []
  for (const id of new Set([...serverProfiles.keys(), ...localProfiles.keys(), ...baseProfiles.keys()])) {
    const base = baseProfiles.get(id)
    const local = localProfiles.get(id)
    const server = serverProfiles.get(id)
    // A masked server key retains its display value when the secret changes.
    // Treat the key input and its server generation as one conflict unit.
    if (base && local && server && local.api_key !== base.api_key &&
      (server.secret_revision ?? 0) !== (base.secret_revision ?? 0)) conflict = true
    const profile = merge(base, local, server) as LlmProfile | undefined
    if (profile) profiles.push(profile)
  }
  const config: LlmConfig = {
    ...latest,
    profiles,
    routes: merge(baseline.routes, edited.routes, latest.routes) as LlmConfig["routes"],
    cache: merge(baseline.cache, edited.cache, latest.cache) as LlmConfig["cache"],
    local_fallback_enabled: merge(baseline.local_fallback_enabled, edited.local_fallback_enabled, latest.local_fallback_enabled) as boolean,
  }
  return { config: normalize(config), conflict }
}

async function reloadConfig() {
  const revision = generation
  try {
    await ElMessageBox.confirm(t("llm.runtimeConfigConflict"), { confirmButtonText: t("llm.reloadConfig"), cancelButtonText: t("llm.cancel"), type: "warning" })
  } catch { return }
  if (revision !== generation || !props.modelValue) return
  loading.value = true
  try {
    const config = await llmApi.config()
    if (revision !== generation) return
    draft.value = normalize(config)
    committed.value = JSON.stringify(draft.value)
    configConflict.value = false
    error.value = ""
    result.value = ""
    publishConfig(config)
  } catch (caught) {
    if (revision === generation) error.value = caught instanceof Error ? caught.message : String(caught)
  } finally {
    if (revision === generation) loading.value = false
  }
}

watch(() => props.modelValue, async open => {
  const revision = ++generation
  stopMonitoring()
  loaded.value = false
  runtimeConfigBusy.value = false
  synchronizedRuntime = ""
  error.value = ""
  result.value = ""
  configConflict.value = false
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
    applyCachePolicy(config)
    draft.value = normalize(config)
    committed.value = JSON.stringify(draft.value)
    loaded.value = true
    await syncReadyRuntime(revision)
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
  if (!loaded.value || configConflict.value || runtimeConfigBusy.value) return
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
    publishConfig(config)
    saving.value = false
    if (!props.embedded) close()
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : String(caught)
  } finally {
    saving.value = false
  }
}

async function test(profile: LlmProfile) {
  if (runtimeConfigBusy.value) return
  testing.value = profile.id
  error.value = ""
  result.value = ""
  try {
    await llmApi.connectionTest({ profile_id: profile.id })
    const config = await llmApi.config()
    draft.value = normalize(config)
    committed.value = JSON.stringify(draft.value)
    publishConfig(config)
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
      <button v-if="configConflict" type="button" class="llm-reload-config" :disabled="loading || saving || Boolean(testing) || localBusy || runtimeConfigBusy" @click="reloadConfig">{{ t("llm.reloadConfig") }}</button>
      <fieldset :disabled="!loaded || loading || saving || Boolean(testing) || localBusy || configConflict">
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
          <ManagedVisionModel :status="local" :busy="localBusy" :locked="!loaded || loading || saving || Boolean(testing) || runtimeConfigBusy" @action="manageLocal" />
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
            <button type="button" :disabled="dirty || !profile.enabled || runtimeConfigBusy" @click="test(profile)">{{ t("llm.test") }}</button>
            <button type="button" :disabled="profile.source === 'managed-local'" @click="draft.profiles = draft.profiles.filter(item => item.id !== profile.id)">{{ t("llm.remove") }}</button>
          </div>
        </details>
        <button type="button" class="llm-add-profile" @click="add">{{ t("llm.add") }}</button>
      </fieldset>
    </div>
    <div v-if="embedded" class="form-actions"><button type="button" class="primary-action llm-save" :disabled="!loaded || loading || saving || Boolean(testing) || localBusy || runtimeConfigBusy || configConflict" @click="save">{{ t("llm.save") }}</button><button type="button" class="secondary-action" :disabled="!loaded || loading || saving || Boolean(testing) || localBusy || runtimeConfigBusy || configConflict" @click="reset">{{ t("settings.api.reset") }}</button></div>
    <template v-if="!embedded" #footer><button type="button" class="llm-cancel" :disabled="saving || Boolean(testing) || localBusy" @click="close">{{ t("llm.cancel") }}</button><button type="button" class="primary-action llm-save" :disabled="!loaded || loading || saving || Boolean(testing) || localBusy || runtimeConfigBusy || configConflict" @click="save">{{ t("llm.save") }}</button></template>
  </component>
</template>
