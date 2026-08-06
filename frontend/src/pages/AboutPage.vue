<script setup lang="ts">
import { useI18n } from "vue-i18n"

const { t } = useI18n()

const credits = [
  {
    name: "Akegarasu / lora-scripts",
    href: "https://github.com/Akegarasu/lora-scripts",
    noteKey: "about.credits.akegarasu",
  },
  {
    name: "kohya-ss / sd-scripts",
    href: "https://github.com/kohya-ss/sd-scripts",
    noteKey: "about.credits.kohya",
  },
  {
    name: "sorryhyun / anima_lora",
    href: "https://github.com/sorryhyun/anima_lora",
    noteKey: "about.credits.animaFast",
  },
  {
    name: "KohakuBlueleaf / LyCORIS",
    href: "https://github.com/KohakuBlueleaf/LyCORIS",
    noteKey: "about.credits.lycoris",
  },
  {
    name: "SmilingWolf / WD Tagger",
    href: "https://huggingface.co/SmilingWolf/wd-v1-4-convnextv2-tagger-v2",
    noteKey: "about.credits.tagger",
  },
  {
    name: "shigma / schemastery",
    href: "https://github.com/shigma/schemastery",
    noteKey: "about.credits.schemastery",
  },
] as const
</script>

<template>
  <article class="content-page">
    <header class="content-hero content-hero-split">
      <div>
        <span class="eyebrow">ABOUT</span>
        <h1>Next Trainer</h1>
        <p>{{ t("about.tagline") }}</p>
      </div>
      <img class="about-logo" src="/assets/home-logo.webp" alt="Next Trainer" />
    </header>

    <section>
      <h2>{{ t("about.projectTitle") }}</h2>
      <i18n-t keypath="about.projectDesc" tag="p" scope="global">
        <template #schemastery>
          <a href="https://github.com/shigma/schemastery" target="_blank" rel="noreferrer">Schemastery</a>
        </template>
      </i18n-t>
    </section>

    <section>
      <h2>{{ t("about.creditsTitle") }}</h2>
      <p>{{ t("about.creditsIntro") }}</p>
      <ul class="about-credits">
        <li v-for="item in credits" :key="item.href">
          <a :href="item.href" target="_blank" rel="noreferrer">{{ item.name }}</a>
          <span>{{ t(item.noteKey) }}</span>
        </li>
      </ul>
      <p>
        <i18n-t keypath="about.creditsNotice" tag="span" scope="global">
          <template #notice>
            <a href="https://github.com/wochenlong/lora-scripts-next/blob/dev/NOTICE.md" target="_blank" rel="noreferrer">NOTICE.md</a>
          </template>
          <template #license>
            <a href="https://github.com/wochenlong/lora-scripts-next/blob/dev/LICENSE" target="_blank" rel="noreferrer">LICENSE</a>
          </template>
        </i18n-t>
      </p>
    </section>

    <section>
      <h2>{{ t("about.feedbackTitle") }}</h2>
      <i18n-t keypath="about.feedbackDesc" tag="p" scope="global">
        <template #issues>
          <a href="https://github.com/wochenlong/lora-scripts-next/issues" target="_blank" rel="noreferrer">GitHub Issues</a>
        </template>
      </i18n-t>
    </section>

    <section>
      <h2>{{ t("about.linksTitle") }}</h2>
      <div class="content-links">
        <a href="https://github.com/wochenlong/lora-scripts-next" target="_blank" rel="noreferrer">{{ t("about.source") }}</a>
        <a href="https://github.com/wochenlong/lora-scripts-next/releases" target="_blank" rel="noreferrer">{{ t("about.releases") }}</a>
        <a href="https://github.com/wochenlong/lora-scripts-next/issues" target="_blank" rel="noreferrer">{{ t("about.issues") }}</a>
      </div>
    </section>
  </article>
</template>
