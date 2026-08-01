<script setup lang="ts">
import { useI18n } from "vue-i18n"
import DatasetEditorPage from "./DatasetEditorPage.vue"
import TaggerPage from "./TaggerPage.vue"

defineProps<{ tab: "editor" | "tagger" }>()
const { t } = useI18n()
</script>

<template>
  <div class="dataset-section">
    <header class="dataset-section-header">
      <h1>{{ t("dataset.title") }}</h1>
      <div class="segmented dataset-switch" role="group" :aria-label="t('dataset.switchAria')">
        <RouterLink to="/dataset/editor" :class="{ active: tab === 'editor' }">{{ t("dataset.tab.editor") }}</RouterLink>
        <RouterLink to="/dataset/tagger" :class="{ active: tab === 'tagger' }">{{ t("dataset.tab.tagger") }}</RouterLink>
      </div>
    </header>
    <DatasetEditorPage v-if="tab === 'editor'" />
    <TaggerPage v-else />
  </div>
</template>
