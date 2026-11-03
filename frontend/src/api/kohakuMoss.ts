import { apiData } from "./client"
import type { EngineRuntimeState } from "../engines/catalog"
import type { DownloadSourcesPayload } from "../engines/downloadSources"
import type { FormModel } from "../schema/adapter"
import type { PreflightResult } from "./training"

export interface KohakuMossStatus {
  state: EngineRuntimeState
  feature_enabled: boolean
  reason?: string
  message?: string
  facts?: {
    task_id?: string
    audit?: { ok?: boolean; errors?: string[]; warnings?: string[] }
  }
  runtime?: {
    python?: string
    environment_path?: string
    source?: string
    external_runtime_exists?: boolean
  }
}

export interface KohakuMossInstallResult {
  already_ready?: boolean
  task_id?: string
  log_stream?: string
  progress_stream?: string
  status?: KohakuMossStatus
}

function installBody(downloadSources?: DownloadSourcesPayload) {
  return JSON.stringify({ dry_run: false, ...(downloadSources || {}) })
}

export const kohakuMossApi = {
  status: () => apiData<KohakuMossStatus>("/api/engines/kohaku-moss/status"),
  install: (downloadSources?: DownloadSourcesPayload) => apiData<KohakuMossInstallResult>("/api/engines/kohaku-moss/install", { method: "POST", body: installBody(downloadSources) }),
  repair: (downloadSources?: DownloadSourcesPayload) => apiData<KohakuMossInstallResult>("/api/engines/kohaku-moss/repair", { method: "POST", body: installBody(downloadSources) }),
  uninstall: () => apiData<{ status?: KohakuMossStatus }>("/api/engines/kohaku-moss/uninstall", { method: "POST", body: "{}" }),
  preflight: (config: FormModel) => apiData<PreflightResult>("/api/engines/kohaku-moss/preflight", { method: "POST", body: JSON.stringify(config) }),
  dryRun: (config: FormModel) => apiData<PreflightResult>("/api/engines/kohaku-moss/dry-run", { method: "POST", body: JSON.stringify(config) }),
  installLogUrl: (taskId: string) => `/api/engines/kohaku-moss/install/log/stream/${encodeURIComponent(taskId)}`,
  installProgressUrl: (taskId: string) => `/api/engines/kohaku-moss/install/progress/stream/${encodeURIComponent(taskId)}`,
}
