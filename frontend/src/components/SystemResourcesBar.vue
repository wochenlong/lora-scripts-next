<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { useI18n } from "vue-i18n"
import { systemApi, type SystemResources } from "../api/system"

const { t } = useI18n()
const resources = ref<SystemResources | null>(null)
let timer: number | undefined

function mbToGb(mb: number): string {
  return (mb / 1024).toFixed(mb >= 10240 ? 0 : 1)
}

function percent(used: number, total: number): number {
  if (!total) return 0
  return Math.min(100, Math.round((used * 100) / total))
}

/** Nearly full → red fill so OOM risk is visible at a glance. */
function pressureLevel(pct: number): "ok" | "high" {
  return pct >= 90 ? "high" : "ok"
}

const gpuLabel = computed(() => {
  const gpu = resources.value?.gpu
  if (!gpu?.vram_total_mb) return ""
  return t("tasks.resources.gpu", {
    used: mbToGb(gpu.vram_used_mb),
    total: mbToGb(gpu.vram_total_mb),
  })
})

const ramLabel = computed(() => {
  const ram = resources.value?.ram
  if (!ram?.total_mb) return ""
  return t("tasks.resources.ram", {
    used: mbToGb(ram.used_mb),
    total: mbToGb(ram.total_mb),
  })
})

const gpuPct = computed(() => {
  const gpu = resources.value?.gpu
  return gpu ? percent(gpu.vram_used_mb, gpu.vram_total_mb) : 0
})

const ramPct = computed(() => {
  const ram = resources.value?.ram
  if (!ram) return 0
  if (typeof ram.percent === "number") return Math.min(100, Math.round(ram.percent))
  return percent(ram.used_mb, ram.total_mb)
})

const visible = computed(() => Boolean(gpuLabel.value || ramLabel.value))

async function refresh() {
  try {
    resources.value = await systemApi.resources()
  } catch {
    // Keep the last good snapshot; header stays quiet if never loaded.
  }
}

onMounted(async () => {
  await refresh()
  timer = window.setInterval(() => { void refresh() }, 3000)
})

onBeforeUnmount(() => {
  if (timer !== undefined) window.clearInterval(timer)
})
</script>

<template>
  <div v-if="visible" class="system-resources-bar" data-testid="system-resources-bar" :title="resources?.gpu?.name || undefined">
    <div v-if="gpuLabel" class="system-resource" :data-level="pressureLevel(gpuPct)">
      <span class="system-resource-label">{{ gpuLabel }}</span>
      <span class="system-resource-track" aria-hidden="true"><i :style="{ width: `${gpuPct}%` }" /></span>
    </div>
    <div v-if="ramLabel" class="system-resource" :data-level="pressureLevel(ramPct)">
      <span class="system-resource-label">{{ ramLabel }}</span>
      <span class="system-resource-track" aria-hidden="true"><i :style="{ width: `${ramPct}%` }" /></span>
    </div>
  </div>
</template>
