<script setup lang="ts">
import { computed } from "vue"
import { useI18n } from "vue-i18n"
import { ElButton, ElDialog } from "element-plus"
import type { TagDictionaryStatus, TagTranslationProvider } from "../../api/dataset"

const props = defineProps<{
  modelValue: boolean
  loading: boolean
  error: string
  provider: TagTranslationProvider
  llmMode: "remote" | "local"
  dictionary: TagDictionaryStatus
  dictionaryBusy: boolean
}>()

const emit = defineEmits<{
  "update:modelValue": [value: boolean]
  "update:provider": [value: TagTranslationProvider]
  "update:llm-mode": [value: "remote" | "local"]
  checkDictionary: []
  updateDictionary: []
  retryDictionary: []
  cancelDictionary: []
}>()

const { t } = useI18n()

/** Three concrete sources map onto the backend's dictionary/LLM providers. */
type TranslationSource = "dictionary" | "local" | "api"

const providerOptions = computed<Array<{ key: TranslationSource; label: string }>>(() => [
  { key: "dictionary", label: t("datasetEditor.caption.translationProviderDanbooru") },
  { key: "local", label: t("datasetEditor.caption.translationProviderLocalModel") },
  { key: "api", label: t("datasetEditor.caption.translationProviderApi") },
])

const activeSource = computed<TranslationSource>(() => {
  if (props.provider !== "llm") return "dictionary"
  return props.llmMode === "local" ? "local" : "api"
})

function selectSource(key: TranslationSource) {
  if (key === "dictionary") {
    emit("update:provider", "danbooru")
    return
  }
  emit("update:provider", "llm")
  emit("update:llm-mode", key === "local" ? "local" : "remote")
}
</script>

<template>
  <el-dialog :model-value="modelValue" :title="t('datasetEditor.caption.translationSettingsTitle')" width="min(640px, 94vw)" @update:model-value="emit('update:modelValue', $event)">
    <div class="caption-translation-dialog">
      <p class="caption-translation-dialog-hint">{{ t("datasetEditor.caption.translationSettingsHint") }}</p>

      <section class="translation-settings-section">
        <div class="translation-settings-section-heading"><strong>{{ t("datasetEditor.caption.translationProvider") }}</strong></div>
        <div class="caption-translation-provider" role="radiogroup" :aria-label="t('datasetEditor.caption.translationProvider')">
          <button
            v-for="option in providerOptions"
            :key="option.key"
            type="button"
            role="radio"
            :aria-checked="activeSource === option.key"
            :class="{ active: activeSource === option.key }"
            @click="selectSource(option.key)"
          >{{ option.label }}</button>
        </div>
      </section>

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

      <p class="caption-translation-dialog-hint">
        {{ t("datasetEditor.caption.translationSettingsMoved") }}
        <RouterLink class="translation-settings-link" to="/settings/api">{{ t("settings.nav.api") }}</RouterLink>
      </p>
      <small v-if="loading">{{ t("datasetEditor.caption.translationLoading") }}</small>
      <small v-if="error" class="caption-translation-error">{{ error }}</small>
    </div>
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">{{ t("datasetEditor.caption.translationCancel") }}</el-button>
    </template>
  </el-dialog>
</template>
