<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { useI18n } from "vue-i18n"
import { ArrowLeft, ArrowRight } from "@element-plus/icons-vue"

export interface TocSection { id: string; title: string }

const props = defineProps<{ sections: TocSection[] }>()
const { t } = useI18n()
const hovered = ref(false)
const pinned = ref(false)
const activeId = ref("")
let observer: IntersectionObserver | undefined

const hasSections = computed(() => props.sections.length > 0)
const open = computed(() => hasSections.value && (hovered.value || pinned.value))

function anchorId(id: string) { return `sec-${id}` }

function togglePinned() {
  pinned.value = !pinned.value
}

function collapseNow() {
  pinned.value = false
  hovered.value = false
}

function navigate(id: string) {
  activeId.value = id
  document.getElementById(anchorId(id))?.scrollIntoView({ behavior: "smooth", block: "start" })
}

function observe() {
  observer?.disconnect()
  if (typeof IntersectionObserver === "undefined") {
    if (!activeId.value && props.sections[0]) activeId.value = props.sections[0].id
    return
  }
  observer = new IntersectionObserver((entries) => {
    const hit = entries
      .filter((entry) => entry.isIntersecting)
      .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)[0]
    if (hit?.target instanceof HTMLElement) {
      activeId.value = hit.target.id.replace(/^sec-/, "")
    }
  }, { rootMargin: "-15% 0px -75% 0px", threshold: [0, 0.12, 0.4] })
  for (const section of props.sections) {
    const el = document.getElementById(anchorId(section.id))
    if (el) observer.observe(el)
  }
  if (!activeId.value && props.sections[0]) activeId.value = props.sections[0].id
}

onMounted(observe)
watch(() => props.sections, observe)
onBeforeUnmount(() => {
  observer?.disconnect()
})
</script>

<template>
  <aside
    class="section-toc schema-toc"
    :class="{ open, collapsed: !open, empty: !hasSections }"
    :aria-label="t('training.toc.title')"
    @mouseenter="hovered = true"
    @mouseleave="hovered = false"
  >
    <button
      type="button"
      class="toc-seam schema-toc-seam"
      :title="t('training.toc.expand')"
      :aria-label="t('training.toc.expand')"
      :aria-expanded="open ? 'true' : 'false'"
      :disabled="!hasSections"
      @click="togglePinned"
    >
      <el-icon class="schema-toc-seam-icon" :size="12"><ArrowRight /></el-icon>
    </button>
    <div
      class="toc-panel schema-toc-panel"
      :aria-hidden="open ? 'false' : 'true'"
    >
      <header class="schema-toc-head">
        <p class="schema-toc-caption">{{ t("training.toc.title") }}</p>
        <button
          type="button"
          class="schema-toc-toggle icon-btn"
          :title="t('training.toc.collapse')"
          :aria-label="t('training.toc.collapse')"
          @click="collapseNow"
        >
          <el-icon :size="14"><ArrowLeft /></el-icon>
        </button>
      </header>
      <div class="schema-toc-list">
        <button
          v-for="section in sections"
          :key="section.id"
          type="button"
          class="toc-item schema-toc-tab"
          :class="{ active: activeId === section.id }"
          :title="section.title"
          @click="navigate(section.id)"
        >
          <i aria-hidden="true"></i>
          <span>{{ section.title }}</span>
        </button>
      </div>
    </div>
  </aside>
</template>
