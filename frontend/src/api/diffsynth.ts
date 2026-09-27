import { apiData } from "./client"
import type { DownloadSourcesPayload } from "../engines/downloadSources"

export type DiffSynthState = "unknown" | "installing" | "auditing" | "ready" | "broken" | "installed_unverified" | "not_installed" | "disabled"

export interface DiffSynthAudit {
  ok?: boolean
  errors?: string[]
  warnings?: string[]
}

export interface DiffSynthFacts {
  task_id?: string
  audit?: DiffSynthAudit
}

export interface DiffSynthRuntime {
  source?: string
  environment_path?: string
  python?: string
  output_dir?: string
  logging_dir?: string
  cache_dir?: string
  external_runtime_exists?: boolean
}

export interface DiffSynthStatus {
  state: DiffSynthState
  feature_enabled: boolean
  reason?: string
  message?: string
  source?: string
  python?: string
  facts?: DiffSynthFacts
  runtime?: DiffSynthRuntime
}

export interface DiffSynthInstallResult {
  already_ready?: boolean
  task_id?: string
  log_stream?: string
  progress_stream?: string
  status?: DiffSynthStatus
}

export interface DiffSynthPreflightResult {
  ok: boolean
  errors?: string[]
  warnings?: string[]
  facts?: Record<string, unknown>
}

function installBody(downloadSources?: DownloadSourcesPayload) {
  return JSON.stringify({ dry_run: false, ...(downloadSources || {}) })
}

export const diffsynthApi = {
  status: () => apiData<DiffSynthStatus>("/api/engines/diffsynth/status"),
  install: (downloadSources?: DownloadSourcesPayload) =>
    apiData<DiffSynthInstallResult>("/api/engines/diffsynth/install", { method: "POST", body: installBody(downloadSources) }),
  repair: (downloadSources?: DownloadSourcesPayload) =>
    apiData<DiffSynthInstallResult>("/api/engines/diffsynth/repair", { method: "POST", body: installBody(downloadSources) }),
  uninstall: () => apiData<{ status?: DiffSynthStatus }>("/api/engines/diffsynth/uninstall", { method: "POST", body: "{}" }),
  preflight: (config: Record<string, unknown>) => apiData<DiffSynthPreflightResult>("/api/engines/diffsynth/preflight", { method: "POST", body: JSON.stringify(config) }),
}
