<script setup lang="ts">
import { ref, watch } from "vue"
import { useI18n } from "vue-i18n"
import { ElButton, ElDialog, ElInput } from "element-plus"
import type { LocalModelStatus, LlmProfile, TagDictionaryStatus } from "../../api/dataset"

const props = defineProps<{
  modelValue: boolean
  loading: boolean
  saving: boolean
  error: string
  profiles: LlmProfile[]
  activeRemoteId: string
  llmMode: "remote" | "local"
  cacheCount: number
  clearingCache: boolean
  dictionary: TagDictionaryStatus
  dictionaryBusy: boolean
  localModel: LocalModelStatus
  localModelBusy: boolean
  remoteConfigured: boolean
}>()

const emit = defineEmits<{
  "update:modelValue": [value: boolean]
  "update:profiles": [value: LlmProfile[]]
  "update:active-remote-id": [value: string]
  "update:llm-mode": [value: "remote" | "local"]
  save: []
  clearCache: []
  checkDictionary: []
  updateDictionary: []
  retryDictionary: []
  cancelDictionary: []
  setupLocalModel: []
  cancelLocalModel: []
  startLocalModel: []
  stopLocalModel: []
  useRemoteMode: []
}>()

const { t } = useI18n()
const expandedProfiles = ref(new Set<string>())

watch(() => [props.activeRemoteId, ...props.profiles.map((profile) => profile.id)], () => {
  const next = new Set(expandedProfiles.value)
  if (props.activeRemoteId) next.add(props.activeRemoteId)
  expandedProfiles.value = next
}, { immediate: true })

function updateProfile(id: string, patch: Partial<LlmProfile>) {
  emit("update:profiles", props.profiles.map((profile) => {
    if (profile.id !== id) return profile
    const next = { ...profile, ...patch }
    if ("api_key" in patch && patch.api_key !== "********") next.api_key_configured = Boolean(patch.api_key)
    return next
  }))
}

function addProfile() {
  const id = "remote-" + Date.now()
  const profile: LlmProfile = {
    id,
    name: t("datasetEditor.caption.translationProfileNew"),
    endpoint: "https://api.example.com/v1/chat/completions",
    model: "",
    api_key: "",
    reasoning_effort: "disabled",
  }
  emit("update:profiles", [...props.profiles, profile])
  emit("update:active-remote-id", id)
  emit("update:llm-mode", "remote")
  expandedProfiles.value = new Set([...expandedProfiles.value, id])
}

function removeProfile(id: string) {
  if (props.profiles.length <= 1) return
  const next = props.profiles.filter((profile) => profile.id !== id)
  emit("update:profiles", next)
  if (props.activeRemoteId === id) emit("update:active-remote-id", next[0].id)
  const expanded = new Set(expandedProfiles.value)
  expanded.delete(id)
  expandedProfiles.value = expanded
}

