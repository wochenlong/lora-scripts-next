<script setup lang="ts">
import { computed, onMounted } from "vue"
import { storeToRefs } from "pinia"
import { useRoute } from "vue-router"
import { useI18n } from "vue-i18n"
import { isSafePluginHostUrl } from "../../api/plugins"
import { useExtensionsStore } from "../../stores/extensions"

const route = useRoute()
const { t } = useI18n()
const extensionsStore = useExtensionsStore()
const { loading, error } = storeToRefs(extensionsStore)
const pluginId = computed(() => String(route.params.pluginId || ""))
const extension = computed(() => extensionsStore.find(pluginId.value))
const settingsUrl = computed(() => {
  const value = extension.value?.ui.settings?.entryUrl
  return isSafePluginHostUrl(value) ? value : ""
})

onMounted(() => void extensionsStore.ensureLoaded())
</script>

<template>
  <div class="plugin-extension-page plugin-settings-page">
    <header>
      <span class="eyebrow">{{ t("extensionHost.settings.eyebrow") }}</span>
      <h1>{{ extension?.displayName || t("extensionHost.settings.title") }}</h1>
      <p>{{ t("extensionHost.settings.subtitle") }}</p>
    </header>
    <section v-if="loading" class="plugin-extension-state" aria-live="polite">{{ t("extensionHost.loading") }}</section>
    <section v-else-if="error" class="plugin-extension-state is-error" role="alert">{{ error }}</section>
    <section v-else-if="!settingsUrl" class="plugin-extension-state">
      <h2>{{ t("extensionHost.settings.unavailable") }}</h2>
      <p>{{ t("extensionHost.settings.unavailableHint") }}</p>
    </section>
    <iframe
      v-else
      class="plugin-settings-frame"
      :src="settingsUrl"
      :title="t('extensionHost.settings.frameTitle', { name: extension?.displayName || pluginId })"
      sandbox="allow-scripts"
      referrerpolicy="no-referrer"
    />
  </div>
</template>
