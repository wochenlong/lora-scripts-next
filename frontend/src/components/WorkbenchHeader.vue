<script setup lang="ts">
import { useI18n } from "vue-i18n"

const { t } = useI18n()
const emit = defineEmits<{ save: []; import: []; reset: [] }>()
</script>

<template>
  <header class="workbench-header">
    <div><h1>{{ t("training.title") }}</h1><p>{{ t("training.subtitle") }}</p></div>
    <div class="workbench-actions">
      <button class="ghost-button" @click="emit('save')">{{ t("training.actions.save") }}</button>
      <button class="ghost-button" @click="emit('import')">{{ t("training.actions.import") }}</button>
      <button class="ghost-button" @click="emit('reset')">{{ t("training.actions.reset") }}</button>
    </div>
  </header>
</template>
