<script setup lang="ts">
import { useI18n } from "vue-i18n"
import type { LocalVisionStatus } from "../api/llm"

defineProps<{ status: LocalVisionStatus; busy: boolean; locked?: boolean }>()
const emit = defineEmits<{ action: [action: "setup" | "start" | "stop" | "cancel"] }>()
const { t } = useI18n()
</script>

<template>
  <section class="caption-local-runtime wide-field managed-vision-model">
    <strong>{{ t("tagger.caption.localRuntimeTitle") }}</strong>
    <p>{{ t("tagger.caption.localRuntimeHint") }}</p>
    <p role="status">{{ t('tagger.caption.localStates.' + status.state) }} · {{ (status.downloaded_bytes / 1048576).toFixed(1) }} / {{ (status.total_bytes / 1048576).toFixed(1) }} MiB</p>
    <p v-if="status.error" role="alert">{{ status.error }}</p>
    <button v-if="['installing', 'downloading'].includes(status.state)" type="button" :disabled="busy" @click="emit('action', 'cancel')">{{ t("tagger.caption.cancelInstall") }}</button>
    <button v-else-if="!status.installed || !status.runtime_installed" type="button" :disabled="busy || locked" @click="emit('action', 'setup')">{{ t("tagger.caption.setupLocal") }}</button>
    <button v-else-if="status.state !== 'running'" type="button" :disabled="busy || locked" @click="emit('action', 'start')">{{ t("tagger.caption.startLocal") }}</button>
    <button v-else type="button" :disabled="busy || locked" @click="emit('action', 'stop')">{{ t("tagger.caption.stopLocal") }}</button>
  </section>
</template>
