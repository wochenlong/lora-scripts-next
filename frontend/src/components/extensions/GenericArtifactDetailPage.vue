<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { useRoute } from "vue-router"
import { useI18n } from "vue-i18n"
import { isSafePluginHostUrl, pluginsApi, type PluginArtifactProjection } from "../../api/plugins"

const route = useRoute()
const { t } = useI18n()
const loading = ref(false)
const error = ref("")
const artifact = ref<PluginArtifactProjection | null>(null)
const pluginId = computed(() => String(route.params.pluginId || ""))
const artifactId = computed(() => String(route.params.artifactId || ""))
const safeDownloadUrl = computed(() => (isSafePluginHostUrl(artifact.value?.downloadUrl) ? artifact.value.downloadUrl : ""))

async function load() {
  artifact.value = null
  error.value = ""
  loading.value = true
  try {
    artifact.value = await pluginsApi.getArtifact(pluginId.value, artifactId.value)
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : t("extensionHost.artifact.unavailable")
  } finally {
    loading.value = false
  }
}

watch([pluginId, artifactId], () => void load(), { immediate: true })
</script>

<template>
  <div class="plugin-extension-page artifact-detail-page">
    <header>
      <span class="eyebrow">{{ t("extensionHost.artifact.eyebrow") }}</span>
      <h1>{{ artifact?.title || t("extensionHost.artifact.title") }}</h1>
      <p>{{ pluginId }} / {{ artifactId }}</p>
    </header>
    <section v-if="loading" class="plugin-extension-state" aria-live="polite">{{ t("extensionHost.loading") }}</section>
    <section v-else-if="error" class="plugin-extension-state is-error" role="alert">
      <h2>{{ t("extensionHost.artifact.unavailable") }}</h2>
      <p>{{ error }}</p>
      <button type="button" class="secondary-action" @click="load">{{ t("extensionHost.retry") }}</button>
    </section>
    <section v-else-if="artifact" class="plugin-artifact-card" :data-status="artifact.status">
      <dl>
        <div>
          <dt>{{ t("extensionHost.artifact.kind") }}</dt>
          <dd>{{ artifact.kind }}</dd>
        </div>
        <div>
          <dt>{{ t("extensionHost.artifact.status") }}</dt>
          <dd>{{ artifact.status }}</dd>
        </div>
      </dl>
      <p v-if="artifact.summary">{{ artifact.summary }}</p>
      <a v-if="safeDownloadUrl" class="primary-action" :href="safeDownloadUrl">{{ t("extensionHost.artifact.download") }}</a>
    </section>
  </div>
</template>
