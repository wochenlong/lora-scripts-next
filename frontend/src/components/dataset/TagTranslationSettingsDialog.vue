<script setup lang="ts">
import { useI18n } from "vue-i18n"
import { ElButton, ElDialog, ElInput } from "element-plus"

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
