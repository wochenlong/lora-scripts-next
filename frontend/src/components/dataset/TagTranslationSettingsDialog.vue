<script setup lang="ts">
import { ref, watch } from "vue"
import { useI18n } from "vue-i18n"
import { ElButton, ElDialog } from "element-plus"
import LlmSettingsDialog from "../LlmSettingsDialog.vue"
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
  sharedLocalReady: boolean
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
  sharedSaved: []
}>()

const { t } = useI18n()
const sharedOpen = ref(false)
watch(() => props.modelValue, open => { if (!open) sharedOpen.value = false })
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
        <p>{{ t("llm.sharedHint") }}</p>
        <label class="translation-fallback"><input type="checkbox" :checked="llmMode === 'local'" :disabled="saving" @change="emit('update:llm-mode', ($event.target as HTMLInputElement).checked ? 'local' : 'remote')" />{{ t("llm.localFallback") }}</label>
        <button type="button" class="translation-profile-add" :disabled="saving" @click="sharedOpen = true">{{ t("llm.title") }}</button>
        <div v-if="llmMode === 'local'" class="translation-profile-list">
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
              <el-button size="small" @click="emit('useRemoteMode')">{{ t("datasetEditor.caption.translationRemoteMode") }}</el-button>
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
                <el-button v-if="localModel.state === 'installing' || localModel.state === 'downloading' || localModel.runtime_state === 'installing'" :loading="localModelBusy" @click="emit('cancelLocalModel')">{{ t("datasetEditor.caption.translationLocalCancel") }}</el-button>
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
      <el-button type="primary" :loading="saving" :disabled="loading || (llmMode === 'local' && localModel.state !== 'running' && !sharedLocalReady && !remoteConfigured)" @click="emit('save')">{{ t("datasetEditor.caption.translationSave") }}</el-button>
    </template>
  </el-dialog>
  <LlmSettingsDialog v-model="sharedOpen" capability="text" @saved="emit('sharedSaved')" />
</template>
