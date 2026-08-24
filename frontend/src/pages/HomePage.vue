<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { useI18n } from "vue-i18n"

const { t } = useI18n()

const portals = computed(() => [
  { title: t("home.portals.training.title"), text: t("home.portals.training.text"), to: "/training", tone: "blue" },
  { title: t("home.portals.dataset.title"), text: t("home.portals.dataset.text"), to: "/dataset", tone: "violet" },
  { title: t("home.portals.tasks.title"), text: t("home.portals.tasks.text"), to: "/tasks", tone: "cyan" },
] as const)

/** 1 product · 2 event · 3 tutorial video (placeholder until official upload). */
const slides = computed(() => [
  { id: "intro", kind: "intro" as const },
  {
    id: "anima-event",
    kind: "poster" as const,
    src: "/assets/home-sponsor-anima.webp",
    href: "https://kusart.com/zh-CN/events/anima",
    alt: t("home.sponsor.anima.alt"),
    badge: t("home.sponsor.anima.badge"),
    caption: t("home.sponsor.anima.caption"),
  },
  {
    id: "anima-tutorial",
    kind: "poster" as const,
    src: "/assets/home-sponsor-bilibili-placeholder.jpg",
    href: "https://www.bilibili.com/video/BV1H3gp68E3R",
    alt: t("home.sponsor.tutorial.alt"),
    badge: t("home.sponsor.tutorial.badge"),
    caption: t("home.sponsor.tutorial.caption"),
  },
])

const active = ref(0)
const paused = ref(false)
let timer: ReturnType<typeof setInterval> | undefined

function go(index: number) {
  const total = slides.value.length
  if (total <= 0) return
  active.value = ((index % total) + total) % total
}

function next() {
  go(active.value + 1)
}

function prev() {
  go(active.value - 1)
}

function startAutoplay() {
  stopAutoplay()
  if (slides.value.length < 2) return
  timer = setInterval(() => {
    if (!paused.value) next()
  }, 7000)
}

function stopAutoplay() {
  if (timer !== undefined) {
    clearInterval(timer)
    timer = undefined
  }
}

onMounted(startAutoplay)
onBeforeUnmount(stopAutoplay)
</script>

<template>
  <div class="home-page">
    <section
      class="hero-carousel"
      :aria-label="t('home.carouselAria')"
      @mouseenter="paused = true"
      @mouseleave="paused = false"
      @focusin="paused = true"
      @focusout="paused = false"
    >
      <div class="hero-track" :style="{ transform: `translateX(-${active * 100}%)` }">
        <article v-for="slide in slides" :key="slide.id" class="hero-slide" :data-kind="slide.kind">
          <template v-if="slide.kind === 'intro'">
            <div class="hero">
              <div class="hero-copy">
                <span class="eyebrow">FUTURE ✦ AGENT ✦ LOCAL</span>
                <h1>{{ t("home.heroTitle") }}</h1>
                <p>{{ t("home.heroSubtitle") }}</p>
                <div class="hero-actions">
                  <RouterLink class="primary-action" to="/training">{{ t("home.startTraining") }}</RouterLink>
                  <RouterLink class="secondary-action" to="/help/guide.html">{{ t("home.readGuide") }}</RouterLink>
                </div>
              </div>
              <div class="hero-visual">
                <div class="visual-grid" />
                <div class="orbit orbit-one" />
                <div class="orbit orbit-two" />
                <img src="/assets/home-logo.webp" alt="Next Trainer" />
              </div>
            </div>
          </template>
          <template v-else>
            <a class="hero-poster" :href="slide.href" target="_blank" rel="noopener noreferrer">
              <img :src="slide.src" :alt="slide.alt" />
              <div class="poster-meta">
                <span class="poster-tag">{{ slide.badge }}</span>
                <span class="poster-tag">{{ slide.caption }}</span>
              </div>
            </a>
          </template>
        </article>
      </div>

      <div v-if="slides.length > 1" class="hero-controls">
        <button type="button" class="hero-nav" :aria-label="t('home.carouselPrev')" @click="prev">‹</button>
        <div class="hero-dots" role="tablist" :aria-label="t('home.carouselAria')">
          <button
            v-for="(slide, index) in slides"
            :key="slide.id"
            type="button"
            class="hero-dot"
            role="tab"
            :aria-selected="active === index"
            :aria-label="t('home.carouselDot', { n: index + 1 })"
            @click="go(index)"
          />
        </div>
        <button type="button" class="hero-nav" :aria-label="t('home.carouselNext')" @click="next">›</button>
      </div>
    </section>

    <nav class="portal-strip" :aria-label="t('home.portalAria')" data-layout="compact-v3">
      <RouterLink v-for="(portal, index) in portals" :key="portal.to" :to="portal.to" class="portal-chip" :data-tone="portal.tone">
        <span class="portal-index">0{{ index + 1 }}</span>
        <span class="portal-title">{{ portal.title }}</span>
        <span class="portal-go">{{ t("home.enter") }} →</span>
      </RouterLink>
    </nav>
    <section class="status-strip">
      <span><i class="status-dot" /> {{ t("home.status.local") }}</span>
      <span>{{ t("home.status.vue") }}</span>
      <span>{{ t("home.status.models") }}</span>
    </section>
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
