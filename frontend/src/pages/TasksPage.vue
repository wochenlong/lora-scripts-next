<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { Refresh } from "@element-plus/icons-vue"
import { storeToRefs } from "pinia"
import { useI18n } from "vue-i18n"
import { useTasksStore } from "../stores/tasks"
import type { TaskStatus, TrainingTask } from "../api/tasks"

const store = useTasksStore()
const { tasks, loading, error, terminatingId } = storeToRefs(store)
const { t } = useI18n()
let timer: number | undefined

const statusLabels: Record<TaskStatus, string> = {
  CREATED: "已创建",
  RUNNING: "运行中",
  FINISHED: "已完成",
  TERMINATED: "已终止",
  FAILED: "失败",
}

const activeTab = ref<"running" | "recent">("running")
const selectedId = ref("")

const orderedTasks = computed(() => [...tasks.value].reverse())
const runningList = computed(() => orderedTasks.value.filter((task) => task.status === "RUNNING" || task.status === "CREATED"))
const recentList = computed(() => orderedTasks.value.filter((task) => task.status !== "RUNNING" && task.status !== "CREATED"))
const visibleList = computed(() => activeTab.value === "running" ? runningList.value : recentList.value)
const selected = computed(() => tasks.value.find((task) => task.id === selectedId.value))

function taskName(task: TrainingTask) {
  return String(task.metadata.output_name || task.metadata.trainer_file || task.metadata.backend || "训练任务")
}

function taskDetail(task: TrainingTask) {
  return String(task.metadata.config_path || task.metadata.command || "暂无任务描述")
}

function select(task: TrainingTask) {
  selectedId.value = task.id
}

watch(visibleList, (list) => {
  if (!list.some((task) => task.id === selectedId.value)) selectedId.value = list[0]?.id ?? ""
}, { immediate: true })

async function terminate(task: TrainingTask) {
  try {
    await ElMessageBox.confirm(`确定要停止任务 ${task.id} 吗？`, "终止训练", {
      confirmButtonText: "停止任务",
      cancelButtonText: "取消",
      type: "warning",
    })
    await store.terminate(task.id)
    ElMessage.success("停止任务成功")
  } catch (caught) {
    if (caught !== "cancel" && caught !== "close") {
      ElMessage.error(caught instanceof Error ? caught.message : "停止任务失败")
    }
  }
}

onMounted(async () => {
  await store.refresh()
  timer = window.setInterval(() => store.refresh({ silent: true }), 2000)
})

onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <div class="tasks-board">
    <header class="tasks-board-header">
      <h1>{{ t("tasks.title") }}</h1>
      <button class="ghost-button" :disabled="loading" @click="store.refresh()"><el-icon><Refresh /></el-icon>{{ t("tasks.refresh") }}</button>
    </header>

    <div v-if="error" class="task-error"><strong>无法读取任务</strong><span>{{ error }}</span><button @click="store.refresh()">重试</button></div>
    <div v-else-if="loading && !tasks.length" class="task-empty">正在读取任务列表…</div>
    <div v-else-if="!tasks.length" class="task-empty"><strong>当前没有训练任务</strong><span>从训练页提交任务后，将在这里显示状态和日志入口。</span></div>

    <div v-else class="tasks-columns">
      <aside class="tasks-list-panel">
        <div class="tasks-tabs" role="group" aria-label="任务筛选">
          <button :class="{ active: activeTab === 'running' }" @click="activeTab = 'running'">{{ t("tasks.tabs.running") }}<b>{{ runningList.length }}</b></button>
          <button :class="{ active: activeTab === 'recent' }" @click="activeTab = 'recent'">{{ t("tasks.tabs.recent") }}<b>{{ recentList.length }}</b></button>
        </div>
        <p v-if="!visibleList.length" class="tasks-tab-empty">暂无任务</p>
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
        <p class="task-deferred-note">{{ t("tasks.detail.logsDeferred") }}</p>
      </section>
      <section v-else class="task-detail task-detail-empty"><p>{{ t("tasks.detail.empty") }}</p></section>
    </div>
  </div>
</template>
