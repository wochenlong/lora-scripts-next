<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { ElMessage, ElMessageBox } from "element-plus"
import { Refresh } from "@element-plus/icons-vue"
import { stringify } from "smol-toml"
import { storeToRefs } from "pinia"
import { useI18n } from "vue-i18n"
import { useTasksStore } from "../stores/tasks"
import { tasksApi, type TaskMetrics, type TaskPreviewImage, type TaskProgress, type TaskStatus, type TrainingTask } from "../api/tasks"
import { moduleForTrainType } from "../training/modules"
import { copyText } from "../utils/clipboard"
import LossChart from "../components/LossChart.vue"
import TaskLogPanel from "../components/TaskLogPanel.vue"

const router = useRouter()

const store = useTasksStore()
const { tasks, loading, error, terminatingId } = storeToRefs(store)
const { t } = useI18n()
let timer: number | undefined
let insightTick = 0

const previews = ref<TaskPreviewImage[]>([])
const lightboxImage = ref<TaskPreviewImage | null>(null)
const metrics = ref<TaskMetrics>({})
const progress = ref<TaskProgress>({})
const previewEnabled = ref(true)
/** Default expanded; collapse to focus on the training log. */
const previewOpen = ref(true)
const lossOpen = ref(true)
let previewSig = ""
let metricsSig = ""

function imageLabel(image: TaskPreviewImage): string {
  if (image.epoch != null) return t("tasks.detail.epochLabel", { n: image.epoch })
  if (image.step != null) return t("tasks.detail.stepLabel", { n: image.step })
  return ""
}
const hasLoss = computed(() => Object.values(metrics.value).some((points) => points.length > 0))
const lossSeries = computed(() => {
  const series: { name: string; color: string; points: { step: number; value: number }[] }[] = []
  const average = metrics.value["loss/average"]
  const current = metrics.value["loss/current"]
  if (average?.length) series.push({ name: "loss/average", color: "#2563eb", points: average })
  if (current?.length) series.push({ name: "loss/current", color: "#d97706", points: current })
  if (!series.length) {
    for (const [name, points] of Object.entries(metrics.value)) {
      if (points.length) series.push({ name, color: series.length ? "#d97706" : "#2563eb", points })
    }
  }
  return series
})

let insightController: AbortController | undefined

async function loadInsights(taskId: string) {
  insightController?.abort()
  const controller = new AbortController()
  insightController = controller
  try {
    const [previewsData, data] = await Promise.all([tasksApi.previews(taskId, controller.signal), tasksApi.metrics(taskId, controller.signal)])
    if (controller.signal.aborted || taskId !== selected.value?.id) return
    previewEnabled.value = previewsData.preview_enabled !== false
    const images = previewsData.images
    if (images.length > 0) {
      const nextPreviewSig = images.map((image) => `${image.name}:${image.mtime}`).join("|")
      if (nextPreviewSig !== previewSig) {
        previewSig = nextPreviewSig
        previews.value = images
      }
    }
    const tags = data.tags
    if (Object.values(tags).some((points) => points.length > 0)) {
      const nextMetricsSig = Object.entries(tags).map(([tag, points]) => `${tag}:${points.length}:${points[points.length - 1]?.step ?? 0}`).join("|")
      if (nextMetricsSig !== metricsSig) {
        metricsSig = nextMetricsSig
        metrics.value = tags
      }
    }
    if (data.progress && Object.keys(data.progress).length > 0) progress.value = data.progress
  } catch {}
}

const statusLabels = computed<Record<TaskStatus, string>>(() => ({
  CREATED: t("tasks.status.created"),
  QUEUED: t("tasks.status.queued"),
  RUNNING: t("tasks.status.running"),
  FINISHED: t("tasks.status.finished"),
  TERMINATED: t("tasks.status.terminated"),
  FAILED: t("tasks.status.failed"),
}))

/** Restored-after-restart queued tasks wait for manual confirmation. */
function isHeld(task: TrainingTask): boolean {
  return task.status === "QUEUED" && task.metadata.held === true
}

function statusLabel(task: TrainingTask): string {
  if (isHeld(task)) return t("tasks.status.held")
  return statusLabels.value[task.status] || task.status
}

