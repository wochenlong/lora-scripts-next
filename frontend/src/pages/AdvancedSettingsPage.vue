<script setup lang="ts">
import { useI18n } from "vue-i18n"
import DownloadSourcesPanel from "../components/DownloadSourcesPanel.vue"
import NetworkSettingsPanel from "../components/NetworkSettingsPanel.vue"

/** Network and dependency sources: shared by engine, tagger and plugin installs. */
const { t } = useI18n()
</script>

<template>
  <section class="settings-card">
    <h2>{{ t("settings.advanced.title") }}</h2>
    <small>{{ t("settings.advanced.hint") }}</small>
  </section>
  <NetworkSettingsPanel />
  <DownloadSourcesPanel />
</template>
