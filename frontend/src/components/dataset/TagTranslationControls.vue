<script setup lang="ts">
import { useI18n } from "vue-i18n"
import { ElOption, ElSelect, ElSwitch } from "element-plus"
import type { TagTranslationProvider } from "../../api/dataset"

defineProps<{
  enabled: boolean
  available: boolean
  unavailableHint: string
  provider: TagTranslationProvider
  loading: boolean
  error: string
  progressCompleted: number
  progressTotal: number
  progressUnresolved: number
}>()

const emit = defineEmits<{
  "update:enabled": [value: boolean]
  "update:provider": [value: TagTranslationProvider]
}>()

const { t } = useI18n()
</script>

<template>
  <div class="caption-translation-toolbar" aria-live="polite">
    <div class="caption-translation-heading">
      <span>{{ t("datasetEditor.caption.translationEnabled") }}</span>
      <el-switch
        :model-value="enabled"
        :disabled="!available"
        :aria-label="t('datasetEditor.caption.translationEnabled')"
        @update:model-value="emit('update:enabled', Boolean($event))"
      />
    </div>
    <small v-if="!available" class="caption-translation-warning">{{ unavailableHint }}</small>
    <el-select :model-value="provider" :aria-label="t('datasetEditor.caption.translationProvider')" @update:model-value="emit('update:provider', $event)">
      <el-option value="danbooru" :label="t('datasetEditor.caption.translationProviderDanbooru')" />
      <el-option value="mymemory" :label="t('datasetEditor.caption.translationProviderMymemory')" />
      <el-option value="llm" :label="t('datasetEditor.caption.translationProviderLlm')" />
      <el-option value="auto" :label="t('datasetEditor.caption.translationAuto')" />
    </el-select>
    <small v-if="loading || progressTotal" class="caption-translation-progress">
      <span v-if="loading">{{ t("datasetEditor.caption.translationLoading") }}</span>
      <span v-if="progressTotal">{{ progressCompleted }}/{{ progressTotal }}<template v-if="progressUnresolved">（{{ t("datasetEditor.caption.translationUnresolved", { n: progressUnresolved }) }}）</template></span>
    </small>
    <small v-if="error" class="caption-translation-error">{{ error }}</small>
  </div>
</template>
