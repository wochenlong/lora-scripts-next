<script setup lang="ts">
import { releases } from "../content/releases"
</script>

<template>
  <article class="content-page">
    <header class="content-hero content-hero-split"><div><span class="eyebrow">RELEASE NOTES</span><h1>更新日志</h1><p>仓库完整历史保存在 <code>CHANGELOG.md</code>，这里展示主要发行版本。</p></div><img src="/assets/changelog-banner.webp" alt="Next Trainer 更新日志"></header>
    <section class="release-list"><article v-for="release in releases" :key="release.version"><header><h2>{{ release.version }}</h2><time>{{ release.date }}</time></header><ul><li v-for="item in release.items" :key="item">{{ item }}</li></ul></article></section>
    <a class="secondary-action" href="https://github.com/wochenlong/lora-scripts-next/blob/master/CHANGELOG.md" target="_blank" rel="noreferrer">查看完整更新日志</a>
  </article>
</template>
