import { apiData, apiRequest } from "./client"

export type TaggerPhase = "idle" | "downloading" | "tagging" | "captioning" | "done" | "error" | "pending" | "cancelling"
export type CaptionMode = "natural" | "combined" | "tag"
export type CaptionJobPhase = "idle" | "pending" | "captioning" | "cancelling" | "cancelled" | "done" | "error"
export type CaptionConflictAction = "ignore" | "copy" | "prepend" | "append"
export interface TaggerStep { current: number; total: number; filename: string; bytes_current: number; bytes_total: number; percent: number }
export interface TaggerStatus { phase: TaggerPhase; message: string; model: string; download: TaggerStep; tagging: TaggerStep; error?: string | null; updated_at: number }
export interface TaggerRequest {
  path: string; interrogator_model: string; threshold: number; character_threshold: number
  add_rating_tag: boolean; add_model_tag: boolean; additional_tags: string; exclude_tags: string
  escape_tag: boolean; batch_input_recursive: boolean; batch_output_action_on_conflict: CaptionConflictAction
  replace_underscore: boolean; download_endpoint: string; replace_underscore_excludes: string
}

export interface CaptionJobRequest {
  path: string
  mode: CaptionMode
  recursive: boolean
  allow_local_fallback?: boolean
  profile_id?: string
  prompt: string
  language: string
  layout: "tags_then_caption" | "caption_then_tags" | "tags_only" | "caption_only"
  conflict_action: "ignore" | "copy" | "prepend" | "append"
  interrogator_model: string
  download_endpoint: string
  threshold: number
  character_threshold: number
  add_rating_tag: boolean
  add_model_tag: boolean
  additional_tags: string
  exclude_tags: string
  escape_tag: boolean
  replace_underscore: boolean
  replace_underscore_excludes: string
}

export interface CaptionJobStatus {
  job_id: string | null
  phase: CaptionJobPhase
  mode: CaptionMode | null
  message: string
  current: number
  total: number
  filename: string
  succeeded: number
  failed: number
  cancelled: number
  errors: Array<{ filename?: string; code?: string; message?: string }>
  updated_at: number
}

export const taggerApi = {
  status: () => apiData<TaggerStatus>("/api/tagger/status"),
  start: (body: TaggerRequest) => apiRequest("/api/interrogate", { method: "POST", body: JSON.stringify(body) }),
  prefetch: (interrogator_model: string, download_endpoint: string) => apiRequest("/api/tagger/prefetch", { method: "POST", body: JSON.stringify({ interrogator_model, download_endpoint }) }),
  cancel: () => apiRequest("/api/tagger/cancel", { method: "POST" }),
  reset: () => apiRequest("/api/tagger/reset", { method: "POST" }),
  captionStatus: () => apiData<CaptionJobStatus>("/api/tagger/jobs"),
  captionStart: (body: CaptionJobRequest) => apiData<CaptionJobStatus>("/api/tagger/jobs", { method: "POST", body: JSON.stringify(body) }),
  captionCancel: () => apiData<CaptionJobStatus>("/api/tagger/jobs/cancel", { method: "POST" }),
  captionRetryFailed: () => apiData<CaptionJobStatus>("/api/tagger/jobs/retry-failed", { method: "POST" }),
  captionPreview: (body: CaptionJobRequest & { image_path: string }) => apiData<{ caption: string; language: string; profile_id: string; profile_revision: string }>("/api/tagger/jobs/preview", { method: "POST", body: JSON.stringify(body) }),
}
