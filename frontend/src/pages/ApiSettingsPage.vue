<script setup lang="ts">
import { onMounted, ref } from "vue"
import { ElButton, ElMessage } from "element-plus"
import { useI18n } from "vue-i18n"
import { datasetApi } from "../api/dataset"
import { useTagTranslations } from "../composables/useTagTranslations"
import LlmSettingsDialog from "../components/LlmSettingsDialog.vue"

const { t } = useI18n()
const cacheCount = ref(0)
const clearingCache = ref(false)
const error = ref("")

async function loadCacheCount() {
  try { cacheCount.value = (await datasetApi.tagTranslationCache()).total }
  catch { cacheCount.value = 0 }
}

async function clearCache() {
  clearingCache.value = true
  error.value = ""
  try {
    await datasetApi.clearTagTranslationCache()
    useTagTranslations().clearCache()
    cacheCount.value = 0
    ElMessage.success(t("settings.api.cacheCleared"))
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : String(caught)
  } finally {
    clearingCache.value = false
  }
}

onMounted(() => { void loadCacheCount() })
</script>

<template>
  <section class="settings-card">
    <h2>{{ t("settings.api.title") }}</h2>
    <small>{{ t("settings.api.hint") }}</small>
    <LlmSettingsDialog :model-value="true" capability="text" embedded />
    <details class="llm-advanced-settings api-cache-maintenance">
      <summary>{{ t("datasetEditor.caption.translationCache", { n: cacheCount }) }}</summary>
      <div class="caption-translation-cache-row">
        <el-button :loading="clearingCache" @click="clearCache">{{ clearingCache ? t("datasetEditor.caption.translationCacheClearing") : t("datasetEditor.caption.translationCacheClear") }}</el-button>
        <small v-if="error" class="caption-translation-error" role="alert">{{ error }}</small>
      </div>
    </details>
  </section>
</template>
