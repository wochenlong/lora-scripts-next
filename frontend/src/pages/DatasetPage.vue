<script setup lang="ts">
import { useI18n } from "vue-i18n"
import DatasetEditorPage from "./DatasetEditorPage.vue"
import DatasetManagePage from "./DatasetManagePage.vue"
import TaggerPage from "./TaggerPage.vue"

defineProps<{ tab: "manage" | "editor" | "tagger" }>()
const { t } = useI18n()
</script>

<template>
  <div class="dataset-section">
    <header class="dataset-section-header">
      <h1>{{ t("dataset.title") }}</h1>
      <div class="segmented dataset-switch" role="group" :aria-label="t('dataset.switchAria')">
        <RouterLink to="/dataset/manage" :class="{ active: tab === 'manage' }">{{ t("dataset.tab.manage") }}</RouterLink>
        <RouterLink to="/dataset/tagger" :class="{ active: tab === 'tagger' }">{{ t("dataset.tab.tagger") }}</RouterLink>
        <RouterLink to="/dataset/editor" :class="{ active: tab === 'editor' }">{{ t("dataset.tab.editor") }}</RouterLink>
      </div>
    </header>
    <KeepAlive>
      <DatasetManagePage v-if="tab === 'manage'" />
      <DatasetEditorPage v-else-if="tab === 'editor'" />
      <TaggerPage v-else />
    </KeepAlive>
  </div>
</template>