const activeTab = ref<"running" | "recent">("running")
const selectedId = ref("")

interface TaskStage {
  id: string
  name: string
  status: TaskStatus
}

interface TaskGroup {
  key: string
  tasks: TrainingTask[]
  representative: TrainingTask
  stages: TaskStage[]
}

const STAGE_ORDER = ["cache_latents", "cache_text_encoder", "train"]
const STAGE_LABEL_KEYS: Record<string, string> = {
  cache_latents: "tasks.stage.cacheLatents",
  cache_text_encoder: "tasks.stage.cacheTextEncoder",
  train: "tasks.stage.train",
}

function stageLabelKey(name: string): string {
  return STAGE_LABEL_KEYS[name] ?? ""
}

function isActiveTask(task: TrainingTask): boolean {
  return task.status === "RUNNING" || task.status === "CREATED" || task.status === "QUEUED"
}

function groupKey(task: TrainingTask): string {
  const group = task.metadata.train_task_id
  const stage = task.metadata.stage
  return typeof group === "string" && typeof stage === "string" ? group : task.id
}

function stageRank(task: TrainingTask): number {
  const rank = STAGE_ORDER.indexOf(String(task.metadata.stage))
  return rank === -1 ? STAGE_ORDER.length : rank
}

function pickRepresentative(bucket: TrainingTask[]): TrainingTask {
  const staged = bucket.filter((task) => typeof task.metadata.stage === "string")
  if (staged.length < 2) return bucket[0]
  const running = staged.find((task) => task.status === "RUNNING")
  if (running) return running
  const queued = staged.find((task) => task.status === "QUEUED")
  if (queued) return queued
  const failed = [...staged].sort((a, b) => stageRank(b) - stageRank(a)).find((task) => task.status === "FAILED" || task.status === "TERMINATED")
  if (failed) return failed
  return [...staged].sort((a, b) => stageRank(b) - stageRank(a))[0]
}

function buildGroups(list: TrainingTask[]): TaskGroup[] {
  const buckets = new Map<string, TrainingTask[]>()
  for (const task of list) {
    const key = groupKey(task)
    const bucket = buckets.get(key)
    if (bucket) bucket.push(task)
    else buckets.set(key, [task])
  }
  return [...buckets.entries()].map(([key, bucket]) => {
    const stages = bucket
      .filter((task) => typeof task.metadata.stage === "string")
      .sort((a, b) => stageRank(a) - stageRank(b))
      .map((task) => ({ id: task.id, name: String(task.metadata.stage), status: task.status }))
    return { key, tasks: bucket, representative: pickRepresentative(bucket), stages }
  })
}

/** Running groups first (oldest start first), then CREATED, then queued groups in execution order. */
function groupRank(group: TaskGroup): number {
  if (group.tasks.some((task) => task.status === "RUNNING")) return 0
  if (group.tasks.some((task) => task.status === "CREATED")) return 1
  return 2
}

function groupCreatedAt(group: TaskGroup): number {
  return Math.min(...group.tasks.map((task) => Number(task.metadata.created_at) || 0))
}

function groupQueuePosition(group: TaskGroup): number {
  const positions = group.tasks.map((task) => task.queue_position ?? 0).filter((n) => n > 0)
  return positions.length ? Math.min(...positions) : Number.MAX_SAFE_INTEGER
}

const orderedTasks = computed(() => [...tasks.value].reverse())
const allGroups = computed(() => buildGroups(orderedTasks.value))
const runningList = computed(() =>
  allGroups.value
    .filter((group) => group.tasks.some(isActiveTask))
    .sort((a, b) => {
      const rank = groupRank(a) - groupRank(b)
      if (rank !== 0) return rank
      if (groupRank(a) === 2) return groupQueuePosition(a) - groupQueuePosition(b)
      return groupCreatedAt(a) - groupCreatedAt(b)
    }),
)
const recentList = computed(() => allGroups.value.filter((group) => !group.tasks.some(isActiveTask)))

const filterStatus = ref<"" | TaskStatus>("")
const filterType = ref("")
const filterKeyword = ref("")

