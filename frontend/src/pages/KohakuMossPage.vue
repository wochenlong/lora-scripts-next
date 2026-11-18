<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { useI18n } from "vue-i18n"
import { RouterLink } from "vue-router"
import { enginesApi, type EngineStatus } from "../api/engines"
import { tasksApi } from "../api/tasks"
import { kohakuMossApi } from "../api/kohakuMoss"
import EngineStatusBar from "../components/EngineStatusBar.vue"
import TrainingPage from "./TrainingPage.vue"
import { SCHEMA_META } from "../training/modules"

withDefaults(defineProps<{ bare?: boolean }>(), { bare: false })

const status = ref<EngineStatus>({ id: "kohaku-moss", state: "unknown", featureEnabled: true })
const loading = ref(false)
const logs = ref<string[]>([])
const progress = ref(0)
const phase = ref("")
let disposed = false
let refreshSequence = 0
let appliedRefresh = 0
let timer: number | undefined
let logSource: EventSource | undefined
let progressSource: EventSource | undefined

const { t } = useI18n()
const meta = SCHEMA_META["kohaku-moss-image-lora"]
const title = computed(() => t(meta.titleKey))
const area = computed(() => t(meta.areaKey))
const ready = computed(() => status.value.featureEnabled && status.value.state === "ready")
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
  if (status.value.message) return status.value.message
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
  logSource = new EventSource(logUrl || kohakuMossApi.installLogUrl(taskId))
  logSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.text) logs.value.push(data.text)
      if (data.done) logSource?.close()
    } catch {
      logs.value.push(event.data)
    }
  }
  progressSource = new EventSource(progressUrl || kohakuMossApi.installProgressUrl(taskId))
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
  const sequence = ++refreshSequence
  try {
    const next = await enginesApi.status("kohaku-moss")
    if (disposed || sequence < appliedRefresh) return
    appliedRefresh = sequence
    status.value = next
    if (ready.value) { stopPolling(); closeStreams() }
    const id = status.value.facts?.task_id
    if (id && working.value && !logSource) streams(String(id))
  } catch (error) {
    if (!disposed && sequence >= appliedRefresh && reportError) ElMessage.error(error instanceof Error ? error.message : t("settings.engines.msg.statusFail"))
  }
}

