<script setup lang="ts">
import { useI18n } from "vue-i18n"

const { t } = useI18n()
</script>

<template>
  <header class="workbench-header">
    <div><h1>{{ t("training.title") }}</h1><p>{{ t("training.subtitle") }}</p></div>
  </header>
</template>
