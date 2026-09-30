<script setup lang="ts">
import { useI18n } from "vue-i18n"

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
}>()

const emit = defineEmits<{
  "update:modelValue": [value: boolean]
  "update:endpoint": [value: string]
  "update:model": [value: string]
  "update:apiKey": [value: string]
  save: []
  clearCache: []
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
      <label>{{ t("datasetEditor.caption.translationEndpoint") }}<input :value="endpoint" :placeholder="t('datasetEditor.caption.translationEndpointPlaceholder')" @input="emit('update:endpoint', ($event.target as HTMLInputElement).value)"></label>
      <label>{{ t("datasetEditor.caption.translationModel") }}<input :value="model" :placeholder="t('datasetEditor.caption.translationModelPlaceholder')" @input="emit('update:model', ($event.target as HTMLInputElement).value)"></label>
      <label>{{ t("datasetEditor.caption.translationKey") }}<input :value="apiKey" type="password" :placeholder="t('datasetEditor.caption.translationKeyPlaceholder')" @input="emit('update:apiKey', ($event.target as HTMLInputElement).value)"></label>
      <small v-if="loading">{{ t("datasetEditor.caption.translationLoading") }}</small>
      <small v-if="error" class="caption-translation-error">{{ error }}</small>
      <div class="caption-translation-cache-row">
        <span>{{ t("datasetEditor.caption.translationCache", { n: cacheCount }) }}</span>
        <button type="button" class="dataset-tool-secondary" :disabled="clearingCache" @click="emit('clearCache')">
          {{ clearingCache ? t("datasetEditor.caption.translationCacheClearing") : t("datasetEditor.caption.translationCacheClear") }}
        </button>
      </div>
    </div>
    <template #footer>
      <button type="button" class="dataset-tool-secondary" :disabled="saving" @click="emit('update:modelValue', false)">{{ t("datasetEditor.caption.translationCancel") }}</button>
      <button type="button" class="primary-action" :disabled="saving || loading" @click="emit('save')">{{ saving ? t("datasetEditor.caption.translationSaving") : t("datasetEditor.caption.translationSave") }}</button>
    </template>
  </el-dialog>
</template>
