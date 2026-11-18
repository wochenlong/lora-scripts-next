import { apiData } from "./client"
import type { DownloadSourcesPayload } from "../engines/downloadSources"

export type KohyaState = "unknown" | "installing" | "auditing" | "ready" | "broken" | "installed_unverified" | "not_installed" | "disabled"

export interface KohyaAudit {
  ok?: boolean
  errors?: string[]
}

export interface KohyaDriftEntry {
  name: string
  spec: string
  installed?: string | null
}

export interface KohyaFacts {
  task_id?: string
  audit?: KohyaAudit
  mode?: "standalone" | "main_env"
  main_env_python?: string
  main_env_rejected?: { python?: string; errors?: string[] }
  update_available?: boolean
  drift?: KohyaDriftEntry[]
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

export interface KohyaUpgradeResult {
  already_up_to_date?: boolean
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
  upgrade: (downloadSources?: DownloadSourcesPayload) =>
    apiData<KohyaUpgradeResult>("/api/engines/kohya/upgrade", { method: "POST", body: installBody(downloadSources) }),
}
