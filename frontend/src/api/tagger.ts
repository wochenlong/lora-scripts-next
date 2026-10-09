import { apiData, apiRequest } from "./client"
import { readDownloadSources, resolveHfEndpoint } from "../engines/downloadSources"

export type TaggerPhase = "idle" | "downloading" | "tagging" | "done" | "error" | "pending" | "cancelling"
export type CaptionConflictAction = "ignore" | "copy" | "prepend"
export interface TaggerStep { current: number; total: number; filename: string; bytes_current: number; bytes_total: number; percent: number }
export interface TaggerStatus { phase: TaggerPhase; message: string; model: string; download: TaggerStep; tagging: TaggerStep; error?: string | null; updated_at: number }
export interface TaggerRequest {
  path: string; interrogator_model: string; threshold: number; character_threshold: number
  add_rating_tag: boolean; add_model_tag: boolean; additional_tags: string; exclude_tags: string
  escape_tag: boolean; batch_input_recursive: boolean; batch_output_action_on_conflict: CaptionConflictAction
  replace_underscore: boolean; replace_underscore_excludes: string
}

function withDownloadEndpoint<T extends object>(body: T) {
  return { ...body, download_endpoint: resolveHfEndpoint(readDownloadSources()) }
}

export const taggerApi = {
  models: async () => (await apiData<{ models: Array<{ id: string; downloaded: boolean }> }>("/api/tagger/models")).models,
  status: () => apiData<TaggerStatus>("/api/tagger/status"),
  start: (body: TaggerRequest) => apiRequest("/api/interrogate", { method: "POST", body: JSON.stringify(withDownloadEndpoint(body)) }),
  prefetch: (interrogator_model: string) => apiRequest("/api/tagger/prefetch", { method: "POST", body: JSON.stringify(withDownloadEndpoint({ interrogator_model })) }),
  cancel: () => apiRequest("/api/tagger/cancel", { method: "POST" }),
  reset: () => apiRequest("/api/tagger/reset", { method: "POST" }),
}
