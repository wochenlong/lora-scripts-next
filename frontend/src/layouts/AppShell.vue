<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { useRoute } from "vue-router"
import { useI18n } from "vue-i18n"
import { Cpu, DataLine, FolderOpened, Menu as MenuIcon, QuestionFilled, Setting, Box } from "@element-plus/icons-vue"
import { storeToRefs } from "pinia"
import { useAppStore } from "../stores/app"
import { useTasksStore } from "../stores/tasks"

const route = useRoute()
const { t } = useI18n()
const mobileOpen = ref(false)
const appStore = useAppStore()
const tasksStore = useTasksStore()
const { version } = storeToRefs(appStore)
const { showNavBadge, navBadgeCount, activeCount } = storeToRefs(tasksStore)
const versionLabel = computed(() => {
  if (!version.value) return "beta"
  const pre = /(?:alpha|beta|rc)/i.test(version.value)
  return pre ? `v${version.value} · ${t("app.prerelease")}` : `v${version.value}`
})

const sections = [
  { key: "training", to: "/training", icon: Cpu, match: ["/training", "/lora/", "/dreambooth/"] },
  { key: "dataset", to: "/dataset", icon: FolderOpened, match: ["/dataset", "/tagger.html", "/native-tageditor.html", "/dataset-editor.html", "/tageditor.html"] },
  { key: "tasks", to: "/tasks", icon: DataLine, match: ["/tasks", "/task.html", "/tensorboard.html"] },
  { key: "manage", to: "/products", icon: Box, match: ["/products"] },
  { key: "settings", to: "/settings", icon: Setting, match: ["/settings", "/other/"] },
] as const

const currentPath = computed(() => route.path)
function isActive(match: readonly string[]) {
  return match.some((prefix) => currentPath.value.startsWith(prefix))
}

let tasksPoll: number | undefined

function clearAttentionIfOnTasks() {
  const path = route.path
  if (path.startsWith("/tasks") || path.startsWith("/task.html") || path.startsWith("/tensorboard.html")) {
    tasksStore.clearAttention()
  }
}

onMounted(() => {
  appStore.loadVersion()
  void tasksStore.refresh({ silent: true })
  tasksPoll = window.setInterval(() => tasksStore.refresh({ silent: true }), 4000)
  clearAttentionIfOnTasks()
})

watch(() => route.path, clearAttentionIfOnTasks)
onBeforeUnmount(() => {
  if (tasksPoll !== undefined) window.clearInterval(tasksPoll)
})
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
        <span class="brand-mark">N</span><span><strong>{{ t("app.brand") }}</strong><small>{{ versionLabel }}</small></span>
      </RouterLink>
      <nav class="navigation" :aria-label="t('nav.mainAria')">
        <RouterLink
          v-for="section in sections"
          :key="section.key"
          :to="section.to"
          class="nav-link"
          :class="{ active: isActive(section.match) }"
          :aria-label="section.key === 'tasks' && showNavBadge ? t('nav.tasksWithBadge', { n: navBadgeCount }) : undefined"
          @click="mobileOpen = false"
        >
          <el-icon><component :is="section.icon" /></el-icon>
          <span class="nav-label">
            {{ t(`nav.${section.key}`) }}
            <i
              v-if="section.key === 'tasks' && showNavBadge"
              class="nav-badge"
              :class="{ 'nav-badge-dot': activeCount === 0 }"
              :title="activeCount > 0 ? t('nav.tasksBadgeHint', { n: activeCount }) : t('nav.tasksBadgeUnread')"
            >{{ activeCount > 0 ? (activeCount > 9 ? "9+" : activeCount) : "" }}</i>
          </span>
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