const FILTER_STATUSES: TaskStatus[] = ["RUNNING", "QUEUED", "CREATED", "FINISHED", "FAILED", "TERMINATED"]

function taskTypeLabel(task: TrainingTask): string {
  return metaString(task, "train_type") || metaString(task, "backend")
}

const typeOptions = computed(() => {
  const values = new Set<string>()
  for (const task of tasks.value) {
    const label = taskTypeLabel(task)
    if (label) values.add(label)
  }
  return [...values].sort()
})

function groupMatchesFilters(group: TaskGroup): boolean {
  if (filterStatus.value && !group.tasks.some((task) => task.status === filterStatus.value)) return false
  if (filterType.value && !group.tasks.some((task) => taskTypeLabel(task) === filterType.value)) return false
  const keyword = filterKeyword.value.trim().toLowerCase()
  if (keyword) {
    const haystacks = group.tasks.flatMap((task) => [
      task.id,
      group.key,
      taskName(task),
      metaString(task, "config_path"),
      metaString(task, "output_dir"),
      metaString(task, "output_name"),
    ])
    if (!haystacks.some((text) => text.toLowerCase().includes(keyword))) return false
  }
  return true
}

const visibleList = computed(() => (activeTab.value === "running" ? runningList.value : recentList.value).filter(groupMatchesFilters))
const selected = computed(() => allGroups.value.find((group) => group.key === selectedId.value)?.representative)
const selectedIsMaintenance = computed(() => (selected.value ? isMaintenanceTask(selected.value) : false))

const KIND_LABEL_KEYS: Record<string, string> = {
  musubi_install: "tasks.kind.musubiInstall",
  anima_fast_install: "tasks.kind.animaFastInstall",
  assets_download: "tasks.kind.assetsDownload",
}

function kindLabelKey(task: TrainingTask): string {
  const kind = task.metadata.kind
  return typeof kind === "string" ? (KIND_LABEL_KEYS[kind] ?? "") : ""
}

/** Install/download tasks never produce training insights. */
function isMaintenanceTask(task: TrainingTask): boolean {
  return task.lane === "maintenance" || Boolean(kindLabelKey(task))
}

/**
 * Insights (previews/loss) are resolved by scanning output/logging dirs with an
 * mtime filter, so a task that has not started yet would pick up files written
 * by the currently running task. Only fetch insights for training tasks that
 * have actually run (or are running).
 */
function insightsEligible(task: TrainingTask | undefined | null): boolean {
  if (!task || isMaintenanceTask(task)) return false
  return task.status !== "QUEUED" && task.status !== "CREATED"
}

function taskName(task: TrainingTask) {
  const kindKey = kindLabelKey(task)
  if (kindKey) return t(kindKey)
  return String(task.metadata.output_name || task.metadata.trainer_file || task.metadata.backend || t("tasks.defaultName"))
}

/** Short group id for the list row; full id stays in the detail panel. */
function groupShortId(group: TaskGroup): string {
  return group.key.length > 12 ? `${group.key.slice(0, 8)}…` : group.key
}

async function copyOutputDir(task: TrainingTask) {
  const dir = metaString(task, "output_dir")
  if (!dir) return
  try {
    await copyText(dir)
    ElMessage.success(t("tasks.detail.outputDirCopied"))
  } catch {
    ElMessage.error(t("tasks.detail.outputDirCopyFail"))
  }
}

function taskDetail(task: TrainingTask) {
  return String(task.metadata.config_path || task.metadata.command || t("tasks.noDetail"))
}

const selectedError = computed(() => {
  const value = selected.value?.metadata.error
  return typeof value === "string" ? value : ""
})
const selectedErrorLines = computed(() => {
  const value = selected.value?.metadata.last_log_lines
  return Array.isArray(value) ? value.filter((line): line is string => typeof line === "string") : []
})

function metaString(task: TrainingTask, key: string): string {
  const value = task.metadata[key]
  return typeof value === "string" && value ? value : ""
}

