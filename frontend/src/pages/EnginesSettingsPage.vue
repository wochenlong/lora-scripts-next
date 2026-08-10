<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { useI18n } from "vue-i18n"
import { enginesApi, type EngineStatus } from "../api/engines"
import { ENGINE_CATALOG, type EngineDefinition } from "../engines/catalog"
import { readEnginePrefs, writeEnginePrefs } from "../engines/prefs"
import type { TrainingEngine } from "../training/modules"

const { t } = useI18n()
const loadingId = ref<string | null>(null)
const statuses = ref<Record<string, EngineStatus>>({})
const logs = ref<string[]>([])
const progress = ref(0)
const phase = ref("")
const activeConsoleId = ref<string | null>(null)
const rememberLast = ref(readEnginePrefs().rememberLast)
let timer: number | undefined
let logSource: EventSource | undefined
let progressSource: EventSource | undefined

const MANAGED_ENGINES = new Set(["anima-fast", "musubi"])
const INSTALL_STREAM_BASE: Record<string, string> = {
  "anima-fast": "/api/plugins/anima-lora/install",
  musubi: "/api/plugins/musubi/install",
}

function isManaged(id: string) {
  return MANAGED_ENGINES.has(id)
}

function workingStatus(id: string): EngineStatus | undefined {
  const status = statuses.value[id]
  return status && ["installing", "auditing"].includes(status.state) ? status : undefined
}

const cards = computed(() => ENGINE_CATALOG.map((engine) => ({
  engine,
  status: statuses.value[engine.id] || defaultStatus(engine),
})))

function defaultStatus(engine: EngineDefinition): EngineStatus {
  if (engine.kind === "builtin") return { id: engine.id, state: "ready", featureEnabled: true }
  if (engine.kind === "planned") return { id: engine.id, state: "coming_soon", featureEnabled: false }
  return { id: engine.id, state: "unknown", featureEnabled: true }
}

function stateLabel(state: string) {
  const key = `settings.engines.state.${state}`
  const translated = t(key)
  return translated === key ? state : translated
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
    } catch { /* ignore malformed chunks */ }
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
  try {
    await ElMessageBox.confirm(t("settings.engines.confirm.uninstall"), t("settings.engines.actions.uninstall"), { type: "warning" })
    loadingId.value = engineId
    const status = await enginesApi.uninstall(engineId)
    statuses.value = { ...statuses.value, [engineId]: status }
    logs.value = []
    progress.value = 0
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

onMounted(async () => {
  await refresh()
  const working = [...MANAGED_ENGINES].map((id) => workingStatus(id)).find(Boolean)
  if (working) {
    timer = window.setInterval(() => refresh(false), 2000)
  }
})

onBeforeUnmount(() => {
  stopPolling()
  closeStreams()
})
</script>

<template>
  <div class="engines-settings">
    <section class="settings-card">
      <h2>{{ t("settings.engines.title") }}</h2>
      <p class="engines-lead">{{ t("settings.engines.lead") }}</p>
      <div class="engines-policy">
        <strong>{{ t("settings.engines.defaultPolicy.title") }}</strong>
        <p>{{ t("settings.engines.defaultPolicy.body") }}</p>
      </div>
      <label class="engines-toggle">
        <input v-model="rememberLast" type="checkbox" @change="saveRemember">
        <span>
          <b>{{ t("settings.engines.rememberLast.label") }}</b>
          <small>{{ t("settings.engines.rememberLast.hint") }}</small>
        </span>
      </label>
    </section>

    <section
      v-for="card in cards"
      :key="card.engine.id"
      class="settings-card engine-card"
      :data-engine="card.engine.id"
      :data-state="card.status.state"
    >
      <header class="engine-card-header">
        <div>
          <h2>{{ t(card.engine.nameKey) }}</h2>
          <p>{{ t(card.engine.summaryKey) }}</p>
        </div>
        <span class="engine-state-pill" :data-state="card.status.state">{{ stateLabel(card.status.state) }}</span>
      </header>

      <ul class="engine-meta" v-if="card.engine.sizeHintKey || card.engine.requiresGpu || card.engine.kind === 'builtin'">
        <li v-if="card.engine.kind === 'builtin'">{{ t("settings.engines.meta.builtin") }}</li>
        <li v-if="card.engine.sizeHintKey">{{ t(card.engine.sizeHintKey) }}</li>
        <li v-if="card.engine.requiresGpu">{{ t("settings.engines.meta.gpu") }}</li>
        <li v-if="card.engine.kind === 'planned'">{{ t("settings.engines.meta.planned") }}</li>
      </ul>

      <p v-if="card.status.runtime?.animaRoot || card.status.runtime?.musubiRoot" class="engine-path">
        <span>{{ t("settings.engines.meta.path") }}</span>
        <code>{{ card.status.runtime.animaRoot || card.status.runtime.musubiRoot }}</code>
      </p>

      <div v-if="isManaged(card.engine.id)" class="engine-card-actions">
        <button
          class="primary-action"
          :disabled="loadingId === card.engine.id || ['installing', 'auditing', 'ready'].includes(card.status.state) || !card.status.featureEnabled"
          @click="install(card.engine.id, false)"
        >
          {{ ["installing", "auditing"].includes(card.status.state) ? t("settings.engines.actions.installing") : t("settings.engines.actions.install") }}
        </button>
        <button
          class="secondary-action"
          :disabled="loadingId === card.engine.id || !['broken', 'installed_unverified'].includes(card.status.state)"
          :title="t('settings.engines.actions.reinstallHint')"
          @click="install(card.engine.id, true)"
        >
          {{ t("settings.engines.actions.reinstall") }}
        </button>
        <button
          class="secondary-action"
          :disabled="loadingId === card.engine.id || ['installing', 'auditing', 'not_installed', 'coming_soon'].includes(card.status.state)"
          @click="uninstall(card.engine.id)"
        >
          {{ t("settings.engines.actions.uninstall") }}
        </button>
        <button class="ghost-button" :disabled="loadingId === card.engine.id" @click="refresh()">
          {{ t("settings.engines.actions.refresh") }}
        </button>
      </div>

      <div v-if="isManaged(card.engine.id) && activeConsoleId === card.engine.id && (logs.length || ['installing', 'auditing'].includes(card.status.state))" class="engine-console">
        <header>
          <span>{{ phase || t("settings.engines.console.idle") }}</span>
          <b>{{ progress }}%</b>
        </header>
        <div class="install-progress"><i :style="{ width: `${progress}%` }" /></div>
        <pre>{{ logs.length ? logs.join("\n") : t("settings.engines.console.waiting") }}</pre>
      </div>
    </section>
  </div>
</template>
