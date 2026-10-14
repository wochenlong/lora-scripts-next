<script setup lang="ts">
import { useI18n } from "vue-i18n"
import type { LocalVisionStatus } from "../api/llm"

defineProps<{ status: LocalVisionStatus; busy: boolean; locked?: boolean }>()
const emit = defineEmits<{ action: [action: "setup" | "start" | "stop" | "cancel"] }>()
const { t } = useI18n()
</script>

<template>
  <section class="caption-local-runtime wide-field managed-vision-model">
    <p>{{ t("tagger.caption.localRuntimeHint") }}</p>
    <dl class="managed-model-facts">
      <template v-if="status.size_bytes"><dt>{{ t("llm.modelSize") }}</dt><dd>{{ (status.size_bytes / 1073741824).toFixed(2) }} GiB</dd></template>
      <dt>{{ t("llm.memoryEstimate") }}</dt><dd>{{ status.estimated_peak_rss_bytes ? (status.estimated_peak_rss_bytes / 1073741824).toFixed(2) + ' GiB' : t("llm.memoryUnknown") }}</dd>
      <dt>{{ t("llm.serviceStatus") }}</dt><dd role="status">{{ t('tagger.caption.localStates.' + status.state) }}</dd>
      <template v-if="status.runtime_state"><dt>{{ t("llm.runtimeStatus") }}</dt><dd>{{ status.runtime_state === 'ready' ? t('tagger.caption.localStates.ready') : status.runtime_state === 'installing' ? t('tagger.caption.localStates.installing') : status.runtime_state }}</dd></template>
    </dl>
    <p v-if="['installing', 'downloading'].includes(status.state) || status.runtime_state === 'installing'" class="managed-model-progress" role="status">{{ (status.downloaded_bytes / 1048576).toFixed(1) }} / {{ (status.total_bytes / 1048576).toFixed(1) }} MiB<template v-if="status.runtime_downloaded_bytes"> · {{ (status.runtime_downloaded_bytes / 1048576).toFixed(1) }} / {{ ((status.runtime_total_bytes || 0) / 1048576).toFixed(1) }} MiB</template></p>
    <p v-if="status.error" role="alert">{{ status.error }}</p>
    <button v-if="['installing', 'downloading'].includes(status.state) || status.runtime_state === 'installing'" type="button" :disabled="busy" @click="emit('action', 'cancel')">{{ t("tagger.caption.cancelInstall") }}</button>
    <button v-else-if="!status.installed || !status.runtime_installed" type="button" :disabled="busy || locked" @click="emit('action', 'setup')">{{ t("tagger.caption.setupLocal") }}</button>
    <button v-else-if="status.state !== 'running'" type="button" :disabled="busy || locked" @click="emit('action', 'start')">{{ t("tagger.caption.startLocal") }}</button>
    <button v-else type="button" :disabled="busy || locked" @click="emit('action', 'stop')">{{ t("tagger.caption.stopLocal") }}</button>
  </section>
</template>
