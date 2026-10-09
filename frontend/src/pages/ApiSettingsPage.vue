<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { ElButton, ElInput, ElMessage } from "element-plus"
import { useI18n } from "vue-i18n"
import { datasetApi, type LlmProfile, type LocalModelStatus } from "../api/dataset"
import { useTagTranslations } from "../composables/useTagTranslations"

/**
 * Global API settings: LLM/API profiles (endpoint, model, key) and the managed
 * local model runtime. Translation (and later API tagging) only pick a source;
 * credentials live here so every feature shares one configuration.
 */

const { t } = useI18n()
const loading = ref(false)
const saving = ref(false)
const error = ref("")
const profiles = ref<LlmProfile[]>([])
const activeRemoteId = ref("default")
const llmMode = ref<"remote" | "local">("remote")
const committedProfiles = ref<LlmProfile[]>([])
const committedActiveRemoteId = ref("default")
const committedLlmMode = ref<"remote" | "local">("remote")
const cacheCount = ref(0)
const clearingCache = ref(false)
const expandedProfiles = ref(new Set<string>())
const localModel = ref<LocalModelStatus>({
  state: "missing", model_id: "", model_filename: "", model_url: "", model_path: "",
  installed: false, size_bytes: 0, downloaded_bytes: 0, total_bytes: 0,
  runtime_path: "", endpoint: "internal://dataset-translation", port: 0, error: null,
})
const localModelBusy = ref(false)
let poll: ReturnType<typeof setTimeout> | undefined

