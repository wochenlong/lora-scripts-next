<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { useI18n } from "vue-i18n"
import { enginesApi, type EngineStatus } from "../api/engines"
import DownloadSourcesPanel from "../components/DownloadSourcesPanel.vue"
import {
  ENGINE_CATALOG,
  PRODUCT_DEFAULT_ENGINE,
  type EngineDefinition,
} from "../engines/catalog"
import { readEnginePrefs, writeEnginePrefs } from "../engines/prefs"
import type { TrainingEngine } from "../training/modules"

const { t } = useI18n()
const loadingId = ref<string | null>(null)
const statuses = ref<Record<string, EngineStatus>>({})
const logs = ref<string[]>([])
const progress = ref(0)
const phase = ref("")
const activeConsoleId = ref<string | null>(null)
const manageId = ref<string | null>(null)
const menuId = ref<string | null>(null)
const rememberLast = ref(readEnginePrefs().rememberLast)
const downloadPanel = ref<{ openAdvanced: () => void } | null>(null)
let timer: number | undefined
let logSource: EventSource | undefined
let progressSource: EventSource | undefined

const MANAGED_ENGINES = new Set(["anima-fast", "musubi"])
const INSTALL_STREAM_BASE: Record<string, string> = {
  "anima-fast": "/api/engines/anima-fast/install",
  musubi: "/api/engines/musubi/install",
}

function isManaged(id: string) {
  return MANAGED_ENGINES.has(id)
}

function isProductDefault(id: string) {
  return id === PRODUCT_DEFAULT_ENGINE
}

function workingStatus(id: string): EngineStatus | undefined {
  const status = statuses.value[id]
  return status && ["installing", "auditing"].includes(status.state) ? status : undefined
}

const cards = computed(() => ENGINE_CATALOG.map((engine) => {
  const status = statuses.value[engine.id] || defaultStatus(engine)
  return { engine, status }
}))

const manageCard = computed(() => cards.value.find((card) => card.engine.id === manageId.value) || null)

function defaultStatus(engine: EngineDefinition): EngineStatus {
  if (engine.kind === "builtin") return { id: engine.id, state: "ready", featureEnabled: true }
  if (engine.kind === "planned") return { id: engine.id, state: "coming_soon", featureEnabled: false }
  return { id: engine.id, state: "unknown", featureEnabled: true }
}

function closeStreams() {
  logSource?.close()
  progressSource?.close()
  logSource = undefined
  progressSource = undefined
}

function stopPolling() {
  if (timer !== undefined) {
    window.clearInterval(timer)
    timer = undefined
  }
}

function attachStreams(engineId: string, taskId: string, logUrl?: string, progressUrl?: string) {
  closeStreams()
  activeConsoleId.value = engineId
  manageId.value = engineId
  const base = INSTALL_STREAM_BASE[engineId] || INSTALL_STREAM_BASE["anima-fast"]
  logSource = new EventSource(logUrl || `${base}/log/stream/${taskId}`)
  logSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.text) logs.value.push(data.text)
      if (data.done) logSource?.close()
    } catch {
      logs.value.push(event.data)
    }
  }
  progressSource = new EventSource(progressUrl || `${base}/progress/stream/${taskId}`)
  progressSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.type === "progress") {
        progress.value = Number(data.percent || 0)
        phase.value = data.message || data.phase || ""
      }
      if (data.done || data.type === "done") progressSource?.close()
    } catch { /* ignore */ }
  }
}

async function refresh(reportError = true) {
  try {
    const list = await enginesApi.list()
    const next: Record<string, EngineStatus> = {}
    for (const item of list) next[item.id] = item
    statuses.value = next
    const active = activeConsoleId.value ? workingStatus(activeConsoleId.value) : undefined
    const working = active ?? [...MANAGED_ENGINES].map((id) => workingStatus(id)).find(Boolean)
    if (working?.facts?.task_id && !logSource) attachStreams(working.id, working.facts.task_id)
    if (!working) stopPolling()
  } catch (error) {
    if (reportError) ElMessage.error(error instanceof Error ? error.message : t("settings.engines.msg.statusFail"))
  }
}

async function install(engineId: TrainingEngine, forceReinstall = false) {
  menuId.value = null
  try {
    await ElMessageBox.confirm(
      forceReinstall ? t("settings.engines.confirm.reinstall") : t(`settings.engines.confirm.install.${engineId}`),
      forceReinstall ? t("settings.engines.actions.reinstall") : t("settings.engines.actions.install"),
      { type: "warning" },
    )
    loadingId.value = engineId
    logs.value = []
    progress.value = 0
    phase.value = ""
    const result = forceReinstall ? await enginesApi.repair(engineId) : await enginesApi.install(engineId)
    if (result.alreadyReady) {
      if (result.status) statuses.value = { ...statuses.value, [engineId]: result.status }
      ElMessage.success(t("settings.engines.msg.ready"))
      return
    }
    if (result.taskId) {
      attachStreams(engineId, result.taskId, result.logStream, result.progressStream)
      if (!timer) timer = window.setInterval(() => refresh(false), 2000)
    }
    await refresh(false)
    ElMessage.success(t("settings.engines.msg.started"))
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error instanceof Error ? error.message : t("settings.engines.msg.fail"))
    }
  } finally {
    loadingId.value = null
  }
}

