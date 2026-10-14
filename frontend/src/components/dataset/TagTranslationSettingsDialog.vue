<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { useI18n } from "vue-i18n"
import { ElButton, ElDialog } from "element-plus"
import type { TagDictionaryStatus, TagTranslationProvider } from "../../api/dataset"
import { DEFAULT_CAPTION_TRANSLATION_SETTINGS, type CaptionTranslationSettings } from "../../api/llm"

const props = defineProps<{
  modelValue: boolean
  loading: boolean
  error: string
  provider: TagTranslationProvider
  contentType?: "tag" | "natural"
  llmMode: "remote" | "local"
  dictionary: TagDictionaryStatus
  dictionaryBusy: boolean
  remoteConfigured?: boolean
  sharedLocalReady?: boolean
  captionSettings?: CaptionTranslationSettings
  captionSettingsLoaded?: boolean
  captionSettingsLoading?: boolean
  captionSettingsSaving?: boolean
  captionSettingsError?: string
}>()

const emit = defineEmits<{
  "update:modelValue": [value: boolean]
  "update:provider": [value: TagTranslationProvider]
  "update:llm-mode": [value: "remote" | "local"]
  checkDictionary: []
  updateDictionary: []
  retryDictionary: []
  cancelDictionary: []
  manageLlm: []
  goToLlmPage: []
  saveCaptionSettings: [settings: CaptionTranslationSettings]
  reloadCaptionSettings: []
}>()

const { t } = useI18n()
const captionDraft = ref<CaptionTranslationSettings>({ ...DEFAULT_CAPTION_TRANSLATION_SETTINGS })
watch(() => [props.modelValue, props.captionSettings] as const, () => {
  if (props.modelValue) captionDraft.value = { ...(props.captionSettings || DEFAULT_CAPTION_TRANSLATION_SETTINGS) }
}, { immediate: true })
const captionParametersValid = computed(() => Number.isInteger(captionDraft.value.concurrency) && captionDraft.value.concurrency >= 1 && captionDraft.value.concurrency <= 8
  && Number.isInteger(captionDraft.value.max_tokens) && captionDraft.value.max_tokens >= 128 && captionDraft.value.max_tokens <= 8192
  && typeof captionDraft.value.temperature === "number" && Number.isFinite(captionDraft.value.temperature) && captionDraft.value.temperature >= 0 && captionDraft.value.temperature <= 2)

/** LLM requests share the global remote-first route. */
type TranslationSource = "mymemory" | "llm"

const providerOptions = computed<Array<{ key: TranslationSource; label: string }>>(() => [
  { key: "mymemory", label: t("datasetEditor.caption.translationProviderDictionaryFree") },
  { key: "llm", label: t("datasetEditor.caption.translationProviderDictionaryLlm") },
])

const activeSource = computed<TranslationSource>(() => {
  if (props.provider !== "llm") return "mymemory"
  return "llm"
})

function selectSource(key: TranslationSource) {
  emit("update:provider", key)
  // Source selection must never enable a local-only routing bypass.
}
</script>

<template>
  <el-dialog :model-value="modelValue" :title="t('datasetEditor.caption.translationSettingsTitle')" width="min(640px, 94vw)" :close-on-click-modal="!captionSettingsSaving" :close-on-press-escape="!captionSettingsSaving" :show-close="!captionSettingsSaving" @update:model-value="emit('update:modelValue', $event)">
    <div class="caption-translation-dialog">
      <p class="caption-translation-dialog-hint">{{ t(contentType === 'natural' ? "datasetEditor.caption.naturalTranslationSettingsHint" : "datasetEditor.caption.translationSettingsHint") }}</p>

      <section v-if="contentType === 'natural'" class="translation-settings-section natural-translation-parameters">
        <strong>{{ t("datasetEditor.caption.naturalParameters") }}</strong>
        <fieldset :disabled="!captionSettingsLoaded || captionSettingsLoading || captionSettingsSaving" class="caption-translation-settings">
          <label>{{ t('datasetEditor.caption.translationConcurrency') }}<input v-model.number="captionDraft.concurrency" class="natural-translation-concurrency" type="number" min="1" max="8" step="1" /></label>
          <label>{{ t('datasetEditor.caption.translationMaxTokens') }}<input v-model.number="captionDraft.max_tokens" class="natural-translation-max-tokens" type="number" min="128" max="8192" step="1" /></label>
          <label>{{ t('datasetEditor.caption.translationTemperature') }}<input v-model.number="captionDraft.temperature" class="natural-translation-temperature" type="number" min="0" max="2" step="0.1" /></label>
        </fieldset>
        <small>{{ t('datasetEditor.caption.naturalParametersHint') }}</small>
        <small v-if="captionSettingsLoading" role="status">{{ t('datasetEditor.caption.translationLoading') }}</small>
        <small v-if="captionSettingsError" class="caption-translation-error" role="alert">{{ captionSettingsError }}</small>
        <small v-if="!captionParametersValid" class="caption-translation-error" role="alert">{{ t('datasetEditor.caption.naturalParametersInvalid') }}</small>
        <el-button v-if="captionSettingsError" class="natural-translation-reload" :disabled="captionSettingsLoading || captionSettingsSaving" @click="emit('reloadCaptionSettings')">{{ t('datasetEditor.caption.naturalParametersReload') }}</el-button>
      </section>

      <section v-if="contentType !== 'natural'" class="translation-settings-section">
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

      <section v-if="contentType !== 'natural'" class="translation-settings-section">
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
        <p class="caption-translation-dialog-hint">{{ t("datasetEditor.caption.translationSettingsMoved") }}</p>
        <el-button v-if="contentType === 'natural'" class="translation-go-llm" :disabled="captionSettingsSaving" @click="emit('goToLlmPage')">{{ t('datasetEditor.caption.goToLlmPage') }}</el-button>
        <el-button v-else class="translation-manage-llm" @click="emit('manageLlm')">{{ t("llm.title") }}</el-button>
      </section>
      <small v-if="loading">{{ t("datasetEditor.caption.translationLoading") }}</small>
      <small v-if="error" class="caption-translation-error">{{ error }}</small>
    </div>
    <template #footer>
      <el-button v-if="contentType === 'natural'" class="natural-translation-save" :loading="captionSettingsSaving" :disabled="!captionSettingsLoaded || captionSettingsLoading || captionSettingsSaving || !captionParametersValid" @click="emit('saveCaptionSettings', { ...captionDraft })">{{ t('datasetEditor.caption.naturalParametersSave') }}</el-button>
      <el-button :disabled="captionSettingsSaving" @click="emit('update:modelValue', false)">{{ t("datasetEditor.caption.translationCancel") }}</el-button>
    </template>
  </el-dialog>
</template>
