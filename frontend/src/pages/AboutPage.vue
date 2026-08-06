<script setup lang="ts">
import { useI18n } from "vue-i18n"

const { t } = useI18n()
</script>

<template>
  <article class="content-page">
    <header class="content-hero content-hero-split"><div><span class="eyebrow">ABOUT</span><h1>Next Trainer</h1><p>{{ t("about.tagline") }}</p></div><img class="about-logo" src="/assets/home-logo.webp" alt="Next Trainer"></header>
    <section><h2>{{ t("about.projectTitle") }}</h2><i18n-t keypath="about.projectDesc" tag="p" scope="global"><template #schemastery><a href="https://github.com/shigma/schemastery" target="_blank" rel="noreferrer">Schemastery</a></template></i18n-t></section>
    <section><h2>{{ t("about.feedbackTitle") }}</h2><i18n-t keypath="about.feedbackDesc" tag="p" scope="global"><template #issues><a href="https://github.com/wochenlong/lora-scripts-next/issues" target="_blank" rel="noreferrer">GitHub Issues</a></template></i18n-t></section>
    <section><h2>{{ t("about.linksTitle") }}</h2><div class="content-links"><a href="https://github.com/wochenlong/lora-scripts-next" target="_blank" rel="noreferrer">{{ t("about.source") }}</a><a href="https://github.com/wochenlong/lora-scripts-next/releases" target="_blank" rel="noreferrer">{{ t("about.releases") }}</a><a href="https://github.com/wochenlong/lora-scripts-next/issues" target="_blank" rel="noreferrer">{{ t("about.issues") }}</a></div></section>
  </article>
</template>
