<script setup lang="ts">
import { computed } from "vue"
import { useI18n } from "vue-i18n"
import type { CaptionJobStatus } from "../api/tagger"
const props = defineProps<{ status: CaptionJobStatus }>()
const { t } = useI18n()
const percent = computed(() => props.status.total ? Math.round(props.status.current / props.status.total * 100) : 0)
const progressLabel = computed(() => t(props.status.mode === "tag" ? "tagger.taggingMeter" : "tagger.caption.progress"))
</script>

<template>
  <div class="caption-job-progress">
    <div class="meter" role="progressbar" :aria-label="progressLabel" :aria-valuenow="percent" aria-valuemin="0" aria-valuemax="100"><header><span>{{ progressLabel }}</span><b>{{ percent }}%</b></header><div><i :style="{ width: percent + '%' }" /></div><small>{{ status.current }} / {{ status.total }} {{ status.filename }}</small></div>
    <p>{{ t("tagger.caption.counts", { success: status.succeeded, skipped: status.skipped || 0, failed: status.failed, cancelled: status.cancelled }) }}</p>
    <p v-if="status.recovered" class="caption-recovered" role="status">{{ t("tagger.caption.recovered") }}</p>
    <ul v-if="status.errors.length" class="caption-error-list"><li v-for="(item, index) in status.errors" :key="index">{{ item.filename }} · {{ item.code }} · {{ item.message }}</li></ul>
  </div>
</template>