const activeProfile = computed(() => profiles.value.find((profile) => profile.id === activeRemoteId.value))
const remoteConfigured = computed(() => {
  const profile = activeProfile.value
  if (!profile) return false
  const endpoint = profile.endpoint.trim().toLowerCase()
  return Boolean(profile.api_key_configured || /^http:\/\/(127\.0\.0\.1|localhost|\[::1\])(?::\d+)?\//.test(endpoint))
})

function cloneProfiles(list: LlmProfile[]): LlmProfile[] {
  return list.map((profile) => ({ ...profile }))
}

function snapshot() {
  committedProfiles.value = cloneProfiles(profiles.value)
  committedActiveRemoteId.value = activeRemoteId.value
  committedLlmMode.value = llmMode.value
}

function restore() {
  profiles.value = cloneProfiles(committedProfiles.value)
  activeRemoteId.value = committedActiveRemoteId.value
  llmMode.value = committedLlmMode.value
}

function toggleProfile(id: string) {
  const next = new Set(expandedProfiles.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedProfiles.value = next
}

function activateProfile(id: string) {
  activeRemoteId.value = id
}

function updateProfile(id: string, patch: Partial<LlmProfile>) {
  profiles.value = profiles.value.map((profile) => {
    if (profile.id !== id) return profile
    const next = { ...profile, ...patch }
    if ("api_key" in patch && patch.api_key !== "********") next.api_key_configured = Boolean(patch.api_key)
    return next
  })
}

function removeProfile(id: string) {
  profiles.value = profiles.value.filter((profile) => profile.id !== id)
  if (activeRemoteId.value === id) activeRemoteId.value = profiles.value[0]?.id ?? "default"
}

function addProfile() {
  const id = `profile-${Date.now().toString(36)}`
  profiles.value = [
    ...profiles.value,
    {
      id,
      name: t("datasetEditor.caption.translationProfileNew"),
      endpoint: "",
      model: "",
      api_key: "",
      api_key_configured: false,
    },
  ]
  activeRemoteId.value = id
  toggleProfile(id)
}

async function loadCacheCount() {
  try {
    cacheCount.value = (await datasetApi.tagTranslationCache()).total
  } catch {
    cacheCount.value = 0
  }
}

async function loadLocalModel() {
  try {
    localModel.value = await datasetApi.localModelStatus()
  } catch (caught) {
    localModel.value = { ...localModel.value, state: "error", error: caught instanceof Error ? caught.message : String(caught) }
  }
}

function schedulePoll() {
  if (poll) clearTimeout(poll)
  const state = localModel.value.state
  if (state !== "downloading" && state !== "installing" && localModel.value.runtime_state !== "installing") return
  poll = setTimeout(async () => {
    await loadLocalModel()
    schedulePoll()
  }, 1000)
}

async function load() {
  loading.value = true
  error.value = ""
  try {
    const config = await datasetApi.tagTranslationConfig()
    profiles.value = config.remote_profiles?.length
      ? config.remote_profiles
      : [{ ...config.deepseek, id: "default", name: t("datasetEditor.caption.translationProfileNew") }]
    activeRemoteId.value = config.active_remote_id || profiles.value[0]?.id || "default"
    llmMode.value = config.llm_mode || (config.local?.enabled ? "local" : "remote")
    expandedProfiles.value = new Set(activeRemoteId.value ? [activeRemoteId.value] : [])
    snapshot()
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : String(caught)
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  error.value = ""
  try {
    await datasetApi.saveTagTranslationConfig({
      llm_mode: llmMode.value,
      active_remote_id: activeRemoteId.value,
      remote_profiles: profiles.value,
      local: { enabled: llmMode.value === "local" },
    })
    snapshot()
    ElMessage.success(t("settings.api.saved"))
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : String(caught)
    restore()
  } finally {
    saving.value = false
  }
}

async function clearCache() {
  clearingCache.value = true
  try {
    await datasetApi.clearTagTranslationCache()
    // The editor's translations are cached in this module-scoped composable;
    // clearing only the server cache would keep showing stale text.
    useTagTranslations().clearCache()
    cacheCount.value = 0
    ElMessage.success(t("settings.api.cacheCleared"))
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : String(caught)
  } finally {
    clearingCache.value = false
  }
}

async function setupLocalModel() {
  localModelBusy.value = true
  try { localModel.value = await datasetApi.setupLocalModel(); schedulePoll() }
  catch (caught) { error.value = caught instanceof Error ? caught.message : String(caught) }
  finally { localModelBusy.value = false }
}

async function cancelLocalModel() {
  localModelBusy.value = true
  try { localModel.value = await datasetApi.cancelLocalModel() }
  catch (caught) { error.value = caught instanceof Error ? caught.message : String(caught) }
  finally { localModelBusy.value = false }
}

async function startLocalModel() {
  localModelBusy.value = true
  try { localModel.value = await datasetApi.startLocalModel() }
  catch (caught) { error.value = caught instanceof Error ? caught.message : String(caught) }
  finally { localModelBusy.value = false }
}

async function stopLocalModel() {
  localModelBusy.value = true
  try { localModel.value = await datasetApi.stopLocalModel() }
  catch (caught) { error.value = caught instanceof Error ? caught.message : String(caught) }
  finally { localModelBusy.value = false }
}

onMounted(() => {
  void load()
  void loadCacheCount()
  void loadLocalModel()
})
onBeforeUnmount(() => { if (poll) clearTimeout(poll) })
</script>

<template>
  <section class="settings-card">
    <h2>{{ t("settings.api.title") }}</h2>
    <small>{{ t("settings.api.hint") }}</small>
    <small v-if="loading">{{ t("datasetEditor.caption.translationLoading") }}</small>
    <small v-if="error" class="caption-translation-error">{{ error }}</small>

    <div class="translation-mode-tabs" role="tablist">
      <button type="button" :class="{ active: llmMode === 'remote' }" :disabled="saving" @click="llmMode = 'remote'">{{ t("datasetEditor.caption.translationRemoteMode") }}</button>
      <button type="button" :class="{ active: llmMode === 'local' }" :disabled="saving" @click="llmMode = 'local'">{{ t("datasetEditor.caption.translationLocalMode") }}</button>
    </div>

    <div v-if="llmMode === 'remote'" class="translation-profile-list">
      <p v-if="!remoteConfigured" class="translation-runtime-warning">{{ t("datasetEditor.caption.translationRemoteNotConfigured") }}</p>
      <article v-for="profile in profiles" :key="profile.id" class="translation-llm-card" :class="{ active: profile.id === activeRemoteId, collapsed: !expandedProfiles.has(profile.id) }">
        <header class="translation-llm-card-header">
          <button type="button" class="translation-profile-summary" @click="toggleProfile(profile.id)">
            <strong>{{ profile.name }}</strong>
            <small>{{ profile.model || t("datasetEditor.caption.translationModelPlaceholder") }}</small>
          </button>
          <div class="translation-profile-actions">
            <el-button v-if="profile.id !== activeRemoteId" size="small" @click="activateProfile(profile.id)">{{ t("datasetEditor.caption.translationProfileEnable") }}</el-button>
            <span v-else class="translation-profile-active">{{ t("datasetEditor.caption.translationProfileActive") }}</span>
            <el-button v-if="profiles.length > 1" size="small" text type="danger" @click="removeProfile(profile.id)">{{ t("datasetEditor.caption.translationProfileRemove") }}</el-button>
            <el-button size="small" text @click="toggleProfile(profile.id)">{{ expandedProfiles.has(profile.id) ? t("datasetEditor.caption.translationProfileCollapse") : t("datasetEditor.caption.translationProfileExpand") }}</el-button>
          </div>
        </header>
        <div v-if="expandedProfiles.has(profile.id)" class="translation-profile-fields">
          <label class="schema-field"><span class="field-label">{{ t("datasetEditor.caption.translationProfileName") }}</span><el-input :model-value="profile.name" @update:model-value="updateProfile(profile.id, { name: $event })" /></label>
          <label class="schema-field"><span class="field-label">{{ t("datasetEditor.caption.translationEndpoint") }}</span><el-input :model-value="profile.endpoint" :placeholder="t('datasetEditor.caption.translationEndpointPlaceholder')" @update:model-value="updateProfile(profile.id, { endpoint: $event })" /></label>
          <label class="schema-field"><span class="field-label">{{ t("datasetEditor.caption.translationModel") }}</span><el-input :model-value="profile.model" :placeholder="t('datasetEditor.caption.translationModelPlaceholder')" @update:model-value="updateProfile(profile.id, { model: $event })" /></label>
          <label class="schema-field"><span class="field-label">{{ t("datasetEditor.caption.translationKey") }}</span><el-input :model-value="profile.api_key" type="password" show-password autocomplete="new-password" :placeholder="t('datasetEditor.caption.translationKeyPlaceholder')" @update:model-value="updateProfile(profile.id, { api_key: $event })" /></label>
        </div>
      </article>
      <el-button class="translation-profile-add" @click="addProfile">{{ t("datasetEditor.caption.translationProfileAdd") }}</el-button>
    </div>

    <div v-else class="translation-profile-list">
      <article class="translation-llm-card active">
        <header class="translation-llm-card-header"><strong>{{ t("datasetEditor.caption.translationLocalModelTitle") }}</strong><span class="translation-profile-active">{{ localModel.model_id }}</span></header>
        <p class="caption-translation-dialog-hint">{{ t("datasetEditor.caption.translationLocalModelHint") }}</p>
        <p class="translation-runtime-managed">{{ t("datasetEditor.caption.translationManagedRuntime") }}</p>
        <small v-if="localModel.error" class="caption-translation-error">{{ localModel.error }}</small>
        <p v-if="localModel.runtime_state === 'installing'" class="translation-runtime-warning">
          {{ t("datasetEditor.caption.translationLocalRuntimeInstalling") }}
        </p>
        <p v-else-if="localModel.state !== 'running'" class="translation-runtime-warning">
          {{ t("datasetEditor.caption.translationLocalUnavailable") }}
          <el-button size="small" @click="llmMode = 'remote'">{{ t("datasetEditor.caption.translationRemoteMode") }}</el-button>
        </p>
        <div class="caption-translation-cache-row">
          <span>
            <template v-if="localModel.runtime_state === 'installing'">
              {{ t("datasetEditor.caption.translationLocalRuntimeInstalling") }}
              <template v-if="localModel.runtime_downloaded_bytes"> · {{ localModel.runtime_downloaded_bytes }}/{{ localModel.runtime_total_bytes || "?" }}</template>
            </template>
            <template v-else>
              {{ localModel.state }}<template v-if="localModel.downloaded_bytes"> · {{ localModel.downloaded_bytes }}/{{ localModel.total_bytes || "?" }}</template>
            </template>
          </span>
          <span class="translation-settings-actions">
            <el-button v-if="localModel.state === 'installing' || localModel.state === 'downloading' || localModel.runtime_state === 'installing'" :loading="localModelBusy" @click="cancelLocalModel">{{ t("datasetEditor.caption.translationLocalCancel") }}</el-button>
            <el-button v-else-if="!localModel.installed || localModel.runtime_state !== 'ready'" :loading="localModelBusy" @click="setupLocalModel">{{ t("datasetEditor.caption.translationLocalSetup") }}</el-button>
            <el-button v-else-if="localModel.state === 'running'" :loading="localModelBusy" @click="stopLocalModel">{{ t("datasetEditor.caption.translationLocalStop") }}</el-button>
            <el-button v-else :loading="localModelBusy" @click="startLocalModel">{{ t("datasetEditor.caption.translationLocalStart") }}</el-button>
          </span>
        </div>
        <small class="caption-translation-dialog-hint">{{ t("datasetEditor.caption.translationLocalMutuallyExclusive") }}</small>
      </article>
    </div>

    <div class="caption-translation-cache-row">
      <span>{{ t("datasetEditor.caption.translationCache", { n: cacheCount }) }}</span>
      <el-button :loading="clearingCache" @click="clearCache">{{ clearingCache ? t("datasetEditor.caption.translationCacheClearing") : t("datasetEditor.caption.translationCacheClear") }}</el-button>
    </div>

    <div class="form-actions">
      <button class="primary-action" data-testid="api-settings-save" :disabled="saving" @click="save">{{ t("settings.api.save") }}</button>
      <button class="secondary-action" data-testid="api-settings-reset" :disabled="saving" @click="restore">{{ t("settings.api.reset") }}</button>
    </div>
  </section>
</template>
