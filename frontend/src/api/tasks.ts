import { apiData, apiRequest } from "./client"

export type TaskStatus = "CREATED" | "RUNNING" | "FINISHED" | "TERMINATED" | "FAILED"

export interface TrainingTask {
  id: string
  status: TaskStatus
  metadata: Record<string, unknown>
  returncode?: number | null
}

interface TasksData {
  tasks: TrainingTask[]
}

export interface TaskPreviewImage {
  name: string
  epoch?: number | null
  mtime: number
  url: string
}

export interface TaskMetricsPoint {
  step: number
  value: number
}

export type TaskMetrics = Record<string, TaskMetricsPoint[]>

export const tasksApi = {
  list: async () => (await apiData<TasksData>("/api/tasks")).tasks,
  terminate: (taskId: string) => apiRequest(`/api/tasks/terminate/${encodeURIComponent(taskId)}`),
  previews: async (taskId: string) => (await apiData<{ images: TaskPreviewImage[] }>(`/api/tasks/${encodeURIComponent(taskId)}/previews`)).images,
  metrics: async (taskId: string) => (await apiData<{ tags: TaskMetrics }>(`/api/tasks/${encodeURIComponent(taskId)}/metrics`)).tags,
}