const now = ref(Date.now())
const selectedCreatedAt = computed(() => {
  const value = selected.value?.metadata.created_at
  return typeof value === "number" && value > 0 ? value : null
})
const selectedFinishedAt = computed(() => {
  const value = selected.value?.metadata.finished_at
  return typeof value === "number" && value > 0 ? value : null
})
function formatTimestamp(ts: number): string {
  return new Date(ts * 1000).toLocaleString()
}
const elapsedLabel = computed(() => {
  const created = selectedCreatedAt.value
  if (!created) return ""
  const end = selectedFinishedAt.value ? selectedFinishedAt.value * 1000 : now.value
  const seconds = Math.max(0, Math.floor((end - created * 1000) / 1000))
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const secs = seconds % 60
  if (hours) return `${hours}h ${minutes}m ${secs}s`
  if (minutes) return `${minutes}m ${secs}s`
  return `${secs}s`
})

function select(group: TaskGroup) {
  selectedId.value = group.key
}

watch(visibleList, (list) => {
  if (!list.some((group) => group.key === selectedId.value)) selectedId.value = list[0]?.key ?? ""
}, { immediate: true })

watch(() => selected.value?.id, (id) => {
  previews.value = []
  metrics.value = {}
  progress.value = {}
  previewEnabled.value = true
  previewSig = ""
  metricsSig = ""
  if (id && insightsEligible(selected.value)) loadInsights(id)
})

watch(() => selected.value?.status, (status, previous) => {
  const wasActive = previous === "RUNNING" || previous === "CREATED" || previous === "QUEUED"
  const isActive = status === "RUNNING" || status === "CREATED" || status === "QUEUED"
  const id = selected.value?.id
  if (wasActive && status && !isActive && id && insightsEligible(selected.value)) loadInsights(id)
  // A queued task that just started becomes eligible: load once it is running.
  if (previous === "QUEUED" && status === "RUNNING" && id && insightsEligible(selected.value)) loadInsights(id)
})

async function terminate(task: TrainingTask) {
  try {
    await ElMessageBox.confirm(t("tasks.terminate.confirm", { id: task.id }), t("tasks.terminate.title"), {
      confirmButtonText: t("tasks.terminate.confirmButton"),
      cancelButtonText: t("tasks.terminate.cancel"),
      type: "warning",
    })
    await store.terminate(task.id)
    ElMessage.success(t("tasks.terminate.success"))
  } catch (caught) {
    if (caught !== "cancel" && caught !== "close") {
      ElMessage.error(caught instanceof Error ? caught.message : t("tasks.terminate.fail"))
    }
  }
}

async function dequeue(task: TrainingTask) {
  try {
    await ElMessageBox.confirm(t("tasks.dequeue.confirm", { id: task.id }), t("tasks.dequeue.title"), {
      confirmButtonText: t("tasks.dequeue.confirmButton"),
      cancelButtonText: t("tasks.terminate.cancel"),
      type: "warning",
    })
    await store.terminate(task.id)
    ElMessage.success(t("tasks.dequeue.success"))
  } catch (caught) {
    if (caught !== "cancel" && caught !== "close") {
      ElMessage.error(caught instanceof Error ? caught.message : t("tasks.dequeue.fail"))
    }
  }
}

const actionBusyId = ref("")

function isTerminal(task: TrainingTask): boolean {
  return task.status === "FINISHED" || task.status === "FAILED" || task.status === "TERMINATED"
}

async function removeTask(task: TrainingTask) {
  try {
    await ElMessageBox.confirm(t("tasks.deleteTask.confirm", { id: task.id }), t("tasks.deleteTask.title"), {
      confirmButtonText: t("tasks.deleteTask.confirmButton"),
      cancelButtonText: t("tasks.terminate.cancel"),
      type: "warning",
    })
    actionBusyId.value = task.id
    await tasksApi.remove(task.id)
    await store.refresh({ silent: true })
    ElMessage.success(t("tasks.deleteTask.success"))
  } catch (caught) {
    if (caught !== "cancel" && caught !== "close") {
      ElMessage.error(caught instanceof Error ? caught.message : t("tasks.deleteTask.fail"))
    }
  } finally {
    actionBusyId.value = ""
  }
}

const purgeOpen = ref(false)
const purgeKeepLast = ref(10)
const purgeBusy = ref(false)

