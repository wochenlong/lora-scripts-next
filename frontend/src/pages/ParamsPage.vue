<script setup lang="ts">
import { useI18n } from "vue-i18n"

const { t } = useI18n()
</script>

<template>
  <article class="content-page">
    <header class="content-hero"><span class="eyebrow">TRAINING REFERENCE</span><h1>{{ t("paramsPage.title") }}</h1><p>{{ t("paramsPage.subtitle") }}</p></header>
    <section><h2>{{ t("paramsPage.s1Title") }}</h2><h3>{{ t("paramsPage.baseModel") }}</h3><p>{{ t("paramsPage.baseModelDesc") }}</p><h3>{{ t("paramsPage.resolution") }}</h3><p>{{ t("paramsPage.resolutionDesc") }}</p></section>
    <section><h2>{{ t("paramsPage.s2Title") }}</h2><div class="content-table"><div><strong>Epoch / Step</strong><span>{{ t("paramsPage.epochDesc") }}</span></div><div><strong>Batch size</strong><span>{{ t("paramsPage.batchDesc") }}</span></div><div><strong>Learning rate</strong><span>{{ t("paramsPage.lrDesc") }}</span></div></div></section>
    <section><h2>{{ t("paramsPage.s3Title") }}</h2><p><code>network_dim</code> {{ t("paramsPage.s3a") }}</p><p>{{ t("paramsPage.s3b") }}</p></section>
    <section><h2>{{ t("paramsPage.s4Title") }}</h2><p>{{ t("paramsPage.s4a") }}</p></section>
  </article>
</template>
