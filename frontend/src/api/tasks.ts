import { apiData, apiRequest } from "./client"

export type TaskStatus = "CREATED" | "QUEUED" | "RUNNING" | "FINISHED" | "TERMINATED" | "FAILED"

export interface TrainingTask {
  id: string
  status: TaskStatus
  metadata: Record<string, unknown>
  returncode?: number | null
  lane?: "compute" | "maintenance" | string
  queue_position?: number | null
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

export interface TaskLogTail {
  task_id: string
  lines: string[]
  total: number
  done: boolean
}

export const trainLogStreamUrl = (taskId: string) => `/api/train/log/stream/${encodeURIComponent(taskId)}`

export interface TaskRetryResult {
  task_id: string
  task_ids: string[]
  queued: boolean
}

export const tasksApi = {
  list: async () => (await apiData<TasksData>("/api/tasks")).tasks,
  terminate: (taskId: string) => apiRequest(`/api/tasks/terminate/${encodeURIComponent(taskId)}`),
  resume: (taskId: string) => apiRequest(`/api/tasks/resume/${encodeURIComponent(taskId)}`),
  retry: (taskId: string) => apiData<TaskRetryResult>(`/api/tasks/retry/${encodeURIComponent(taskId)}`),
  previews: (taskId: string, signal?: AbortSignal) => apiData<TaskPreviewsData>(`/api/tasks/${encodeURIComponent(taskId)}/previews`, { signal }),
  metrics: (taskId: string, signal?: AbortSignal) => apiData<TaskMetricsData>(`/api/tasks/${encodeURIComponent(taskId)}/metrics`, { signal }),
  logTail: (taskId: string, limit = 240) => apiData<TaskLogTail>(`/api/train/log/tail/${encodeURIComponent(taskId)}?limit=${limit}`),
}