function toggleProfile(id: string) {
  const next = new Set(expandedProfiles.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedProfiles.value = next
}

function activateProfile(id: string) {
  emit("update:active-remote-id", id)
  expandedProfiles.value = new Set([...expandedProfiles.value, id])
}
</script>

<template>
  <el-dialog :model-value="modelValue" :title="t('datasetEditor.caption.translationSettingsTitle')" width="min(720px, 94vw)" @update:model-value="emit('update:modelValue', $event)">
    <div class="caption-translation-dialog">
      <p class="caption-translation-dialog-hint">{{ t("datasetEditor.caption.translationSettingsHint") }}</p>
      <section class="translation-settings-section">
        <div class="translation-settings-section-heading"><strong>{{ t("datasetEditor.caption.translationDictionaryTitle") }}</strong><span>{{ dictionary.row_count || 0 }} {{ t("datasetEditor.caption.translationDictionaryRows") }}</span></div>
        <p class="caption-translation-dialog-hint">{{ dictionary.installed ? t("datasetEditor.caption.translationDictionaryReady") : t("datasetEditor.caption.translationDictionaryMissing") }}</p>
        <small v-if="dictionary.state === 'ready' && dictionary.update_available" class="caption-translation-update">{{ t("datasetEditor.caption.translationDictionaryUpdateAvailable") }}</small>
        <small v-else-if="dictionary.state === 'ready' && dictionary.last_checked_at" class="caption-translation-ok">{{ t("datasetEditor.caption.translationDictionaryUpToDate") }}</small>
        <small v-if="dictionary.error" class="caption-translation-error">{{ dictionary.error }}</small>
        <div class="caption-translation-cache-row">
          <span>{{ dictionary.state }}<template v-if="dictionary.downloaded_bytes"> · {{ dictionary.downloaded_bytes }}/{{ dictionary.total_bytes || "?" }}</template></span>
          <span class="translation-settings-actions">
            <el-button :loading="dictionaryBusy" @click="emit('checkDictionary')">{{ t("datasetEditor.caption.translationDictionaryCheck") }}</el-button>
            <el-button v-if="dictionary.installed" :loading="dictionaryBusy" :disabled="dictionary.update_available !== true || dictionary.state === 'checking'" @click="emit('updateDictionary')">{{ t("datasetEditor.caption.translationDictionaryUpdate") }}</el-button>
            <el-button v-else :loading="dictionaryBusy" @click="emit('retryDictionary')">{{ t("datasetEditor.caption.translationDictionaryRetry") }}</el-button>
            <el-button v-if="dictionary.state === 'downloading'" :loading="dictionaryBusy" @click="emit('cancelDictionary')">{{ t("datasetEditor.caption.translationDictionaryCancel") }}</el-button>
          </span>
        </div>
      </section>
      <section class="translation-settings-section">
        <div class="translation-settings-section-heading"><strong>{{ t("datasetEditor.caption.translationLlmTitle") }}</strong><span>{{ llmMode === "local" ? t("datasetEditor.caption.translationLocalMode") : t("datasetEditor.caption.translationRemoteMode") }}</span></div>
        <div class="translation-mode-tabs" role="tablist">
          <button type="button" :class="{ active: llmMode === 'remote' }" :disabled="saving" @click="emit('update:llm-mode', 'remote')">{{ t("datasetEditor.caption.translationRemoteMode") }}</button>
          <button type="button" :class="{ active: llmMode === 'local' }" :disabled="saving" @click="emit('update:llm-mode', 'local')">{{ t("datasetEditor.caption.translationLocalMode") }}</button>
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
            <p v-if="localModel.state !== 'running'" class="translation-runtime-warning">
              {{ t("datasetEditor.caption.translationLocalUnavailable") }}
              <el-button size="small" @click="emit('useRemoteMode')">{{ t("datasetEditor.caption.translationRemoteMode") }}</el-button>
            </p>
            <div class="caption-translation-cache-row">
              <span>{{ localModel.state }}<template v-if="localModel.downloaded_bytes"> · {{ localModel.downloaded_bytes }}/{{ localModel.total_bytes || "?" }}</template></span>
              <span class="translation-settings-actions">
                <el-button v-if="localModel.state === 'installing' || localModel.state === 'downloading'" :loading="localModelBusy" @click="emit('cancelLocalModel')">{{ t("datasetEditor.caption.translationLocalCancel") }}</el-button>
                <el-button v-else-if="!localModel.installed || localModel.runtime_state !== 'ready'" :loading="localModelBusy" @click="emit('setupLocalModel')">{{ t("datasetEditor.caption.translationLocalSetup") }}</el-button>
                <el-button v-else-if="localModel.state === 'running'" :loading="localModelBusy" @click="emit('stopLocalModel')">{{ t("datasetEditor.caption.translationLocalStop") }}</el-button>
                <el-button v-else :loading="localModelBusy" @click="emit('startLocalModel')">{{ t("datasetEditor.caption.translationLocalStart") }}</el-button>
              </span>
            </div>
            <small class="caption-translation-dialog-hint">{{ t("datasetEditor.caption.translationLocalMutuallyExclusive") }}</small>
          </article>
        </div>
      </section>
      <small v-if="loading">{{ t("datasetEditor.caption.translationLoading") }}</small>
      <small v-if="error" class="caption-translation-error">{{ error }}</small>
      <div class="caption-translation-cache-row">
        <span>{{ t("datasetEditor.caption.translationCache", { n: cacheCount }) }}</span>
        <el-button :loading="clearingCache" @click="emit('clearCache')">{{ clearingCache ? t("datasetEditor.caption.translationCacheClearing") : t("datasetEditor.caption.translationCacheClear") }}</el-button>
      </div>
    </div>
    <template #footer>
      <el-button :disabled="saving" @click="emit('update:modelValue', false)">{{ t("datasetEditor.caption.translationCancel") }}</el-button>
      <el-button type="primary" :loading="saving" :disabled="loading || (llmMode === 'local' && localModel.state !== 'running')" @click="emit('save')">{{ t("datasetEditor.caption.translationSave") }}</el-button>
    </template>
  </el-dialog>
</template>
