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
  step?: number | null
  mtime: number
  url: string
  thumb_url?: string
}

export interface TaskPreviewsData {
  images: TaskPreviewImage[]
  preview_enabled?: boolean | null
}

export interface TaskMetricsPoint {
  step: number
  value: number
}

export type TaskMetrics = Record<string, TaskMetricsPoint[]>

export interface TaskProgress {
  percent?: number
  step?: number
  total_steps?: number
  epoch?: number
  total_epochs?: number
}

export interface TaskMetricsData {
  tags: TaskMetrics
  progress?: TaskProgress
}

export const tasksApi = {
  list: async () => (await apiData<TasksData>("/api/tasks")).tasks,
  terminate: (taskId: string) => apiRequest(`/api/tasks/terminate/${encodeURIComponent(taskId)}`),
  previews: (taskId: string) => apiData<TaskPreviewsData>(`/api/tasks/${encodeURIComponent(taskId)}/previews`),
  metrics: (taskId: string) => apiData<TaskMetricsData>(`/api/tasks/${encodeURIComponent(taskId)}/metrics`),
}
