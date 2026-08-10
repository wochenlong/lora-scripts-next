import { apiData } from "./client"

export type AssetSource = "huggingface" | "modelscope"

export interface AssetItem {
  key: string
  label: string
  path: string
  exists: boolean
  optional: boolean
  sources: Record<AssetSource, boolean>
}

export interface AssetCheckData {
  train_type: string
  items: AssetItem[]
}

export interface AssetDownloadResult {
  task_id: string
  log_stream: string
  message?: string
}

export const assetsApi = {
  check: (trainType: string, values: Record<string, unknown>) =>
    apiData<AssetCheckData>("/api/assets/check", { method: "POST", body: JSON.stringify({ train_type: trainType, values }) }),
  download: (trainType: string, values: Record<string, unknown>, items: Array<{ key: string; path: string }>, source: AssetSource) =>
    apiData<AssetDownloadResult>("/api/assets/download", { method: "POST", body: JSON.stringify({ train_type: trainType, values, items, source }) }),
}
