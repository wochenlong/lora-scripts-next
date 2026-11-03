<script setup lang="ts">
import { useI18n } from "vue-i18n"
import DownloadSourcesPanel from "../components/DownloadSourcesPanel.vue"

const { t } = useI18n()
</script>

<template>
  <section class="settings-card">
    <h2>{{ t("settings.advanced.title") }}</h2>
    <small>{{ t("settings.advanced.hint") }}</small>
  </section>
  <DownloadSourcesPanel />
</template>
