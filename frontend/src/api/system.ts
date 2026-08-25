import { apiData } from "./client"

export interface VersionData {
  version: string
}

export interface UpdateCheckData {
  current: string
  latest?: string | null
  has_update: boolean
  release_url?: string
  release_notes?: string
  error?: string | null
  channel?: string
  modelscope_url?: string
  current_is_prerelease?: boolean
}

export const systemApi = {
  getVersion: () => apiData<VersionData>("/api/version"),
  checkUpdate: (force = false) =>
    apiData<UpdateCheckData>(`/api/check_update${force ? "?force=true" : ""}`),
}
