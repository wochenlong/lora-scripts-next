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

const { t } = useI18n()
const status = ref<EngineStatus>({ id: "kohaku-moss", state: "unknown", featureEnabled: true })
const loading = ref(false)
const logs = ref<string[]>([])
const progress = ref(0)
const phase = ref("")
let timer: number | undefined
let logSource: EventSource | undefined
let progressSource: EventSource | undefined

const meta = SCHEMA_META["kohaku-moss-image-lora"]
const ready = computed(() => status.value.featureEnabled && status.value.state === "ready")
const working = computed(() => ["installing", "auditing"].includes(status.value.state))
const unknown = computed(() => status.value.state === "unknown")
const consoleActive = computed(() => working.value || logs.value.length > 0)

function closeStreams() {
  logSource?.close()
  progressSource?.close()
  logSource = undefined
  progressSource = undefined
}

function streams(taskId: string, logUrl?: string, progressUrl?: string) {
  closeStreams()
  logSource = new EventSource(logUrl || `/api/engines/kohaku-moss/install/log/stream/${taskId}`)
  logSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.text) logs.value.push(data.text)
      if (data.done) logSource?.close()
    } catch { logs.value.push(event.data) }
  }
  progressSource = new EventSource(progressUrl || `/api/engines/kohaku-moss/install/progress/stream/${taskId}`)
  progressSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.type === "progress") {
        progress.value = Number(data.percent || 0)
        phase.value = data.message || ""
      }
      if (data.done || data.type === "done") progressSource?.close()
    } catch { /* ignore malformed progress rows */ }
  }
}

async function refresh(reportError = true) {
  try {
    status.value = await enginesApi.status("kohaku-moss")
    if (ready.value && timer !== undefined) {
      window.clearInterval(timer)
      timer = undefined
      closeStreams()
    }
    const taskId = status.value.facts?.task_id
    if (taskId && working.value && !logSource) streams(String(taskId))
  } catch (error) {
    if (reportError) ElMessage.error(error instanceof Error ? error.message : t("settings.engines.msg.statusFail"))
  }
}

async function install(repair = false) {
  try {
    await ElMessageBox.confirm(
      t(repair ? "settings.engines.confirm.reinstall" : "settings.engines.confirm.install.kohaku-moss"),
      t(repair ? "settings.engines.actions.reinstall" : "settings.engines.actions.install"),
      { type: "warning" },
    )
    loading.value = true
    logs.value = []
    progress.value = 0
    const data = repair ? await enginesApi.repair("kohaku-moss") : await enginesApi.install("kohaku-moss")
    if (data.alreadyReady) return ElMessage.success(t("settings.engines.msg.ready"))
    if (data.taskId) {
      streams(data.taskId, data.logStream, data.progressStream)
      if (!timer) timer = window.setInterval(() => refresh(false), 2000)
    }
    await refresh()
    ElMessage.success(t("settings.engines.msg.started"))
  } catch (error) {
    if (error !== "cancel" && error !== "close") ElMessage.error(error instanceof Error ? error.message : t("settings.engines.msg.fail"))
  } finally {
    loading.value = false
  }
}

async function cancelInstall() {
  const taskId = status.value.facts?.task_id
  if (!taskId) return
  await tasksApi.terminate(String(taskId))
  closeStreams()
  await refresh()
}

onMounted(async () => {
  await refresh()
  if (!ready.value) timer = window.setInterval(() => refresh(false), 2000)
})
onBeforeUnmount(() => {
  if (timer !== undefined) window.clearInterval(timer)
  closeStreams()
})
</script>

<template>
  <TrainingPage
    v-if="ready"
    :title="t(meta.titleKey)"
    :area="t(meta.areaKey)"
    schema-name="kohaku-moss-image-lora"
    :bare="bare"
  >
    <template #form-top>
      <slot name="form-top" />
      <p class="engine-ready-chip"><i aria-hidden="true" /><span>{{ t("settings.engines.readyChip") }}</span></p>
      <p class="engine-credit" data-testid="kohaku-moss-credit">
        <i18n-t keypath="kohakuMoss.credit" tag="span" scope="global">
          <template #upstream><a href="https://github.com/KohakuBlueleaf/KohakuMossTrainer" target="_blank" rel="noreferrer">KohakuBlueleaf/KohakuMossTrainer</a></template>
          <template #notice><a href="https://github.com/wochenlong/lora-scripts-next/blob/dev/NOTICE.md" target="_blank" rel="noreferrer">NOTICE.md</a></template>
        </i18n-t>
      </p>
    </template>
  </TrainingPage>

  <div v-else class="fast-page" :class="{ bare, 'has-console': consoleActive }">
    <div class="fast-main">
      <slot name="form-top" />
      <EngineStatusBar
        :state="status.state" :title="t('kohakuMoss.title')"
        :hint="status.message || t('kohakuMoss.intro')" :loading="loading"
        :show-install="false" :show-reinstall="false" :show-refresh="unknown" :show-manage="unknown"
        @refresh="refresh()"
      />
      <section v-if="!unknown || !bare" class="fast-intro">
        <span v-if="!bare" class="eyebrow">EXPERIMENTAL · HIGH PERFORMANCE</span>
        <h1 v-if="!bare">{{ t("kohakuMoss.title") }}</h1>
        <p>{{ t("kohakuMoss.intro") }}</p>
        <p class="engine-credit" data-testid="kohaku-moss-credit">
          <i18n-t keypath="kohakuMoss.credit" tag="span" scope="global">
            <template #upstream><a href="https://github.com/KohakuBlueleaf/KohakuMossTrainer" target="_blank" rel="noreferrer">KohakuBlueleaf/KohakuMossTrainer</a></template>
            <template #notice><a href="https://github.com/wochenlong/lora-scripts-next/blob/dev/NOTICE.md" target="_blank" rel="noreferrer">NOTICE.md</a></template>
          </i18n-t>
        </p>
        <div v-if="!unknown" class="fast-actions">
          <button class="primary-action" :disabled="loading || working || !status.featureEnabled" @click="install(false)">
            {{ working ? t("kohakuMoss.installWorking") : t("kohakuMoss.install") }}
          </button>
          <button v-if="working" class="secondary-action" :disabled="!status.facts?.task_id" @click="cancelInstall">
            {{ t("settings.engines.actions.cancelInstall") }}
          </button>
          <button v-if="status.state === 'broken' || status.state === 'installed_unverified'" class="secondary-action" @click="install(true)">
            {{ t("settings.engines.actions.reinstall") }}
          </button>
          <RouterLink class="secondary-action" to="/settings/engines">{{ t("settings.engines.actions.manage") }}</RouterLink>
        </div>
      </section>
    </div>
    <aside v-if="consoleActive" class="install-console">
      <header><span>{{ phase || t("kohakuMoss.consoleWaiting") }}</span><b>{{ progress }}%</b></header>
      <div class="install-progress"><i :style="{ width: `${progress}%` }" /></div>
      <pre>{{ logs.join("\n") || t("kohakuMoss.consoleWaiting") }}</pre>
    </aside>
  </div>
</template>
