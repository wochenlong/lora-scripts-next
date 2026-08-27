import { apiData } from "./client"
import type { DownloadSourcesPayload } from "../engines/downloadSources"

export type AnimaFastState = "unknown" | "installing" | "auditing" | "ready" | "broken" | "installed_unverified" | "disabled"

export interface AnimaFastAudit {
  ok?: boolean
  errors?: string[]
  warnings?: string[]
}

export interface AnimaFastFacts {
  task_id?: string
  audit?: AnimaFastAudit
}

export interface AnimaFastRuntime {
  python?: string
  environment_path?: string
  version?: string
  cuda?: string
}

export interface AnimaFastStatus {
  state: AnimaFastState
  feature_enabled: boolean
  message?: string
  facts?: AnimaFastFacts
  runtime?: AnimaFastRuntime
}

export interface InstallResult {
  already_ready?: boolean
  task_id?: string
  log_stream?: string
  log_stream_url?: string
  progress_stream?: string
  progress_stream_url?: string
  status?: AnimaFastStatus
}

function installBody(downloadSources?: DownloadSourcesPayload) {
  return JSON.stringify({ dry_run: false, ...(downloadSources || {}) })
}

export const animaFastApi = {
  status: () => apiData<AnimaFastStatus>("/api/engines/anima-fast/status"),
  install: (downloadSources?: DownloadSourcesPayload) =>
    apiData<InstallResult>("/api/engines/anima-fast/install", { method: "POST", body: installBody(downloadSources) }),
  repair: (downloadSources?: DownloadSourcesPayload) =>
    apiData<InstallResult>("/api/engines/anima-fast/repair", { method: "POST", body: installBody(downloadSources) }),
}
