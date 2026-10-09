import { apiData } from "./client"
import type { DownloadSourcesPayload } from "../engines/downloadSources"

export type KohyaState = "unknown" | "installing" | "auditing" | "ready" | "broken" | "installed_unverified" | "not_installed" | "disabled"

export interface KohyaAudit {
  ok?: boolean
  errors?: string[]
}

export interface KohyaFacts {
  task_id?: string
  audit?: KohyaAudit
}

export interface KohyaStatus {
  state: KohyaState
  feature_enabled: boolean
  reason?: string
  message?: string
  train_types?: string[]
  facts?: KohyaFacts
  runtime?: {
    environment_path?: string
    python?: string
  }
}

export interface KohyaInstallResult {
  already_ready?: boolean
  task_id?: string
  log_stream?: string
  progress_stream?: string
  status?: KohyaStatus
}

function installBody(downloadSources?: DownloadSourcesPayload) {
  return JSON.stringify({ dry_run: false, ...(downloadSources || {}) })
}

export const kohyaApi = {
  status: () => apiData<KohyaStatus>("/api/engines/kohya/status"),
  install: (downloadSources?: DownloadSourcesPayload) =>
    apiData<KohyaInstallResult>("/api/engines/kohya/install", { method: "POST", body: installBody(downloadSources) }),
  repair: (downloadSources?: DownloadSourcesPayload) =>
    apiData<KohyaInstallResult>("/api/engines/kohya/repair", { method: "POST", body: installBody(downloadSources) }),
  uninstall: () => apiData<{ status?: KohyaStatus }>("/api/engines/kohya/uninstall", { method: "POST", body: "{}" }),
}
