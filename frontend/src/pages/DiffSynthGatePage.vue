<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { useI18n } from "vue-i18n"
import { RouterLink } from "vue-router"
import { enginesApi, type EngineStatus } from "../api/engines"
import { tasksApi } from "../api/tasks"
import EngineStatusBar from "../components/EngineStatusBar.vue"
import TrainingPage from "./TrainingPage.vue"
import { SCHEMA_META } from "../training/modules"

withDefaults(defineProps<{ bare?: boolean }>(), { bare: false })

const status = ref<EngineStatus>({ id: "diffsynth", state: "unknown", featureEnabled: true })
const loading = ref(false)
const logs = ref<string[]>([])
const progress = ref(0)
const phase = ref("")
let timer: number | undefined
let logSource: EventSource | undefined
let progressSource: EventSource | undefined

const { t } = useI18n()
const meta = SCHEMA_META["qwen-image-21-lora"]
const title = computed(() => t(meta.titleKey))
const area = computed(() => t(meta.areaKey))
const ready = computed(() => status.value.state === "ready")
const working = computed(() => ["installing", "auditing"].includes(status.value.state))
const statusUnknown = computed(() => status.value.state === "unknown")
const consoleActive = computed(() => working.value || logs.value.length > 0 || progress.value > 0)
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
  logSource = new EventSource(logUrl || `/api/engines/diffsynth/install/log/stream/${taskId}`)
  logSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.text) logs.value.push(data.text)
      if (data.done) logSource?.close()
    } catch {
      logs.value.push(event.data)
    }
  }
  progressSource = new EventSource(progressUrl || `/api/engines/diffsynth/install/progress/stream/${taskId}`)
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
    status.value = await enginesApi.status("diffsynth")
    if (ready.value) stopPolling()
    const id = status.value.facts?.task_id
    if (id && working.value && !logSource) streams(String(id))
  } catch (error) {
    if (reportError) ElMessage.error(error instanceof Error ? error.message : t("settings.engines.msg.statusFail"))
  }
}

const diagnosisHint = computed(() => status.value.diagnosis?.summary || "")

async function runAction(kind: "install" | "repair" | "reinstall") {
  try {
    const confirmKey =
      kind === "reinstall"
        ? "settings.engines.confirm.reinstall"
        : kind === "repair"
          ? "settings.engines.confirm.repair"
          : "settings.engines.confirm.install.diffsynth"
    const titleKey =
      kind === "reinstall"
        ? "settings.engines.actions.reinstall"
        : kind === "repair"
          ? "settings.engines.actions.repair"
          : "settings.engines.actions.install"
    await ElMessageBox.confirm(t(confirmKey), t(titleKey), { type: "warning" })
    loading.value = true
    logs.value = []
    progress.value = 0
    const data =
      kind === "reinstall"
        ? await enginesApi.reinstall("diffsynth")
        : kind === "repair"
          ? await enginesApi.repair("diffsynth")
          : await enginesApi.install("diffsynth")
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

async function cancelInstall() {
  const taskId = status.value.facts?.task_id
  if (!taskId) return
  try {
    loading.value = true
    await tasksApi.terminate(String(taskId))
    closeStreams()
    await refresh()
    ElMessage.success(t("settings.engines.actions.cancelInstallDone"))
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t("settings.engines.msg.fail"))
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
    schema-name="qwen-image-21-lora"
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

  <div v-else class="fast-page" :class="{ bare, 'has-console': consoleActive }">
    <div class="fast-main">
      <slot name="form-top" />
      <EngineStatusBar
        :state="status.state"
        :title="label"
        :hint="diagnosisHint || hint"
        :loading="loading"
        :show-install="false"
        :show-reinstall="false"
        :show-refresh="statusUnknown"
        :show-manage="statusUnknown"
        @refresh="refresh()"
      />
      <section v-if="!statusUnknown || !bare" class="fast-intro">
        <span v-if="!bare" class="eyebrow">DIFFSYNTH-STUDIO RUNTIME</span>
        <h1 v-if="!bare">{{ title }}</h1>
        <p v-if="!bare">{{ t("diffsynthGate.intro") }}</p>
        <p v-if="diagnosisHint" class="audit-errors" data-testid="diffsynth-diagnosis">{{ diagnosisHint }}</p>
        <div v-if="status.facts?.audit?.errors?.length" class="audit-errors">
          <strong>{{ t("diffsynthGate.auditTitle") }}</strong>
          <p v-for="error in status.facts.audit.errors" :key="error">{{ error }}</p>
        </div>
        <div v-if="!statusUnknown" class="fast-actions">
          <button
            v-if="status.state !== 'broken'"
            class="primary-action"
            :disabled="loading || working || !status.featureEnabled"
            @click="runAction('install')"
          >
            {{ working ? t("diffsynthGate.installWorking") : t("diffsynthGate.install") }}
          </button>
          <button
            v-if="working"
            type="button"
            class="secondary-action"
            data-testid="engine-cancel-install"
            :disabled="loading || !status.facts?.task_id"
            @click="cancelInstall"
          >{{ t("settings.engines.actions.cancelInstall") }}</button>
          <button
            v-if="status.state === 'broken' && status.diagnosis?.code !== 'host_no_gpu'"
            class="primary-action"
            :disabled="loading || working"
            @click="runAction('repair')"
          >
            {{ t("settings.engines.actions.repair") }}
          </button>
          <button
            v-if="status.state === 'broken' && status.diagnosis?.allows_full_reinstall !== false"
            class="secondary-action"
            :disabled="loading"
            @click="runAction('reinstall')"
          >
            {{ t("settings.engines.actions.reinstall") }}
          </button>
          <RouterLink class="secondary-action" to="/settings/engines">{{ t("settings.engines.actions.manage") }}</RouterLink>
        </div>
      </section>
    </div>
    <aside v-if="consoleActive" class="install-console" data-testid="install-console">
      <header>
        <span>{{ phase || t("diffsynthGate.consoleIdle") }}</span>
        <b>{{ progress }}%</b>
      </header>
      <div class="install-progress"><i :style="{ width: `${progress}%` }" /></div>
      <pre>{{ logs.length ? logs.join("\n") : t("diffsynthGate.consoleWaiting") }}</pre>
    </aside>
  </div>
</template>
