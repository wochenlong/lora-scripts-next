<script setup lang="ts">
import { useI18n } from "vue-i18n"
import type { TagTranslationProvider } from "../../api/dataset"

defineProps<{
  enabled: boolean
  provider: TagTranslationProvider
  loading: boolean
  error: string
  tagCount: number
}>()

const emit = defineEmits<{
  "update:enabled": [value: boolean]
  "update:provider": [value: TagTranslationProvider]
  load: []
  settings: []
}>()

const { t } = useI18n()
</script>

<template>
  <div class="caption-translation-toolbar" aria-live="polite">
    <label class="caption-translation-toggle">
      <input :checked="enabled" type="checkbox" @change="emit('update:enabled', ($event.target as HTMLInputElement).checked)">
      <span>{{ t("datasetEditor.caption.translationEnabled") }}</span>
    </label>
    <select
      :value="provider"
      :aria-label="t('datasetEditor.caption.translationProvider')"
      @change="emit('update:provider', ($event.target as HTMLSelectElement).value as TagTranslationProvider)"
    >
      <option value="danbooru">{{ t("datasetEditor.caption.translationProviderDanbooru") }}</option>
      <option value="mymemory">{{ t("datasetEditor.caption.translationProviderMymemory") }}</option>
      <option value="llm">{{ t("datasetEditor.caption.translationProviderLlm") }}</option>
      <option value="auto">{{ t("datasetEditor.caption.translationAuto") }}</option>
    </select>
    <button type="button" class="dataset-tool-secondary" :disabled="loading || !tagCount || !enabled" @click="emit('load')">
      {{ loading ? t("datasetEditor.caption.translationLoading") : t("datasetEditor.caption.translationAction") }}
    </button>
    <button type="button" class="dataset-tool-secondary" @click="emit('settings')">
      {{ t("datasetEditor.caption.translationSettings") }}
    </button>
    <small v-if="error" class="caption-translation-error">{{ error }}</small>
  </div>
</template>

