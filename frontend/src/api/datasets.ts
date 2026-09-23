import { apiData } from "./client"

export interface DatasetsRoot { root: string; default: string; exists: boolean }
export interface DatasetOverview {
  state: "computing" | "ready" | "error"
  type?: "image" | "image_edit" | null
  type_confidence?: "detected" | "candidate" | "ambiguous" | "override" | null
  targets?: string | null
  refs?: string[] | null
  file_count: number | null
  captioned_count: number | null
  paired_count?: number | null
  unpaired_count?: number | null
  orphan_ref_count?: number | null
  total_bytes: number | null
  updated_at: string | null
  computed_at?: string | null
  error?: string | null
}
export interface DatasetEntry { name: string; path: string; overview: DatasetOverview | null }
export interface DatasetList { root: string; exists: boolean; datasets: DatasetEntry[] }
export interface DatasetCreated { name: string; path: string }
export interface UploadFileItem { file: File; path: string }
export interface UploadFailure { path: string; reason: string }
export interface UploadResult { dataset: string; succeeded: string[]; skipped: string[]; failed: UploadFailure[] }
export interface UploadCheck { conflicts: string[]; invalid: UploadFailure[]; ok: number }
export interface TrashBatch { id: string; dataset: string; deleted_at: string | null; count: number; paths: string[] }
export interface DeleteResult { batch: string | null; deleted: string[]; missing: string[] }
export interface RestoreResult { restored: string[]; conflicts: string[]; missing: string[] }

export const datasetFileUrl = (name: string, path: string) =>
  `/api/datasets/${encodeURIComponent(name)}/file?path=${encodeURIComponent(path)}`
export const datasetDownloadUrl = (name: string) => `/api/datasets/${encodeURIComponent(name)}/download`

export const datasetsApi = {
  getRoot: () => apiData<DatasetsRoot>("/api/datasets/root"),
  updateRoot: (path: string) => apiData<DatasetsRoot>("/api/datasets/root", { method: "PUT", body: JSON.stringify({ path }) }),
  list: () => apiData<DatasetList>("/api/datasets"),
  create: (name: string) => apiData<DatasetCreated>("/api/datasets", { method: "POST", body: JSON.stringify({ name }) }),
  overview: (name: string) => apiData<{ name: string; overview: DatasetOverview }>(`/api/datasets/${encodeURIComponent(name)}/overview`),
  checkUpload: (name: string, paths: string[]) =>
    apiData<UploadCheck>(`/api/datasets/${encodeURIComponent(name)}/upload/check`, { method: "POST", body: JSON.stringify({ paths }) }),
  deleteFiles: (name: string, paths: string[]) =>
    apiData<DeleteResult>(`/api/datasets/${encodeURIComponent(name)}/files`, { method: "DELETE", body: JSON.stringify({ paths }) }),
  deleteDataset: (name: string) => apiData<DeleteResult>(`/api/datasets/${encodeURIComponent(name)}`, { method: "DELETE" }),
  trash: (name: string) => apiData<{ dataset: string; batches: TrashBatch[] }>(`/api/datasets/${encodeURIComponent(name)}/trash`),
  trashAll: () => apiData<{ batches: TrashBatch[] }>("/api/datasets-trash"),
  restoreTrash: (name: string, id: string) =>
    apiData<RestoreResult>(`/api/datasets/${encodeURIComponent(name)}/trash/restore`, { method: "POST", body: JSON.stringify({ id }) }),
  restoreTrashAny: (id: string) => apiData<RestoreResult>("/api/datasets-trash/restore", { method: "POST", body: JSON.stringify({ id }) }),
  emptyTrash: (name: string, id?: string) =>
    apiData<{ removed: number }>(`/api/datasets/${encodeURIComponent(name)}/trash/empty`, { method: "POST", body: JSON.stringify({ id: id ?? null, confirm: true }) }),
  emptyTrashAny: (id?: string) =>
    apiData<{ removed: number }>("/api/datasets-trash/empty", { method: "POST", body: JSON.stringify({ id: id ?? null, confirm: true }) }),
  upload(name: string, files: UploadFileItem[], conflict: "skip" | "overwrite", onProgress?: (percent: number) => void): Promise<UploadResult> {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.open("POST", `/api/datasets/${encodeURIComponent(name)}/upload`)
      if (onProgress) {
        xhr.upload.onprogress = (event) => {
          if (event.lengthComputable) onProgress(Math.round((event.loaded / event.total) * 100))
        }
      }
      xhr.onload = () => {
        let payload: { status?: string; data?: UploadResult; detail?: string; message?: string } = {}
        try {
          payload = JSON.parse(xhr.responseText)
        } catch {
          reject(new Error(`HTTP ${xhr.status}`))
          return
        }
        if (xhr.status >= 200 && xhr.status < 300 && payload.status === "success" && payload.data) resolve(payload.data)
        else reject(new Error(payload.detail || payload.message || `HTTP ${xhr.status}`))
      }
      xhr.onerror = () => reject(new Error("network error"))
      const form = new FormData()
      form.append("conflict", conflict)
      for (const item of files) form.append("files", item.file, item.path)
      xhr.send(form)
    })
  },
}
