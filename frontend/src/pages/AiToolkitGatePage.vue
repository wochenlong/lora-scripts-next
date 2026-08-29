<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { useI18n } from "vue-i18n"
import { RouterLink } from "vue-router"
import { enginesApi, type EngineStatus } from "../api/engines"
import EngineStatusBar from "../components/EngineStatusBar.vue"
import TrainingPage from "./TrainingPage.vue"
import { SCHEMA_META } from "../training/modules"

withDefaults(defineProps<{ bare?: boolean }>(), { bare: false })

const status = ref<EngineStatus>({ id: "ai-toolkit", state: "unknown", featureEnabled: true })
const loading = ref(false)
const logs = ref<string[]>([])
const progress = ref(0)
const phase = ref("")
let timer: number | undefined
let logSource: EventSource | undefined
let progressSource: EventSource | undefined

const { t } = useI18n()
const meta = SCHEMA_META["klein-lora"]
const title = computed(() => t(meta.titleKey))
const area = computed(() => t(meta.areaKey))
const ready = computed(() => status.value.state === "ready")
const working = computed(() => ["installing", "auditing"].includes(status.value.state))
const label = computed(() => {
  const key = `settings.engines.state.${status.value.state}`
  const translated = t(key)
  return translated === key ? status.value.state : translated
})
const hint = computed(() => {
  if (!status.value.featureEnabled || status.value.state === "disabled") return t("settings.engines.hint.disabled")
  const key = `settings.engines.hint.${status.value.state}`
  const translated = t(key)
  return translated === key ? t("settings.engines.hint.unknown") : translated
})

function stopPolling() {
  if (timer !== undefined) {
    window.clearInterval(timer)
    timer = undefined
  }
}

function closeStreams() {
  logSource?.close()
  progressSource?.close()
  logSource = undefined
  progressSource = undefined
}

function streams(taskId: string, logUrl?: string, progressUrl?: string) {
  closeStreams()
  logSource = new EventSource(logUrl || `/api/engines/ai-toolkit/install/log/stream/${taskId}`)
  logSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.text) logs.value.push(data.text)
      if (data.done) logSource?.close()
    } catch {
      logs.value.push(event.data)
    }
  }
  progressSource = new EventSource(progressUrl || `/api/engines/ai-toolkit/install/progress/stream/${taskId}`)
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
    status.value = await enginesApi.status("ai-toolkit")
    if (ready.value) stopPolling()
    const id = status.value.facts?.task_id
    if (id && working.value && !logSource) streams(String(id))
  } catch (error) {
    if (reportError) ElMessage.error(error instanceof Error ? error.message : t("settings.engines.msg.statusFail"))
  }
}

async function install(forceReinstall = false) {
  try {
    await ElMessageBox.confirm(
      forceReinstall ? t("settings.engines.confirm.reinstall") : t("settings.engines.confirm.install.ai-toolkit"),
      forceReinstall ? t("settings.engines.actions.reinstall") : t("settings.engines.actions.install"),
      { type: "warning" },
    )
    loading.value = true
    logs.value = []
    progress.value = 0
    const data = forceReinstall ? await enginesApi.repair("ai-toolkit") : await enginesApi.install("ai-toolkit")
    if (data.alreadyReady) {
      status.value = data.status || status.value
      if (ready.value) stopPolling()
      return ElMessage.success(t("settings.engines.msg.ready"))
    }
    if (data.taskId) {
      streams(data.taskId, data.logStream, data.progressStream)
      if (!timer) timer = window.setInterval(() => refresh(false), 2000)
    }
    await refresh()
    ElMessage.success(t("settings.engines.msg.started"))
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error instanceof Error ? error.message : t("settings.engines.msg.fail"))
    }
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await refresh()
  if (!ready.value) timer = window.setInterval(() => refresh(false), 2000)
})
onBeforeUnmount(() => {
  stopPolling()
  closeStreams()
})
</script>

<template>
  <TrainingPage
    v-if="ready"
    :title="title"
    :area="area"
    schema-name="klein-lora"
    :bare="bare"
  >
    <template #form-top>
      <slot name="form-top" />
      <p class="engine-ready-chip" data-testid="engine-ready-chip" :title="t('settings.engines.hint.ready')">
        <i aria-hidden="true" />
        <span>{{ t("settings.engines.readyChip") }}</span>
      </p>
    </template>
  </TrainingPage>

  <div v-else class="fast-page" :class="{ bare }">
    <div class="fast-main">
      <slot name="form-top" />
      <EngineStatusBar
        :state="status.state"
        :title="label"
        :hint="hint"
        :loading="loading"
        :show-install="status.featureEnabled && !working"
        :show-reinstall="status.state === 'broken'"
        @install="install(false)"
        @reinstall="install(true)"
      />
      <section class="fast-intro">
        <span v-if="!bare" class="eyebrow">AI TOOLKIT RUNTIME</span>
        <h1 v-if="!bare">{{ title }}</h1>
        <p v-if="!bare">{{ t("aiToolkitGate.intro") }}</p>
        <div class="fast-state" :data-state="status.state">
          <span>{{ label }}</span>
          <strong>{{ status.state }}</strong>
        </div>
        <div v-if="status.facts?.audit?.errors?.length" class="audit-errors">
          <strong>{{ t("aiToolkitGate.auditTitle") }}</strong>
          <p v-for="error in status.facts.audit.errors" :key="error">{{ error }}</p>
        </div>
        <div class="fast-actions">
          <button class="primary-action" :disabled="loading || working || !status.featureEnabled" @click="install(false)">
            {{ working ? t("aiToolkitGate.installWorking") : t("aiToolkitGate.install") }}
          </button>
          <button v-if="status.state === 'broken'" class="secondary-action" :disabled="loading" @click="install(true)">
            {{ t("settings.engines.actions.reinstall") }}
          </button>
          <RouterLink class="secondary-action" to="/settings/engines">{{ t("settings.engines.actions.manage") }}</RouterLink>
        </div>
      </section>
    </div>
    <aside class="install-console">
      <header>
        <span>{{ phase || t("aiToolkitGate.consoleIdle") }}</span>
        <b>{{ progress }}%</b>
      </header>
      <div class="install-progress"><i :style="{ width: `${progress}%` }" /></div>
      <pre>{{ logs.length ? logs.join("\n") : t("aiToolkitGate.consoleWaiting") }}</pre>
    </aside>
  </div>
</template>
