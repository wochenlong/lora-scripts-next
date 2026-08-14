import { computed, ref } from "vue"
import { defineStore } from "pinia"
import { tasksApi, type TrainingTask } from "../api/tasks"
import { i18n } from "../i18n"

function isActiveStatus(status: string) {
  return status === "RUNNING" || status === "CREATED"
}

export const useTasksStore = defineStore("tasks", () => {
  const tasks = ref<TrainingTask[]>([])
  const loading = ref(false)
  const error = ref("")
  const terminatingId = ref("")
  /** Unread cue after a task is started elsewhere; cleared when visiting /tasks. */
  const attention = ref(false)
  const runningTasks = computed(() => tasks.value.filter((task) => task.status === "RUNNING"))
  const activeTasks = computed(() => tasks.value.filter((task) => isActiveStatus(task.status)))
  const activeCount = computed(() => activeTasks.value.length)
  const showNavBadge = computed(() => attention.value || activeCount.value > 0)
  const navBadgeCount = computed(() => (activeCount.value > 0 ? activeCount.value : attention.value ? 1 : 0))

  async function refresh(options: { silent?: boolean } = {}) {
    if (!options.silent) loading.value = true
    try {
      tasks.value = await tasksApi.list()
      error.value = ""
    } catch (caught) {
      error.value = caught instanceof Error ? caught.message : i18n.global.t("tasks.listLoadFail")
    } finally {
      loading.value = false
    }
  }

  function markAttention() {
    attention.value = true
  }

  function clearAttention() {
    attention.value = false
  }

  async function terminate(taskId: string) {
    terminatingId.value = taskId
    try {
      await tasksApi.terminate(taskId)
      await refresh({ silent: true })
    } finally {
      terminatingId.value = ""
    }
  }

  return {
    tasks,
    runningTasks,
    activeTasks,
    activeCount,
    attention,
    showNavBadge,
    navBadgeCount,
    loading,
    error,
    terminatingId,
    refresh,
    markAttention,
    clearAttention,
    terminate,
  }
})