async function install(forceReinstall = false) {
  if (loading.value || working.value || !status.value.featureEnabled || status.value.state === "disabled") return
  try {
    loading.value = true
    await ElMessageBox.confirm(
      forceReinstall ? t("settings.engines.confirm.reinstall") : t("settings.engines.confirm.install.kohaku-moss"),
      forceReinstall ? t("settings.engines.actions.reinstall") : t("settings.engines.actions.install"),
      { type: "warning" },
    )
    if (disposed) return
    logs.value = []
    progress.value = 0
    const data = forceReinstall ? await enginesApi.repair("kohaku-moss") : await enginesApi.install("kohaku-moss")
    if (disposed) return
    appliedRefresh = ++refreshSequence
    if (data.status) status.value = data.status
    if (data.alreadyReady) {
      if (!data.status) await refresh()
      if (ready.value) { stopPolling(); closeStreams() }
      return ElMessage.success(t("settings.engines.msg.ready"))
    }
    if (data.taskId) {
      status.value = { ...status.value, state: "installing", facts: { ...status.value.facts, task_id: data.taskId } }
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
  if (!disposed && !ready.value) timer = window.setInterval(() => refresh(false), 2000)
})
onBeforeUnmount(() => {
  disposed = true
  stopPolling()
  closeStreams()
})
</script>

<template>
  <TrainingPage
    v-if="ready"
    :title="title"
    :area="area"
    schema-name="kohaku-moss-image-lora"
    :bare="bare"
  >
    <template #form-top>
      <slot name="form-top" />
      <p class="engine-ready-chip" data-testid="engine-ready-chip" :title="t('settings.engines.hint.ready')">
        <i aria-hidden="true" />
        <span>{{ t("settings.engines.readyChip") }}</span>
      </p>
      <p class="engine-credit" data-testid="kohaku-moss-credit">
        <i18n-t keypath="kohakuMoss.credit" tag="span" scope="global">
          <template #upstream><a href="https://github.com/KohakuBlueleaf/KohakuMossTrainer" target="_blank" rel="noreferrer">KohakuBlueleaf/KohakuMossTrainer</a></template>
          <template #notice><a href="https://github.com/KohakuBlueleaf/KohakuMossTrainer/blob/main/LICENSE" target="_blank" rel="noreferrer">KohakuMoss License 1.0</a></template>
        </i18n-t>
      </p>
    </template>
  </TrainingPage>

  <div v-else class="fast-page" :class="{ bare, 'has-console': consoleActive }">
    <div class="fast-main">
      <slot name="form-top" />
      <!-- Unknown: quiet strip with refresh/manage. Install CTAs only when state is known. -->
      <EngineStatusBar
        :state="status.state"
        :title="label"
        :hint="hint"
        :loading="loading"
        :show-install="false"
        :show-reinstall="false"
        :show-refresh="statusUnknown"
        :show-manage="statusUnknown"
        @refresh="refresh()"
      />
      <section v-if="!statusUnknown || !bare" class="fast-intro">
        <span v-if="!bare" class="eyebrow">KohakuMossTrainer RUNTIME</span>
        <h1 v-if="!bare">{{ title }}</h1>
        <p v-if="!bare">{{ t("kohakuMoss.intro") }}</p>
      <p class="engine-credit" data-testid="kohaku-moss-credit">
        <i18n-t keypath="kohakuMoss.credit" tag="span" scope="global">
          <template #upstream><a href="https://github.com/KohakuBlueleaf/KohakuMossTrainer" target="_blank" rel="noreferrer">KohakuBlueleaf/KohakuMossTrainer</a></template>
          <template #notice><a href="https://github.com/KohakuBlueleaf/KohakuMossTrainer/blob/main/LICENSE" target="_blank" rel="noreferrer">KohakuMoss License 1.0</a></template>
        </i18n-t>
      </p>
        <div v-if="status.facts?.audit?.errors?.length" class="audit-errors">
          <strong>{{ t("kohakuMoss.auditTitle") }}</strong>
          <p v-for="error in status.facts.audit.errors" :key="error">{{ error }}</p>
        </div>
        <div v-if="!statusUnknown" class="fast-actions">
          <button class="primary-action" :disabled="loading || working || !status.featureEnabled || status.state === 'disabled'" @click="install(false)">
            {{ working ? t("kohakuMoss.installWorking") : t("kohakuMoss.install") }}
          </button>
          <button
            v-if="working"
            type="button"
            class="secondary-action"
            data-testid="engine-cancel-install"
            :disabled="loading || !status.facts?.task_id"
            @click="cancelInstall"
          >{{ t("settings.engines.actions.cancelInstall") }}</button>
          <button v-if="status.state === 'broken' || status.state === 'installed_unverified'" class="secondary-action" :disabled="loading || !status.featureEnabled" @click="install(true)">
            {{ t("settings.engines.actions.reinstall") }}
          </button>
          <RouterLink class="secondary-action" to="/settings/engines">{{ t("settings.engines.actions.manage") }}</RouterLink>
        </div>
      </section>
    </div>
    <aside v-if="consoleActive" class="install-console" data-testid="install-console">
      <header>
        <span>{{ phase || t("kohakuMoss.consoleIdle") }}</span>
        <b>{{ progress }}%</b>
      </header>
      <div class="install-progress"><i :style="{ width: `${progress}%` }" /></div>
      <pre>{{ logs.length ? logs.join("\n") : t("kohakuMoss.consoleWaiting") }}</pre>
    </aside>
  </div>
</template>