async function purgeTasks() {
  purgeBusy.value = true
  try {
    const result = await tasksApi.purge(purgeKeepLast.value)
    await store.refresh({ silent: true })
    purgeOpen.value = false
    ElMessage.success(t("tasks.purge.success", { n: result.removed }))
  } catch (caught) {
    ElMessage.error(caught instanceof Error ? caught.message : t("tasks.purge.fail"))
  } finally {
    purgeBusy.value = false
  }
}

async function importToTraining(task: TrainingTask) {
  actionBusyId.value = task.id
  try {
    const data = await tasksApi.config(task.id)
    sessionStorage.setItem("mikazuki-pending-import", JSON.stringify(data.config))
    const targetModule = moduleForTrainType(data.train_type)
    if (targetModule) await router.push({ path: "/training", query: { model: targetModule.model, engine: targetModule.engine, target: targetModule.target } })
    else await router.push("/training")
  } catch (caught) {
    sessionStorage.removeItem("mikazuki-pending-import")
    ElMessage.error(caught instanceof Error ? caught.message : t("tasks.importTrain.fail"))
  } finally {
    actionBusyId.value = ""
  }
}

async function fetchTaskToml(task: TrainingTask) {
  const data = await tasksApi.config(task.id)
  const name = String(data.output_name || data.config.output_name || task.id)
  return { tomlText: stringify(data.config), name }
}

async function exportTaskConfig(task: TrainingTask) {
  actionBusyId.value = task.id
  try {
    const { tomlText, name } = await fetchTaskToml(task)
    const blob = new Blob([tomlText], { type: "application/toml;charset=utf-8" })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement("a")
    anchor.href = url
    anchor.download = `${name}.toml`
    anchor.click()
    URL.revokeObjectURL(url)
    ElMessage.success(t("tasks.exportConfig.success"))
  } catch (caught) {
    ElMessage.error(caught instanceof Error ? caught.message : t("tasks.exportConfig.fail"))
  } finally {
    actionBusyId.value = ""
  }
}

async function copyTaskConfig(task: TrainingTask) {
  actionBusyId.value = task.id
  try {
    const { tomlText } = await fetchTaskToml(task)
    await copyText(tomlText)
    ElMessage.success(t("tasks.exportConfig.copied"))
  } catch (caught) {
    ElMessage.error(caught instanceof Error ? caught.message : t("tasks.exportConfig.copyFail"))
  } finally {
    actionBusyId.value = ""
  }
}

async function resume(task: TrainingTask) {
  actionBusyId.value = task.id
  try {
    await tasksApi.resume(task.id)
    await store.refresh({ silent: true })
    ElMessage.success(t("tasks.resume.success"))
  } catch (caught) {
    ElMessage.error(caught instanceof Error ? caught.message : t("tasks.resume.fail"))
  } finally {
    actionBusyId.value = ""
  }
}

async function retry(task: TrainingTask) {
  try {
    await ElMessageBox.confirm(t("tasks.retryTask.confirm", { id: task.id }), t("tasks.retryTask.title"), {
      confirmButtonText: t("tasks.retryTask.confirmButton"),
      cancelButtonText: t("tasks.terminate.cancel"),
      type: "warning",
    })
    actionBusyId.value = task.id
    const result = await tasksApi.retry(task.id)
    await store.refresh({ silent: true })
    ElMessage.success(t("tasks.retryTask.success", { id: result.task_id }))
  } catch (caught) {
    if (caught !== "cancel" && caught !== "close") {
      ElMessage.error(caught instanceof Error ? caught.message : t("tasks.retryTask.fail"))
    }
  } finally {
    actionBusyId.value = ""
  }
}

onMounted(async () => {
  await store.refresh()
  timer = window.setInterval(() => {
    now.value = Date.now()
    const hasActive = tasks.value.some((task) => task.status === "RUNNING" || task.status === "CREATED" || task.status === "QUEUED")
    if (!hasActive) return
    store.refresh({ silent: true })
    insightTick += 1
    const task = selected.value
    if (task && task.status === "RUNNING" && insightsEligible(task) && insightTick % 4 === 0) loadInsights(task.id)
  }, 2000)
})

