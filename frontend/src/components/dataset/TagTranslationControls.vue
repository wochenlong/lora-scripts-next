<script setup lang="ts">
import { useI18n } from "vue-i18n"
import { ElSwitch } from "element-plus"

defineProps<{
  enabled: boolean
  available: boolean
  unavailableHint: string
  loading: boolean
  error: string
  progressCompleted: number
  progressTotal: number
  progressUnresolved: number
}>()

const emit = defineEmits<{
  "update:enabled": [value: boolean]
}>()

const { t } = useI18n()
</script>

<template>
  <div class="caption-translation-toolbar" aria-live="polite">
    <div class="caption-translation-heading">
      <span>{{ t("datasetEditor.caption.translationEnabled") }}</span>
      <el-switch
        :model-value="enabled"
        :aria-label="t('datasetEditor.caption.translationEnabled')"
        @update:model-value="emit('update:enabled', Boolean($event))"
      />
    </div>
    <small v-if="!available" class="caption-translation-warning">{{ unavailableHint }}</small>
    <small v-if="loading || progressTotal" class="caption-translation-progress">
      <span v-if="loading">{{ t("datasetEditor.caption.translationLoading") }}</span>
      <span v-if="progressTotal">{{ progressCompleted }}/{{ progressTotal }}<template v-if="progressUnresolved">（{{ t("datasetEditor.caption.translationUnresolved", { n: progressUnresolved }) }}）</template></span>
    </small>
    <small v-if="error" class="caption-translation-error">{{ error }}</small>
  </div>
</template>