async function uninstall(engineId: TrainingEngine) {
  menuId.value = null
  try {
    await ElMessageBox.confirm(t("settings.engines.confirm.uninstall"), t("settings.engines.actions.uninstall"), { type: "warning" })
    loadingId.value = engineId
    const status = await enginesApi.uninstall(engineId)
    statuses.value = { ...statuses.value, [engineId]: status }
    logs.value = []
    progress.value = 0
    if (manageId.value === engineId) manageId.value = null
    ElMessage.success(t("settings.engines.msg.uninstalled"))
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error instanceof Error ? error.message : t("settings.engines.msg.fail"))
    }
  } finally {
    loadingId.value = null
  }
}

function saveRemember() {
  const prefs = readEnginePrefs()
  prefs.rememberLast = rememberLast.value
  writeEnginePrefs(prefs)
  ElMessage.success(t("settings.engines.msg.prefsSaved"))
}

function openManage(engineId: string) {
  menuId.value = null
  manageId.value = engineId
}

function closeManage() {
  manageId.value = null
}

function toggleMenu(engineId: string) {
  menuId.value = menuId.value === engineId ? null : engineId
}

function runtimePath(status: EngineStatus) {
  return status.runtime?.animaRoot || status.runtime?.musubiRoot || status.runtime?.environmentPath || ""
}

async function copyPath(status: EngineStatus) {
  menuId.value = null
  const path = runtimePath(status)
  if (!path) {
    ElMessage.warning(t("settings.engines.msg.noPath"))
    return
  }
  try {
    await navigator.clipboard.writeText(path)
    ElMessage.success(t("settings.engines.msg.pathCopied"))
  } catch {
    ElMessage.info(path)
  }
}

function displayVersion(engine: EngineDefinition, status: EngineStatus) {
  return status.runtime?.version || engine.version
}

function onDocClick(event: MouseEvent) {
  const target = event.target as HTMLElement | null
  if (!target?.closest(".engine-more")) menuId.value = null
}

onMounted(async () => {
  document.addEventListener("click", onDocClick)
  await refresh()
  const working = [...MANAGED_ENGINES].map((id) => workingStatus(id)).find(Boolean)
  if (working) timer = window.setInterval(() => refresh(false), 2000)
})

onBeforeUnmount(() => {
  document.removeEventListener("click", onDocClick)
  stopPolling()
  closeStreams()
})
</script>