onBeforeUnmount(() => {
  window.clearInterval(timer)
  insightController?.abort()
})
</script>

<template>
  <div class="tasks-board">
    <header class="tasks-board-header">
      <h1>{{ t("tasks.title") }}</h1>
      <button class="ghost-button" :disabled="loading" @click="store.refresh()"><el-icon><Refresh /></el-icon>{{ t("tasks.refresh") }}</button>
    </header>

    <div v-if="error" class="task-error"><strong>{{ t("tasks.loadError") }}</strong><span>{{ error }}</span><button @click="store.refresh()">{{ t("tasks.retry") }}</button></div>
    <div v-else-if="loading && !tasks.length" class="task-empty">{{ t("tasks.loading") }}</div>
    <div v-else-if="!tasks.length" class="task-empty"><strong>{{ t("tasks.emptyTitle") }}</strong><span>{{ t("tasks.emptyDesc") }}</span></div>

    <div v-else class="tasks-columns">
      <aside class="tasks-list-panel">
        <a class="tasks-monitor-link" href="/train-monitor" target="_blank" rel="noreferrer">{{ t("tasks.trainMonitor") }}</a>
        <div class="tasks-tabs" role="group" :aria-label="t('tasks.filterAria')">
          <button :class="{ active: activeTab === 'running' }" @click="activeTab = 'running'">{{ t("tasks.tabs.running") }}<b>{{ runningList.length }}</b></button>
          <button :class="{ active: activeTab === 'recent' }" @click="activeTab = 'recent'">{{ t("tasks.tabs.recent") }}<b>{{ recentList.length }}</b></button>
        </div>
        <button v-if="activeTab === 'recent' && recentList.length" class="ghost-button tasks-purge-button" @click="purgeOpen = true">{{ t("tasks.purge.button") }}</button>
        <div class="tasks-filters">
          <el-select v-model="filterStatus" size="small" class="tasks-filter-status">
            <el-option value="" :label="t('tasks.filters.allStatuses')" />
            <el-option v-for="s in FILTER_STATUSES" :key="s" :value="s" :label="statusLabels[s] || s" />
          </el-select>
          <el-select v-model="filterType" size="small" class="tasks-filter-type">
            <el-option value="" :label="t('tasks.filters.allTypes')" />
            <el-option v-for="tp in typeOptions" :key="tp" :value="tp" :label="tp" />
          </el-select>
          <input v-model="filterKeyword" class="tasks-filter-keyword" type="search" :placeholder="t('tasks.filters.keywordPlaceholder')">
        </div>
        <p v-if="!visibleList.length" class="tasks-tab-empty">{{ t("tasks.tabEmpty") }}</p>
        <article v-for="group in visibleList" :key="group.key" class="task-row" :class="{ selected: group.key === selectedId }" :data-status="group.representative.status.toLowerCase()" @click="select(group)">
          <span class="task-status">{{ statusLabel(group.representative) }}</span>
          <div class="task-row-main"><h2>{{ taskName(group.representative) }}</h2><code :title="group.key">{{ groupShortId(group) }}</code></div>
          <span v-if="group.representative.status === 'QUEUED' && group.representative.queue_position" class="task-queue-pos">{{ t("tasks.queuePosition", { n: group.representative.queue_position }) }}</span>
          <span v-if="kindLabelKey(group.representative)" class="task-kind">{{ t(kindLabelKey(group.representative)) }}</span>
          <div v-if="group.stages.length > 1" class="task-stage-strip">
            <span v-for="stage in group.stages" :key="stage.id" class="task-stage" :data-status="stage.status.toLowerCase()">{{ stageLabelKey(stage.name) ? t(stageLabelKey(stage.name)) : stage.name }}</span>
          </div>
        </article>
      </aside>

      <section v-if="selected" class="task-detail" :data-status="selected.status.toLowerCase()">
        <header class="task-detail-header">
          <div class="task-detail-title"><h2>{{ taskName(selected) }}</h2><span class="task-status">{{ statusLabel(selected) }}</span></div>
          <div class="task-detail-buttons">
            <button v-if="selected.status === 'RUNNING'" class="danger-action" :disabled="terminatingId === selected.id" @click="terminate(selected)">{{ terminatingId === selected.id ? t("tasks.detail.stopping") : t("tasks.detail.stop") }}</button>
            <button v-else-if="isHeld(selected)" class="primary-action" :disabled="actionBusyId === selected.id" @click="resume(selected)">{{ actionBusyId === selected.id ? t("tasks.detail.starting") : t("tasks.detail.resume") }}</button>
            <button v-else-if="selected.status === 'QUEUED'" class="danger-action" :disabled="terminatingId === selected.id" @click="dequeue(selected)">{{ terminatingId === selected.id ? t("tasks.detail.stopping") : t("tasks.detail.dequeue") }}</button>
            <button v-if="isTerminal(selected) && !selectedIsMaintenance" class="secondary-action" :disabled="actionBusyId === selected.id" @click="retry(selected)">{{ actionBusyId === selected.id ? t("tasks.detail.retrying") : t("tasks.detail.retry") }}</button>
            <button v-if="isTerminal(selected)" class="danger-action" :disabled="actionBusyId === selected.id" @click="removeTask(selected)">{{ t("tasks.detail.delete") }}</button>
          </div>
        </header>
        <div v-if="progress.total_steps" class="task-progress">
          <div class="task-progress-meta"><span>{{ t("tasks.detail.stepProgress", { step: progress.step, total: progress.total_steps }) }}</span><span v-if="progress.total_epochs">{{ t("tasks.detail.epochProgress", { epoch: progress.epoch, total: progress.total_epochs }) }}</span><b>{{ progress.percent }}%</b></div>
          <div class="task-progress-track"><i :style="{ width: `${progress.percent}%` }"></i></div>
        </div>
        <dl class="task-meta-grid">
          <div><dt>{{ t("tasks.detail.taskId") }}</dt><dd><code>{{ selected.id }}</code></dd></div>
          <div><dt>{{ t("tasks.detail.config") }}</dt><dd :title="taskDetail(selected)">{{ taskDetail(selected) }}</dd></div>
          <div><dt>{{ t("tasks.detail.returncode") }}</dt><dd>{{ selected.returncode ?? "-" }}</dd></div>
          <div v-if="selected.status === 'QUEUED' && selected.queue_position"><dt>{{ t("tasks.detail.queuePosition") }}</dt><dd>{{ t("tasks.queuePosition", { n: selected.queue_position }) }}</dd></div>
          <div v-if="metaString(selected, 'backend')"><dt>{{ t("tasks.detail.backend") }}</dt><dd>{{ metaString(selected, "backend") }}</dd></div>
          <div v-if="metaString(selected, 'train_type')"><dt>{{ t("tasks.detail.trainType") }}</dt><dd>{{ metaString(selected, "train_type") }}</dd></div>
          <div v-if="selectedCreatedAt"><dt>{{ t("tasks.detail.createdAt") }}</dt><dd>{{ formatTimestamp(selectedCreatedAt) }}</dd></div>
          <div v-if="selectedCreatedAt"><dt>{{ t("tasks.detail.elapsed") }}</dt><dd>{{ elapsedLabel }}</dd></div>
          <div v-if="metaString(selected, 'output_dir')"><dt>{{ t("tasks.detail.outputDir") }}</dt><dd class="task-output-dir" :title="metaString(selected, 'output_dir')"><span>{{ metaString(selected, "output_dir") }}</span><button type="button" class="copy-button" @click="copyOutputDir(selected)">{{ t("tasks.detail.copyOutputDir") }}</button></dd></div>
        </dl>
        <section v-if="selectedError" class="task-failure">
          <header>{{ t("tasks.detail.errorTitle") }}</header>
          <p class="task-failure-message">{{ selectedError }}</p>
          <pre v-if="selectedErrorLines.length" class="log-lines">{{ selectedErrorLines.join("\n") }}</pre>
        </section>
        <div class="task-detail-actions">
          <a class="ghost-button" :href="`/train-log?task_id=${encodeURIComponent(selected.id)}`" target="_blank" rel="noreferrer">{{ t("tasks.detail.viewLog") }}</a>
          <RouterLink v-if="selected.status !== 'QUEUED' && !selectedIsMaintenance" class="ghost-button" to="/tensorboard.html?from=tasks">{{ t("tasks.detail.tensorboard") }}</RouterLink>
          <button v-if="isTerminal(selected) && !selectedIsMaintenance" class="ghost-button" :disabled="actionBusyId === selected.id" @click="importToTraining(selected)">{{ t("tasks.detail.importTrain") }}</button>
          <button v-if="!selectedIsMaintenance" class="ghost-button" :disabled="actionBusyId === selected.id" @click="exportTaskConfig(selected)">{{ t("tasks.detail.exportConfig") }}</button>
          <button v-if="!selectedIsMaintenance" class="ghost-button" :disabled="actionBusyId === selected.id" @click="copyTaskConfig(selected)">{{ t("tasks.detail.copyConfig") }}</button>
        </div>
        <section v-if="!selectedIsMaintenance" class="task-preview-strip task-placeholder" :class="{ 'has-data': previews.length > 0, collapsed: !previewOpen }">
          <header class="task-panel-header" @click="previewOpen = !previewOpen">
            <span>{{ t("tasks.detail.previewTitle") }}</span>
            <button type="button" class="log-toggle" @click.stop="previewOpen = !previewOpen">{{ previewOpen ? t("tasks.log.collapse") : t("tasks.log.expand") }}</button>
          </header>
          <template v-if="previewOpen">
            <div v-if="previews.length" class="preview-scroll"><div v-for="image in previews" :key="image.name" class="preview-item"><button type="button" class="preview-thumb" @click="lightboxImage = image"><img :src="image.thumb_url || image.url" :alt="image.name" loading="lazy"></button><span v-if="imageLabel(image)">{{ imageLabel(image) }}</span></div></div>
            <p v-else-if="!previewEnabled">{{ t("tasks.detail.previewDisabled") }}</p>
            <p v-else>{{ t("tasks.detail.previewEmpty") }}</p>
          </template>
        </section>
        <section v-if="!selectedIsMaintenance" class="task-loss-panel task-placeholder" :class="{ 'has-data': hasLoss, collapsed: !lossOpen }">
          <header class="task-panel-header" @click="lossOpen = !lossOpen">
            <span>{{ t("tasks.detail.lossTitle") }}</span>
            <button type="button" class="log-toggle" @click.stop="lossOpen = !lossOpen">{{ lossOpen ? t("tasks.log.collapse") : t("tasks.log.expand") }}</button>
          </header>
          <template v-if="lossOpen">
            <LossChart v-if="hasLoss" :series="lossSeries" />
            <p v-else>{{ t("tasks.detail.lossEmpty") }}</p>
          </template>
        </section>
        <TaskLogPanel :task-id="selected.id" :status="selected.status" />
      </section>
      <section v-else class="task-detail task-detail-empty"><p>{{ t("tasks.detail.empty") }}</p></section>
    </div>

    <el-dialog :model-value="!!lightboxImage" :title="lightboxImage ? (imageLabel(lightboxImage) || lightboxImage.name) : ''" align-center class="preview-lightbox" @update:model-value="lightboxImage = null">
      <img v-if="lightboxImage" class="lightbox-image" :src="lightboxImage.url" :alt="lightboxImage.name">
    </el-dialog>

    <el-dialog v-model="purgeOpen" :title="t('tasks.purge.title')" align-center class="purge-dialog">
      <div class="purge-form">
        <label class="purge-keep">
          <span>{{ t("tasks.purge.keepLabel") }}</span>
          <el-input-number v-model="purgeKeepLast" :min="0" :max="999" size="small" />
          <span>{{ t("tasks.purge.keepSuffix") }}</span>
        </label>
        <p class="purge-hint">{{ t("tasks.purge.keepHint") }}</p>
      </div>
      <template #footer>
        <button class="ghost-button" @click="purgeOpen = false">{{ t("tasks.purge.cancel") }}</button>
        <button class="danger-action" :disabled="purgeBusy" @click="purgeTasks">{{ t("tasks.purge.confirmButton") }}</button>
      </template>
    </el-dialog>
  </div>
</template>
