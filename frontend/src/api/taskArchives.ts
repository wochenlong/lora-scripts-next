import { apiData } from "./client"

export interface TaskArchive {
  id: string
  task_id?: string
  name: string
  train_type?: string | null
  config: Record<string, unknown>
  metadata?: Record<string, unknown>
  created_at?: string
  updated_at?: string
}

interface ArchiveListData { archives: TaskArchive[] }

export const taskArchivesApi = {
  list: (trainType?: string) => apiData<ArchiveListData>(
    `/api/user-data/task-archives${trainType ? `?train_type=${encodeURIComponent(trainType)}` : ""}`,
  ).then((data) => data.archives),
  get: (id: string) => apiData<TaskArchive>(`/api/user-data/task-archives/${encodeURIComponent(id)}`),
}
