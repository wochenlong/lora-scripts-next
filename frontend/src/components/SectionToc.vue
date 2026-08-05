<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from "vue"
import { useI18n } from "vue-i18n"

export interface TocSection { id: string; title: string }

const props = defineProps<{ sections: TocSection[] }>()
const { t } = useI18n()
const open = ref(false)
const activeId = ref("")
let observer: IntersectionObserver | undefined

function anchorId(id: string) { return `sec-${id}` }

function navigate(id: string) {
  document.getElementById(anchorId(id))?.scrollIntoView({ behavior: "smooth", block: "start" })
  open.value = false
}

function observe() {
  observer?.disconnect()
  if (typeof IntersectionObserver === "undefined") return
  observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (entry.isIntersecting) activeId.value = entry.target.id.replace(/^sec-/, "")
    }
  }, { rootMargin: "-15% 0px -75% 0px" })
  for (const section of props.sections) {
    const el = document.getElementById(anchorId(section.id))
    if (el) observer.observe(el)
  }
}

onMounted(observe)
watch(() => props.sections, observe)
onBeforeUnmount(() => observer?.disconnect())
</script>

<template>
  <nav class="section-toc" :class="{ open }" :aria-label="t('training.toc.title')" @mouseenter="open = true" @mouseleave="open = false">
    <button class="toc-seam" :aria-label="t('training.toc.expand')" @click="open = !open">
      <span class="toc-seam-arrow" aria-hidden="true">→</span>
      <span class="toc-seam-label">{{ t("training.toc.title") }}</span>
    </button>
    <div class="toc-panel">
      <header>
        <span>{{ t("training.toc.title") }}</span>
        <button :aria-label="t('training.toc.collapse')" @click="open = false">←</button>
      </header>
      <button v-for="section in sections" :key="section.id" class="toc-item" :class="{ active: activeId === section.id }" @click="navigate(section.id)">{{ section.title }}</button>
    </div>
  </nav>
</template>
