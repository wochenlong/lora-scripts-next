<script setup lang="ts">
import { useI18n } from "vue-i18n"
import { ElButton, ElDialog, ElInput } from "element-plus"
import type { LocalModelStatus, TagDictionaryStatus } from "../../api/dataset"

defineProps<{
  modelValue: boolean
  loading: boolean
  saving: boolean
  error: string
  endpoint: string
  model: string
  apiKey: string
  cacheCount: number
  clearingCache: boolean
  dictionary: TagDictionaryStatus
  dictionaryBusy: boolean
  localModel: LocalModelStatus
  localModelBusy: boolean
  localEnabled: boolean
  localEndpoint: string
  localRuntimePath: string
}>()

const emit = defineEmits<{
  "update:modelValue": [value: boolean]
  "update:endpoint": [value: string]
  "update:model": [value: string]
  "update:apiKey": [value: string]
  save: []
  clearCache: []
  checkDictionary: []
  updateDictionary: []
  retryDictionary: []
  cancelDictionary: []
  installLocalModel: []
  cancelLocalModel: []
  startLocalModel: []
  stopLocalModel: []
  "update:local-enabled": [value: boolean]
  "update:local-endpoint": [value: string]
  "update:local-runtime-path": [value: string]
}>()

const { t } = useI18n()
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :title="t('datasetEditor.caption.translationSettingsTitle')"
    width="min(640px, 94vw)"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="caption-translation-dialog">
      <p class="caption-translation-dialog-hint">{{ t("datasetEditor.caption.translationSettingsHint") }}</p>
      <section class="translation-settings-section">
        <div class="translation-settings-section-heading"><strong>{{ t("datasetEditor.caption.translationDictionaryTitle") }}</strong><span>{{ dictionary.row_count || 0 }} {{ t("datasetEditor.caption.translationDictionaryRows") }}</span></div>
        <p class="caption-translation-dialog-hint">{{ dictionary.installed ? t("datasetEditor.caption.translationDictionaryReady") : t("datasetEditor.caption.translationDictionaryMissing") }}</p>
        <small v-if="dictionary.error" class="caption-translation-error">{{ dictionary.error }}</small>
        <div class="caption-translation-cache-row">
          <span>{{ dictionary.state }}<template v-if="dictionary.downloaded_bytes"> · {{ dictionary.downloaded_bytes }}/{{ dictionary.total_bytes || "?" }}</template></span>
          <span class="translation-settings-actions">
            <el-button :loading="dictionaryBusy" @click="emit('checkDictionary')">{{ t("datasetEditor.caption.translationDictionaryCheck") }}</el-button>
            <el-button v-if="dictionary.installed" :loading="dictionaryBusy" @click="emit('updateDictionary')">{{ t("datasetEditor.caption.translationDictionaryUpdate") }}</el-button>
            <el-button v-else :loading="dictionaryBusy" @click="emit('retryDictionary')">{{ t("datasetEditor.caption.translationDictionaryRetry") }}</el-button>
            <el-button v-if="dictionary.state === 'downloading'" :loading="dictionaryBusy" @click="emit('cancelDictionary')">{{ t("datasetEditor.caption.translationDictionaryCancel") }}</el-button>
          </span>
        </div>
      </section>
      <section class="translation-settings-section">
        <div class="translation-settings-section-heading"><strong>{{ t("datasetEditor.caption.translationLocalModelTitle") }}</strong><span>{{ localModel.model_id }}</span></div>
        <p class="caption-translation-dialog-hint">{{ t("datasetEditor.caption.translationLocalModelHint") }}</p>
        <label class="translation-settings-switch"><span>{{ t("datasetEditor.caption.translationLocalEnabled") }}</span><el-switch :model-value="localEnabled" @update:model-value="emit('update:local-enabled', $event)" /></label>
        <label class="schema-field"><span class="field-label">{{ t("datasetEditor.caption.translationLocalEndpoint") }}</span><el-input :model-value="localEndpoint" @update:model-value="emit('update:local-endpoint', $event)" /></label>
        <label class="schema-field"><span class="field-label">{{ t("datasetEditor.caption.translationRuntimePath") }}</span><el-input :model-value="localRuntimePath" :placeholder="t('datasetEditor.caption.translationRuntimePathPlaceholder')" @update:model-value="emit('update:local-runtime-path', $event)" /></label>
        <small v-if="localModel.error" class="caption-translation-error">{{ localModel.error }}</small>
        <div class="caption-translation-cache-row">
          <span>{{ localModel.state }}<template v-if="localModel.downloaded_bytes"> · {{ localModel.downloaded_bytes }}/{{ localModel.total_bytes || "?" }}</template></span>
          <span class="translation-settings-actions">
            <el-button v-if="localModel.state === 'downloading'" :loading="localModelBusy" @click="emit('cancelLocalModel')">{{ t("datasetEditor.caption.translationLocalCancel") }}</el-button>
            <el-button v-else-if="!localModel.installed" :loading="localModelBusy" @click="emit('installLocalModel')">{{ t("datasetEditor.caption.translationLocalInstall") }}</el-button>
            <el-button v-else-if="localModel.state === 'running'" :loading="localModelBusy" @click="emit('stopLocalModel')">{{ t("datasetEditor.caption.translationLocalStop") }}</el-button>
            <el-button v-else :loading="localModelBusy" @click="emit('startLocalModel')">{{ t("datasetEditor.caption.translationLocalStart") }}</el-button>
          </span>
        </div>
      </section>
      <label class="schema-field"><span class="field-label">{{ t("datasetEditor.caption.translationEndpoint") }}</span><el-input :model-value="endpoint" :placeholder="t('datasetEditor.caption.translationEndpointPlaceholder')" @update:model-value="emit('update:endpoint', $event)" /></label>
      <label class="schema-field"><span class="field-label">{{ t("datasetEditor.caption.translationModel") }}</span><el-input :model-value="model" :placeholder="t('datasetEditor.caption.translationModelPlaceholder')" @update:model-value="emit('update:model', $event)" /></label>
      <label class="schema-field"><span class="field-label">{{ t("datasetEditor.caption.translationKey") }}</span><el-input :model-value="apiKey" type="password" show-password autocomplete="new-password" :placeholder="t('datasetEditor.caption.translationKeyPlaceholder')" @update:model-value="emit('update:apiKey', $event)" /></label>
      <small v-if="loading">{{ t("datasetEditor.caption.translationLoading") }}</small>
      <small v-if="error" class="caption-translation-error">{{ error }}</small>
      <div class="caption-translation-cache-row">
        <span>{{ t("datasetEditor.caption.translationCache", { n: cacheCount }) }}</span>
        <el-button :loading="clearingCache" @click="emit('clearCache')">
          {{ clearingCache ? t("datasetEditor.caption.translationCacheClearing") : t("datasetEditor.caption.translationCacheClear") }}
        </el-button>
      </div>
    </div>
    <template #footer>
      <el-button :disabled="saving" @click="emit('update:modelValue', false)">{{ t("datasetEditor.caption.translationCancel") }}</el-button>
      <el-button type="primary" :loading="saving" :disabled="loading" @click="emit('save')">{{ t("datasetEditor.caption.translationSave") }}</el-button>
    </template>
  </el-dialog>
</template>
