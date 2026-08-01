<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { useRoute } from "vue-router"
import { useI18n } from "vue-i18n"
import { Cpu, DataLine, FolderOpened, Menu as MenuIcon, QuestionFilled, Setting } from "@element-plus/icons-vue"
import { storeToRefs } from "pinia"
import { useAppStore } from "../stores/app"

const route = useRoute()
const { t } = useI18n()
const mobileOpen = ref(false)
const appStore = useAppStore()
const { version } = storeToRefs(appStore)

const sections = [
  { key: "training", to: "/training", icon: Cpu, match: ["/training", "/lora/", "/dreambooth/"] },
  { key: "dataset", to: "/dataset", icon: FolderOpened, match: ["/dataset", "/tagger.html", "/native-tageditor.html", "/dataset-editor.html", "/tageditor.html"] },
  { key: "tasks", to: "/tasks", icon: DataLine, match: ["/tasks", "/task.html", "/tensorboard.html"] },
  { key: "settings", to: "/settings", icon: Setting, match: ["/settings", "/other/"] },
] as const

const currentPath = computed(() => route.path)
function isActive(match: readonly string[]) {
  return match.some((prefix) => currentPath.value.startsWith(prefix))
}
onMounted(() => appStore.loadVersion())
</script>

<template>
  <div class="app-shell">
    <header class="mobile-header">
      <button class="icon-button" :aria-label="t('nav.openNav')" @click="mobileOpen = !mobileOpen"><el-icon><MenuIcon /></el-icon></button>
      <RouterLink class="mobile-brand" to="/">{{ t("app.brand") }}</RouterLink>
    </header>
    <button v-if="mobileOpen" class="sidebar-mask" :aria-label="t('nav.closeNav')" @click="mobileOpen = false" />
    <aside class="sidebar" :class="{ 'is-open': mobileOpen }">
      <RouterLink class="brand" to="/" @click="mobileOpen = false">
        <span class="brand-mark">L</span><span><strong>{{ t("app.brand") }}</strong><small>{{ version ? `v${version}` : "Vue 3 workspace" }}</small></span>
      </RouterLink>
      <nav class="navigation" :aria-label="t('nav.mainAria')">
        <RouterLink v-for="section in sections" :key="section.key" :to="section.to" class="nav-link" :class="{ active: isActive(section.match) }" @click="mobileOpen = false">
          <el-icon><component :is="section.icon" /></el-icon><span>{{ t(`nav.${section.key}`) }}</span>
        </RouterLink>
      </nav>
      <footer class="sidebar-footer">
        <RouterLink to="/help/guide.html" class="nav-link help-link" @click="mobileOpen = false">
          <el-icon><QuestionFilled /></el-icon><span>{{ t("nav.help") }}</span>
        </RouterLink>
        <a href="https://github.com/wochenlong/lora-scripts-next" target="_blank" rel="noreferrer" class="github-link">GitHub</a>
      </footer>
    </aside>
    <main class="app-content"><RouterView /></main>
  </div>
</template>
