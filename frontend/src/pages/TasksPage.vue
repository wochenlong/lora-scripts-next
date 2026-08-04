<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { Refresh } from "@element-plus/icons-vue"
import { storeToRefs } from "pinia"
import { useI18n } from "vue-i18n"
import { useTasksStore } from "../stores/tasks"
import { tasksApi, type TaskMetrics, type TaskPreviewImage, type TaskStatus, type TrainingTask } from "../api/tasks"
import LossChart from "../components/LossChart.vue"

const store = useTasksStore()
const { tasks, loading, error, terminatingId } = storeToRefs(store)
const { t } = useI18n()
let timer: number | undefined
let insightTick = 0

const previews = ref<TaskPreviewImage[]>([])
const metrics = ref<TaskMetrics>({})
let previewSig = ""
let metricsSig = ""
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

async function loadInsights(taskId: string) {
  try {
    const [images, tags] = await Promise.all([tasksApi.previews(taskId), tasksApi.metrics(taskId)])
    const nextPreviewSig = images.map((image) => `${image.name}:${image.mtime}`).join("|")
    if (nextPreviewSig !== previewSig) {
      previewSig = nextPreviewSig
      previews.value = images
    }
    const nextMetricsSig = Object.entries(tags).map(([tag, points]) => `${tag}:${points.length}:${points[points.length - 1]?.step ?? 0}`).join("|")
    if (nextMetricsSig !== metricsSig) {
      metricsSig = nextMetricsSig
      metrics.value = tags
    }
  } catch {}
}

const statusLabels = computed<Record<TaskStatus, string>>(() => ({
  CREATED: t("tasks.status.created"),
  RUNNING: t("tasks.status.running"),
  FINISHED: t("tasks.status.finished"),
  TERMINATED: t("tasks.status.terminated"),
  FAILED: t("tasks.status.failed"),
}))

const activeTab = ref<"running" | "recent">("running")
const selectedId = ref("")

const orderedTasks = computed(() => [...tasks.value].reverse())
const runningList = computed(() => orderedTasks.value.filter((task) => task.status === "RUNNING" || task.status === "CREATED"))
const recentList = computed(() => orderedTasks.value.filter((task) => task.status !== "RUNNING" && task.status !== "CREATED"))
const visibleList = computed(() => activeTab.value === "running" ? runningList.value : recentList.value)
const selected = computed(() => tasks.value.find((task) => task.id === selectedId.value))

function taskName(task: TrainingTask) {
  return String(task.metadata.output_name || task.metadata.trainer_file || task.metadata.backend || t("tasks.defaultName"))
}

function taskDetail(task: TrainingTask) {
  return String(task.metadata.config_path || task.metadata.command || t("tasks.noDetail"))
}

function select(task: TrainingTask) {
  selectedId.value = task.id
}

watch(visibleList, (list) => {
  if (!list.some((task) => task.id === selectedId.value)) selectedId.value = list[0]?.id ?? ""
}, { immediate: true })

watch(selected, (task) => {
  previews.value = []
  metrics.value = {}
  previewSig = ""
  metricsSig = ""
  if (task) loadInsights(task.id)
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

onMounted(async () => {
  await store.refresh()
  timer = window.setInterval(() => {
    store.refresh({ silent: true })
    insightTick += 1
    const task = selected.value
    if (task && (task.status === "RUNNING" || task.status === "CREATED") && insightTick % 4 === 0) loadInsights(task.id)
  }, 2000)
})

onBeforeUnmount(() => window.clearInterval(timer))
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
        <div class="tasks-tabs" role="group" :aria-label="t('tasks.filterAria')">
          <button :class="{ active: activeTab === 'running' }" @click="activeTab = 'running'">{{ t("tasks.tabs.running") }}<b>{{ runningList.length }}</b></button>
          <button :class="{ active: activeTab === 'recent' }" @click="activeTab = 'recent'">{{ t("tasks.tabs.recent") }}<b>{{ recentList.length }}</b></button>
        </div>
        <p v-if="!visibleList.length" class="tasks-tab-empty">{{ t("tasks.tabEmpty") }}</p>
        <article v-for="task in visibleList" :key="task.id" class="task-row" :class="{ selected: task.id === selectedId }" :data-status="task.status.toLowerCase()" @click="select(task)">
          <span class="task-status">{{ statusLabels[task.status] || task.status }}</span>
          <div class="task-row-main"><h2>{{ taskName(task) }}</h2><code>{{ task.id }}</code></div>
        </article>
      </aside>

      <section v-if="selected" class="task-detail" :data-status="selected.status.toLowerCase()">
        <header class="task-detail-header">
          <div class="task-detail-title"><h2>{{ taskName(selected) }}</h2><span class="task-status">{{ statusLabels[selected.status] || selected.status }}</span></div>
          <button v-if="selected.status === 'RUNNING'" class="danger-action" :disabled="terminatingId === selected.id" @click="terminate(selected)">{{ terminatingId === selected.id ? t("tasks.detail.stopping") : t("tasks.detail.stop") }}</button>
        </header>
        <dl class="task-meta-grid">
          <div><dt>{{ t("tasks.detail.taskId") }}</dt><dd><code>{{ selected.id }}</code></dd></div>
          <div><dt>{{ t("tasks.detail.config") }}</dt><dd :title="taskDetail(selected)">{{ taskDetail(selected) }}</dd></div>
          <div><dt>{{ t("tasks.detail.returncode") }}</dt><dd>{{ selected.returncode ?? "-" }}</dd></div>
        </dl>
        <div class="task-detail-actions">
          <a class="ghost-button" :href="`/train-log?task_id=${encodeURIComponent(selected.id)}`" target="_blank" rel="noreferrer">{{ t("tasks.detail.viewLog") }}</a>
          <RouterLink class="ghost-button" to="/tensorboard.html">{{ t("tasks.detail.tensorboard") }}</RouterLink>
        </div>
        <section class="task-preview-strip task-placeholder" :class="{ 'has-data': previews.length > 0 }">
          <header>{{ t("tasks.detail.previewTitle") }}</header>
          <div v-if="previews.length" class="preview-scroll"><a v-for="image in previews" :key="image.name" :href="image.url" target="_blank" rel="noreferrer"><img :src="image.url" :alt="image.name" loading="lazy"></a></div>
          <p v-else>{{ t("tasks.detail.previewEmpty") }}</p>
        </section>
        <section class="task-loss-panel task-placeholder" :class="{ 'has-data': hasLoss }">
          <header>{{ t("tasks.detail.lossTitle") }}</header>
          <LossChart v-if="hasLoss" :series="lossSeries" />
          <p v-else>{{ t("tasks.detail.lossEmpty") }}</p>
        </section>
      </section>
      <section v-else class="task-detail task-detail-empty"><p>{{ t("tasks.detail.empty") }}</p></section>
    </div>
  </div>
</template>
