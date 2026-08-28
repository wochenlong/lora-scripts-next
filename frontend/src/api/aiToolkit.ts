import { apiData } from "./client"
import type { DownloadSourcesPayload } from "../engines/downloadSources"

export type AiToolkitState = "unknown" | "installing" | "auditing" | "ready" | "broken" | "installed_unverified" | "not_installed" | "disabled"

export interface AiToolkitAudit {
  ok?: boolean
  errors?: string[]
  warnings?: string[]
}

export interface AiToolkitFacts {
  task_id?: string
  audit?: AiToolkitAudit
}

export interface AiToolkitRuntime {
  toolkit_root?: string
  python?: string
  output_dir?: string
  logging_dir?: string
  cache_dir?: string
  external_runtime_exists?: boolean
}

export interface AiToolkitStatus {
  state: AiToolkitState
  feature_enabled: boolean
  reason?: string
  message?: string
  source?: string
  python?: string
  train_types?: string[]
  facts?: AiToolkitFacts
  runtime?: AiToolkitRuntime
}

export interface AiToolkitInstallResult {
  already_ready?: boolean
  task_id?: string
  log_stream?: string
  progress_stream?: string
  status?: AiToolkitStatus
}

export interface AiToolkitPreflightResult {
  ok: boolean
  errors?: string[]
  warnings?: string[]
  facts?: Record<string, unknown>
}

function installBody(downloadSources?: DownloadSourcesPayload) {
  return JSON.stringify({ dry_run: false, ...(downloadSources || {}) })
}

export const aiToolkitApi = {
  status: () => apiData<AiToolkitStatus>("/api/engines/ai-toolkit/status"),
  install: (downloadSources?: DownloadSourcesPayload) =>
    apiData<AiToolkitInstallResult>("/api/engines/ai-toolkit/install", { method: "POST", body: installBody(downloadSources) }),
  repair: (downloadSources?: DownloadSourcesPayload) =>
    apiData<AiToolkitInstallResult>("/api/engines/ai-toolkit/repair", { method: "POST", body: installBody(downloadSources) }),
  uninstall: () => apiData<{ status?: AiToolkitStatus }>("/api/engines/ai-toolkit/uninstall", { method: "POST", body: "{}" }),
  preflight: (config: Record<string, unknown>) => apiData<AiToolkitPreflightResult>("/api/engines/ai-toolkit/preflight", { method: "POST", body: JSON.stringify(config) }),
}
