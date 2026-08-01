<script setup lang="ts">
import { computed } from "vue"
import { useI18n } from "vue-i18n"
import AppShell from "./layouts/AppShell.vue"
import { getElementPlusLocale, type AppLocale } from "./i18n"

const { locale } = useI18n()
const elementPlusLocale = computed(() => getElementPlusLocale(locale.value as AppLocale))
</script>

<template>
  <el-config-provider :locale="elementPlusLocale">
    <AppShell />
  </el-config-provider>
</template>
