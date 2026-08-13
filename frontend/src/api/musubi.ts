import { apiData } from "./client"
import type { DownloadSourcesPayload } from "../engines/downloadSources"

export type MusubiState = "unknown" | "installing" | "auditing" | "ready" | "broken" | "installed_unverified" | "not_installed" | "disabled"

export interface MusubiAudit {
  ok?: boolean
  errors?: string[]
  warnings?: string[]
}

export interface MusubiFacts {
  task_id?: string
  audit?: MusubiAudit
}

export interface MusubiRuntime {
  musubi_root?: string
  python?: string
  output_dir?: string
  logging_dir?: string
  cache_dir?: string
  external_runtime_exists?: boolean
}

export interface MusubiStatus {
  state: MusubiState
  feature_enabled: boolean
  reason?: string
  message?: string
  source?: string
  python?: string
  facts?: MusubiFacts
  runtime?: MusubiRuntime
}

export interface MusubiInstallResult {
  already_ready?: boolean
  task_id?: string
  log_stream?: string
  progress_stream?: string
  status?: MusubiStatus
}

export interface MusubiPreflightResult {
  ok: boolean
  errors?: string[]
  warnings?: string[]
  facts?: Record<string, unknown>
}

function installBody(downloadSources?: DownloadSourcesPayload) {
  return JSON.stringify({ dry_run: false, ...(downloadSources || {}) })
}

export const musubiApi = {
  status: () => apiData<MusubiStatus>("/api/plugins/musubi/status"),
  install: (downloadSources?: DownloadSourcesPayload) =>
    apiData<MusubiInstallResult>("/api/plugins/musubi/install", { method: "POST", body: installBody(downloadSources) }),
  repair: (downloadSources?: DownloadSourcesPayload) =>
    apiData<MusubiInstallResult>("/api/plugins/musubi/repair", { method: "POST", body: installBody(downloadSources) }),
  uninstall: () => apiData<{ status?: MusubiStatus }>("/api/plugins/musubi/uninstall", { method: "POST", body: "{}" }),
  preflight: (config: Record<string, unknown>) => apiData<MusubiPreflightResult>("/api/plugins/musubi/preflight", { method: "POST", body: JSON.stringify(config) }),
}