<template>
  <div class="engines-settings engines-manager">
    <header class="engines-page-head">
      <div>
        <h2>{{ t("settings.engines.title") }}</h2>
        <p>{{ t("settings.engines.leadShort") }}</p>
      </div>
    </header>

    <section class="engines-toolbar" :aria-label="t('settings.engines.toolbarAria')">
      <label class="toolbar-field">
        <span>{{ t("settings.engines.defaultEngine.label") }}</span>
        <div class="toolbar-default">
          <select disabled :value="PRODUCT_DEFAULT_ENGINE" :aria-label="t('settings.engines.defaultEngine.label')">
            <option :value="PRODUCT_DEFAULT_ENGINE">{{ t("settings.engines.catalog.kohya.name") }}</option>
          </select>
          <i class="engine-badge is-default">{{ t("settings.engines.badges.currentDefault") }}</i>
        </div>
      </label>

      <label class="toolbar-remember">
        <input v-model="rememberLast" type="checkbox" @change="saveRemember">
        <span>
          <b>{{ t("settings.engines.rememberLast.label") }}</b>
          <small>{{ t("settings.engines.rememberLast.hintShort") }}</small>
        </span>
      </label>

      <label class="toolbar-field toolbar-source">
        <span>{{ t("settings.engines.downloadSources.title") }}</span>
        <DownloadSourcesPanel ref="downloadPanel" compact />
      </label>
    </section>

    <div class="engines-list-head">
      <h3>{{ t("settings.engines.listTitle") }}</h3>
    </div>

    <div class="engine-rows">
      <article
        v-for="card in cards"
        :key="card.engine.id"
        class="engine-row"
        :data-engine="card.engine.id"
        :data-state="card.status.state"
      >
        <div class="engine-row-main">
          <div class="engine-logo" :data-engine="card.engine.id">{{ card.engine.mark }}</div>
          <div class="engine-copy">
            <div class="engine-title-line">
              <h4>{{ t(card.engine.nameKey) }}</h4>
              <span v-if="isProductDefault(card.engine.id)" class="engine-badge is-default">{{ t("settings.engines.badges.currentDefault") }}</span>
              <span v-else-if="card.status.state === 'ready'" class="engine-badge is-ready">{{ t("settings.engines.badges.installed") }}</span>
              <span v-else-if="['installing', 'auditing'].includes(card.status.state)" class="engine-badge is-busy">{{ t(`settings.engines.state.${card.status.state}`) }}</span>
              <span v-else-if="card.status.state === 'broken'" class="engine-badge is-broken">{{ t("settings.engines.state.broken") }}</span>
              <span v-else class="engine-badge is-missing">{{ t("settings.engines.badges.notInstalled") }}</span>
              <span v-if="card.engine.recommended && !isProductDefault(card.engine.id)" class="engine-badge is-rec">{{ t("settings.engines.badges.recommended") }}</span>
            </div>
            <p>{{ t(card.engine.summaryKey) }}</p>
            <ul class="engine-tags">
              <li v-for="tag in card.engine.tags" :key="tag">{{ t(`settings.engines.tags.${tag}`) }}</li>
            </ul>
          </div>
        </div>

        <div class="engine-meta-cols">
          <div>
            <small>{{ t("settings.engines.meta.version") }}</small>
            <b>{{ displayVersion(card.engine, card.status) }}</b>
          </div>
          <div>
            <small>{{ t("settings.engines.meta.updated") }}</small>
            <b>{{ card.engine.updatedAt }}</b>
          </div>
        </div>

        <div class="engine-row-actions">
          <template v-if="isProductDefault(card.engine.id)">
            <div class="engine-default-lock">
              <b>{{ t("settings.engines.badges.currentDefault") }}</b>
              <small>{{ t("settings.engines.defaultEngine.locked") }}</small>
            </div>
          </template>
          <template v-else-if="isManaged(card.engine.id)">
            <button
              v-if="card.status.state === 'ready' || card.status.state === 'broken' || card.status.state === 'installed_unverified'"
              type="button"
              class="secondary-action engine-primary"
              :disabled="loadingId === card.engine.id"
              @click="openManage(card.engine.id)"
            >
              {{ t("settings.engines.actions.manage") }}
            </button>
            <button
              v-else
              type="button"
              class="primary-action engine-primary"
              :disabled="loadingId === card.engine.id || ['installing', 'auditing', 'coming_soon'].includes(card.status.state) || !card.status.featureEnabled"
              @click="install(card.engine.id, false)"
            >
              {{ ["installing", "auditing"].includes(card.status.state) ? t("settings.engines.actions.installing") : t("settings.engines.actions.install") }}
            </button>

            <div class="engine-more">
              <button type="button" class="engine-more-btn" :aria-label="t('settings.engines.actions.more')" @click.stop="toggleMenu(card.engine.id)">⋯</button>
              <div v-if="menuId === card.engine.id" class="engine-more-menu" role="menu">
                <button type="button" role="menuitem" @click="refresh()">{{ t("settings.engines.actions.refresh") }}</button>
                <button type="button" role="menuitem" :disabled="!runtimePath(card.status)" @click="copyPath(card.status)">{{ t("settings.engines.actions.copyPath") }}</button>
                <button
                  type="button"
                  role="menuitem"
                  :disabled="loadingId === card.engine.id || !['broken', 'installed_unverified', 'ready'].includes(card.status.state)"
                  @click="install(card.engine.id, true)"
                >
                  {{ t("settings.engines.actions.reinstall") }}
                </button>
                <button
                  type="button"
                  role="menuitem"
                  class="is-danger"
                  :disabled="loadingId === card.engine.id || ['installing', 'auditing', 'not_installed', 'coming_soon', 'unknown'].includes(card.status.state)"
                  @click="uninstall(card.engine.id)"
                >
                  {{ t("settings.engines.actions.uninstall") }}
                </button>
                <button type="button" role="menuitem" @click="openManage(card.engine.id)">{{ t("settings.engines.actions.viewLog") }}</button>
              </div>
            </div>
          </template>
        </div>
      </article>
    </div>

    <p class="engines-end">{{ t("settings.engines.end") }}</p>

    <Teleport to="body">
      <div v-if="manageCard" class="ds-modal-backdrop" @click.self="closeManage">
        <section class="ds-sheet engine-manage-modal" role="dialog">
          <header class="ds-sheet-head">
            <div>
              <p class="ds-kicker">{{ t(manageCard.engine.nameKey) }}</p>
              <h3>{{ t("settings.engines.actions.manage") }}</h3>
              <p class="ds-sheet-lead">{{ t(`settings.engines.hint.${manageCard.status.state}`) }}</p>
            </div>
            <button type="button" class="ds-close" :aria-label="t('settings.engines.downloadSources.close')" @click="closeManage">×</button>
          </header>
          <p v-if="runtimePath(manageCard.status)" class="engine-path">
            <span>{{ t("settings.engines.meta.path") }}</span>
            <code>{{ runtimePath(manageCard.status) }}</code>
          </p>
          <div class="engine-console">
            <header>
              <span>{{ phase || t("settings.engines.console.idle") }}</span>
              <b>{{ progress }}%</b>
            </header>
            <div class="install-progress"><i :style="{ width: `${progress}%` }" /></div>
            <pre>{{ logs.length && activeConsoleId === manageCard.engine.id ? logs.join("\n") : t("settings.engines.console.waiting") }}</pre>
          </div>
        </section>
      </div>
    </Teleport>
  </div>
</template>
