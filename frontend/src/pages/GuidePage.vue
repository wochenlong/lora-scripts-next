<script setup lang="ts">
import { useI18n } from "vue-i18n"

const { t } = useI18n()
</script>

<template>
  <article class="content-page">
    <header class="content-hero content-hero-split"><div><span class="eyebrow">GETTING STARTED</span><h1>{{ t("guide.title") }}</h1><p>{{ t("guide.subtitle") }}</p></div><img src="/assets/guide-mascot.webp" :alt="t('guide.mascotAlt')"></header>
    <section><h2>{{ t("guide.step1Title") }}</h2><i18n-t keypath="guide.step1" tag="p" scope="global"><template #ext><code>.txt</code></template><template #tagger><RouterLink to="/dataset/tagger">{{ t("guide.link.tagger") }}</RouterLink></template><template #editor><RouterLink to="/dataset/editor">{{ t("guide.link.editor") }}</RouterLink></template></i18n-t></section>
    <section><h2>{{ t("guide.step2Title") }}</h2><div class="content-cards"><div><h3>{{ t("guide.loraTitle") }}</h3><i18n-t keypath="guide.loraDesc" tag="p" scope="global"><template #page><RouterLink to="/training">{{ t("guide.link.trainingPage") }}</RouterLink></template></i18n-t></div><div><h3>{{ t("guide.finetuneTitle") }}</h3><i18n-t keypath="guide.finetuneDesc" tag="p" scope="global"><template #anima><RouterLink to="/training?model=anima&engine=kohya&target=finetune">{{ t("guide.link.animaFinetune") }}</RouterLink></template><template #dreambooth><RouterLink to="/dreambooth/index.html">Dreambooth</RouterLink></template></i18n-t></div></div></section>
    <section><h2>{{ t("guide.step3Title") }}</h2><ol><li>{{ t("guide.step3a") }}</li><li>{{ t("guide.step3b") }}</li><li>{{ t("guide.step3c") }}</li></ol></section>
    <section><h2>{{ t("guide.step4Title") }}</h2><i18n-t keypath="guide.step4" tag="p" scope="global"><template #tasks><RouterLink to="/tasks">{{ t("guide.link.tasks") }}</RouterLink></template><template #tensorboard><RouterLink to="/tensorboard.html">TensorBoard</RouterLink></template></i18n-t></section>
    <section><h2>{{ t("guide.migrateTitle") }}</h2><ul><li>{{ t("guide.migrate1") }}</li><li>{{ t("guide.migrate2") }}</li><li>{{ t("guide.migrate3") }}</li></ul></section>
  </article>
</template>
