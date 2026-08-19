<script setup lang="ts">
import { useI18n } from "vue-i18n"

const { t } = useI18n()
</script>

<template>
  <div class="migration-page">
    <span class="eyebrow">404</span><h1>{{ t("notFound.title") }}</h1><p>{{ t("notFound.desc") }}</p>
    <RouterLink class="secondary-action" to="/">{{ t("notFound.back") }}</RouterLink>
  </div>
</template>
