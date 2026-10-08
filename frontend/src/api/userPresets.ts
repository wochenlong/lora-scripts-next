import { apiData } from "./client"

export interface UserPreset {
  id: string
  name: string
  train_type?: string | null
  description?: string | null
  config: Record<string, unknown>
  created_at?: string
  updated_at?: string
}

interface PresetListData { presets: UserPreset[] }

export const userPresetsApi = {
  list: (trainType?: string) => apiData<PresetListData>(
    `/api/user-data/presets${trainType ? `?train_type=${encodeURIComponent(trainType)}` : ""}`,
  ).then((data) => data.presets),
  create: (payload: Pick<UserPreset, "name" | "config"> & Partial<Pick<UserPreset, "train_type" | "description">>) =>
    apiData<UserPreset>("/api/user-data/presets", { method: "POST", body: JSON.stringify(payload) }),
  update: (id: string, payload: Partial<Pick<UserPreset, "name" | "config" | "description">>) =>
    apiData<UserPreset>(`/api/user-data/presets/${encodeURIComponent(id)}`, { method: "PATCH", body: JSON.stringify(payload) }),
  remove: (id: string) =>
    apiData<{ removed: boolean }>(`/api/user-data/presets/${encodeURIComponent(id)}`, { method: "DELETE" }),
}
