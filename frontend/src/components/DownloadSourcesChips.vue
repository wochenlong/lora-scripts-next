<script setup lang="ts">
import { computed, onMounted } from "vue"
import { useI18n } from "vue-i18n"
import { useRouter } from "vue-router"
import { useDownloadSourcesStore } from "../stores/downloadSources"

const { t } = useI18n()
const router = useRouter()
const store = useDownloadSourcesStore()

const channels = [
  { key: "pip", label: "PyPI" },
  { key: "pytorch", label: "PyTorch" },
  { key: "huggingface", label: "HF" },
  { key: "github", label: "GitHub" },
] as const

onMounted(() => {
  void store.ensureLoaded()
})

const items = computed(() =>
  channels.map((channel) => {
    const result = store.resultFor(channel.key)
    const status = store.statusFor(channel.key)
    const choice = store.prefs[channel.key].choice
    const statusText = store.presumedFail(channel.key)
      ? t("settings.engines.downloadSources.status.presumedFail")
      : t(`settings.engines.downloadSources.status.${status}`)
    const detail = result
      ? `${result.url}\n${result.ok ? `${result.latency_ms ?? "?"} ms` : result.error || `HTTP ${result.status ?? "?"}`}`
      : ""
    return {
      key: channel.key,
      label: channel.label,
      status,
      choiceLabel: t(`settings.engines.downloadSources.choices.${channel.key}.${choice}`),
      title: detail ? `${channel.label} · ${statusText}\n${detail}` : `${channel.label} · ${statusText}`,
    }
  }),
)

function openSettings() {
  void router.push("/settings/advanced")
}
</script>

<template>
  <div class="ds-chips" :aria-label="t('settings.engines.downloadSources.chipsAria')">
    <button
      v-for="item in items"
      :key="item.key"
      type="button"
      class="ds-chip"
      :data-status="item.status"
      :title="item.title"
      @click="openSettings"
    >
      <i class="ds-chip-dot" /><span class="ds-chip-label">{{ item.label }}</span><span class="ds-chip-choice">{{ item.choiceLabel }}</span>
    </button>
  </div>
</template>
