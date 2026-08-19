<script setup lang="ts">
import { computed } from "vue"
import { useI18n } from "vue-i18n"

const { t } = useI18n()

const portals = computed(() => [
  { title: t("home.portals.training.title"), text: t("home.portals.training.text"), to: "/training", tone: "blue" },
  { title: t("home.portals.dataset.title"), text: t("home.portals.dataset.text"), to: "/dataset", tone: "violet" },
  { title: t("home.portals.tasks.title"), text: t("home.portals.tasks.text"), to: "/tasks", tone: "cyan" },
] as const)
</script>

<template>
  <div class="home-page">
    <section class="hero">
      <div class="hero-copy">
        <span class="eyebrow">LOCAL TRAINING WORKSPACE</span>
        <h1>{{ t("home.heroTitle") }}</h1>
        <p>{{ t("home.heroSubtitle") }}</p>
        <div class="hero-actions"><RouterLink class="primary-action" to="/training">{{ t("home.startTraining") }}</RouterLink><RouterLink class="secondary-action" to="/help/guide.html">{{ t("home.readGuide") }}</RouterLink></div>
      </div>
      <div class="hero-visual"><div class="visual-grid" /><div class="orbit orbit-one" /><div class="orbit orbit-two" /><img src="/assets/home-logo.webp" alt="Next Trainer"></div>
    </section>
    <section class="portal-grid" :aria-label="t('home.portalAria')">
      <RouterLink v-for="(portal, index) in portals" :key="portal.to" :to="portal.to" class="portal-card" :data-tone="portal.tone">
        <span class="portal-index">0{{ index + 1 }}</span><h2>{{ portal.title }}</h2><p>{{ portal.text }}</p><span class="portal-link">{{ t("home.enter") }} <b>→</b></span>
      </RouterLink>
    </section>
    <section class="status-strip"><span><i class="status-dot" /> {{ t("home.status.local") }}</span><span>{{ t("home.status.vue") }}</span><span>{{ t("home.status.models") }}</span></section>
    <p class="home-credit">
      <i18n-t keypath="home.credit" tag="span" scope="global">
        <template #about><RouterLink to="/settings/about">{{ t("settings.nav.about") }}</RouterLink></template>
        <template #notice>
          <a href="https://github.com/wochenlong/lora-scripts-next/blob/main/NOTICE.md" target="_blank" rel="noreferrer">NOTICE.md</a>
        </template>
      </i18n-t>
    </p>
  </div>
</template>
