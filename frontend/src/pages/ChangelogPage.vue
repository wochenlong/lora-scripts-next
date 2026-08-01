<script setup lang="ts">
import { useI18n } from "vue-i18n"
import { releases } from "../content/releases"

const { t } = useI18n()
</script>

<template>
  <article class="content-page">
    <header class="content-hero content-hero-split"><div><span class="eyebrow">RELEASE NOTES</span><h1>{{ t("changelog.title") }}</h1><i18n-t keypath="changelog.subtitle" tag="p" scope="global"><template #file><code>CHANGELOG.md</code></template></i18n-t></div><img src="/assets/changelog-banner.webp" :alt="t('changelog.bannerAlt')"></header>
    <section class="release-list"><article v-for="release in releases" :key="release.version"><header><h2>{{ release.version }}</h2><time>{{ release.date }}</time></header><ul><li v-for="item in release.items" :key="item">{{ item }}</li></ul></article></section>
    <a class="secondary-action" href="https://github.com/wochenlong/lora-scripts-next/blob/master/CHANGELOG.md" target="_blank" rel="noreferrer">{{ t("changelog.full") }}</a>
  </article>
</template>
