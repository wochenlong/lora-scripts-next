<script setup lang="ts">
import { computed } from "vue"
import { useI18n } from "vue-i18n"
import { useRoute } from "vue-router"

const props = defineProps<{ title?: string; titleKey?: string; src: string; configurable?: boolean }>()
const { t } = useI18n()
const route = useRoute()
const displayTitle = computed(() => props.titleKey ? t(props.titleKey) : props.title ?? "")
const backToTasks = computed(() => route.query.from === "tasks")
const resolvedSrc = computed(() => {
  if (!props.configurable) return props.src
  try {
    const settings = JSON.parse(localStorage.getItem("ui-configs") || "{}") as { tensorboard_url?: string }
    return settings.tensorboard_url?.trim() || props.src
  } catch { return props.src }
})
</script>

<template>
  <div class="integration-page"><header><div><span class="eyebrow">INTEGRATED SERVICE</span><h1>{{ displayTitle }}</h1></div><nav><RouterLink v-if="backToTasks" to="/tasks">{{ t("integration.backToTasks") }}</RouterLink><a :href="resolvedSrc" target="_blank" rel="noreferrer">{{ t("integration.openExternal") }}</a></nav></header><iframe :title="displayTitle" :src="resolvedSrc" /></div>
</template>
