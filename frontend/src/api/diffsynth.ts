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
  repair?: {
    actions?: string[]
    diagnosis?: string
  }
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

export interface DiffSynthDiagnosis {
  code: string
  severity?: string
  summary?: string
  detail?: string
  components?: Record<string, string>
  recommended_actions?: string[]
  allows_full_reinstall?: boolean
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
  diagnosis?: DiffSynthDiagnosis
}

export interface DiffSynthInstallResult {
  already_ready?: boolean
  task_id?: string
  log_stream?: string
  progress_stream?: string
  status?: DiffSynthStatus
  diagnosis?: DiffSynthDiagnosis
  plan?: {
    actions?: string[]
    delete?: string[]
    summary?: string
    diagnosis?: DiffSynthDiagnosis
  }
  dry_run?: boolean
}

export interface DiffSynthPreflightResult {
  ok: boolean
  errors?: string[]
  warnings?: string[]
  facts?: Record<string, unknown>
}

function installBody(downloadSources?: DownloadSourcesPayload, extra?: Record<string, unknown>) {
  return JSON.stringify({ dry_run: false, ...(downloadSources || {}), ...(extra || {}) })
}

export const diffsynthApi = {
  status: () => apiData<DiffSynthStatus>("/api/engines/diffsynth/status"),
  diagnose: () => apiData<DiffSynthDiagnosis>("/api/engines/diffsynth/diagnose"),
  install: (downloadSources?: DownloadSourcesPayload) =>
    apiData<DiffSynthInstallResult>("/api/engines/diffsynth/install", { method: "POST", body: installBody(downloadSources) }),
  /** Surgical repair (diagnose → minimal actions). Not a full wipe. */
  repair: (downloadSources?: DownloadSourcesPayload, options?: { action?: string; dryRun?: boolean }) =>
    apiData<DiffSynthInstallResult>("/api/engines/diffsynth/repair", {
      method: "POST",
      body: JSON.stringify({
        dry_run: options?.dryRun ?? false,
        ...(downloadSources || {}),
        ...(options?.action ? { action: options.action } : { mode: "auto" }),
      }),
    }),
  /** Explicit full wipe + reinstall. */
  reinstall: (downloadSources?: DownloadSourcesPayload) =>
    apiData<DiffSynthInstallResult>("/api/engines/diffsynth/repair", {
      method: "POST",
      body: installBody(downloadSources, { action: "full_reinstall" }),
    }),
  uninstall: () => apiData<{ status?: DiffSynthStatus }>("/api/engines/diffsynth/uninstall", { method: "POST", body: "{}" }),
  preflight: (config: Record<string, unknown>) => apiData<DiffSynthPreflightResult>("/api/engines/diffsynth/preflight", { method: "POST", body: JSON.stringify(config) }),
}
