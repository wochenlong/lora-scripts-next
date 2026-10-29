import { invoke } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'

export interface Check {
  name: string
  ok: boolean
  detail: string
}

export interface Report {
  root: string
  uv: boolean
  python: boolean
  source: boolean
  environment: boolean
  frontend: boolean
  running: boolean
  healthy: boolean
  version: string | null
  port: number | null
  checks: Check[]
  logs: string[]
  current_release: string | null
  previous_known_good: string | null
  profile_path: string
  versions: VersionView[]
  interrupted: string[]
  error?: string
}

export interface VersionView {
  id: string
  channel: string
  version: string
  commit: string
  download_bytes: number
  source_bytes: number
  installed: boolean
  source_ok: boolean
  environment_ok: boolean
  current: boolean
  known_good: boolean
  managed_recipe?: boolean
}

export type ReportCommand = 'inspect' | 'bootstrap' | 'restore_trainer' | 'install_environment' | 'start_trainer'
export type ReleaseCommand = 'install_release' | 'select_release' | 'remove_release'

export function runCommand(command: ReportCommand, root: string) {
  return invoke<Report>(command, { root })
}

export function runReleaseCommand(command: ReleaseCommand, root: string, releaseId: string) {
  return invoke<Report>(command, { root, releaseId })
}

export const rollbackRelease = (root: string) => invoke<Report>('rollback_release', { root })
export const chooseDirectory = () => invoke<string | null>('choose_directory')
export const stopTrainer = () => invoke<void>('stop_trainer')
export const openTrainer = () => invoke<void>('open_trainer')
export const listenToLogs = (handler: (line: string) => void) =>
  listen<string>('launcher:log', (event) => handler(event.payload))

export interface NetworkSettings {
  mode?: 'auto' | 'system' | 'manual' | 'direct'
  http_proxy?: string | null
  https_proxy?: string | null
  no_proxy?: string | null
}
export interface NetworkSettingsView {
  settings: NetworkSettings
  diagnostic: { network_mode: string; source: string; http_proxy: string; https_proxy: string; no_proxy: string; warning: string; proxy_enabled: boolean }
}
export const loadNetworkSettings = (root: string) => invoke<NetworkSettingsView>('load_network_settings', { root })
export const saveNetworkSettings = (root: string, settings: NetworkSettings) => invoke<NetworkSettingsView>('save_network_settings', { root, settings })

export interface OperationSnapshot {
  schema_version: number
  id: string
  kind: 'download' | 'execute' | 'repair'
  phase: 'preparing' | 'downloading' | 'executing' | 'verifying' | 'committing' | 'recovering'
  status: 'running' | 'succeeded' | 'failed' | 'cancelled' | 'interrupted'
  cancel_requested: boolean
  event_seq: number
  started_at: number
  updated_at: number
  error: { code: string; message: string } | null
}
export interface OperationEvent {
  seq: number
  phase: OperationSnapshot['phase']
  status: OperationSnapshot['status']
  message: string
}
export const prefetchRelease = (root: string, releaseId: string) => invoke<OperationSnapshot>('prefetch_release', { root, releaseId })
export const installManagedRelease = (root: string, releaseId: string) => invoke<OperationSnapshot>('install_managed_release', { root, releaseId })
export const operationSnapshot = (operationId: string) => invoke<OperationSnapshot>('operation_snapshot', { operationId })
export const operationEvents = (operationId: string, afterSeq: number) => invoke<OperationEvent[]>('operation_events', { operationId, afterSeq })
export const operationHistory = (root: string) => invoke<OperationSnapshot[]>('operation_history', { root })
export const cancelOperation = (operationId: string) => invoke<'accepted' | 'already_requested' | 'already_finished' | 'commit_in_progress'>('cancel_operation', { operationId })

export interface GeneratedFile {
  path: string
  kind: string
  required: boolean
  present: boolean
  content_verified: boolean
}
export interface PackageIntegrity {
  name: string
  version: string
  status: 'verified_original_files' | 'missing' | 'damaged' | 'unsupported'
  missing: string[]
  damaged: string[]
  unsupported: string[]
  issues: string[]
  generated: GeneratedFile[]
  paths: string[]
}
export interface GuiDiagnosis {
  root: string
  release_id: string
  instance_id: string
  generation: number
  binding_generation: number
  dirty: boolean
  recipe_sha256: string
  source_error: string | null
  installed_metadata_error: string | null
  recovery_pending: boolean
  integrity: { environment: string; packages: PackageIntegrity[] }
}
export interface GuiRepairPreview {
  instance_id: string
  generation: number
  package: string
  version: string
  paths: string[]
  plan_sha256: string
  before_original_files_verified: boolean
  before_runtime_check: string
  boundary: string
}
export const diagnoseGui = (root: string, releaseId: string) => invoke<GuiDiagnosis>('diagnose_gui', { root, releaseId })
export const planGuiRepair = (root: string, releaseId: string, packageName: string) => invoke<GuiRepairPreview>('plan_gui_repair', { root, releaseId, package: packageName })
export const repairGuiPackage = (root: string, releaseId: string, packageName: string, planSha256: string) => invoke<OperationSnapshot>('repair_gui_package', { root, releaseId, package: packageName, planSha256 })
export const recoverGuiRepair = (root: string, releaseId: string) => invoke<OperationSnapshot>('recover_gui_repair', { root, releaseId })
export interface SourceRepairPreview {
  release_id: string
  replacement_root: string
  expected_source_files: string[]
  generated_files: string[]
  source_integrity_error: string | null
  boundary: string
}
export const previewSourceRepair = (root: string, releaseId: string) => invoke<SourceRepairPreview>('preview_source_repair', { root, releaseId })
export const repairManagedSource = (root: string, releaseId: string) => invoke<OperationSnapshot>('repair_managed_source', { root, releaseId })

export interface BasePythonRepairPreview {
  schema_version: number
  component_id: string
  root: string
  target: string
  replacement_scope: string
  expected_files: string[]
  integrity_error: string | null
  references: { release_id: string; instance_id: string; storage_version: number; environment: string; generation: number; initial_dirty: boolean }[]
  blockers: string[]
  pending_transaction: string | null
  plan_sha256: string
  repair_available: boolean
  recovery_available: boolean
  recovery_error: string | null
}
export const previewBasePythonRepair = (root: string) => invoke<BasePythonRepairPreview>('preview_base_python_repair', { root })
export const repairBasePython = (root: string, releaseId: string, planSha256: string) => invoke<OperationSnapshot>('repair_base_python', { root, releaseId, planSha256 })
export const recoverBasePython = (root: string, releaseId: string) => invoke<OperationSnapshot>('recover_base_python', { root, releaseId })

export interface DownloadCounters {
  observed_body_bytes: number
  uncertain_charge_bytes: number
  requests: number
  retries: number
  redirects: number
  cache_hits: number
}
export interface DownloadOperationLimits {
  max_charged_body_bytes: number
  max_requests: number
  max_retries: number
  max_redirects: number
  max_elapsed_ms: number
}
export interface OperationDownloadReceipt {
  schema_version: number
  measurement: string
  workspace_id: string
  operation_id: string
  retry_of: string | null
  outcome: 'succeeded' | 'failed' | 'cancelled' | 'interrupted'
  accounting_complete: boolean
  started_at_ms: number
  finished_at_ms: number
  policy_revision: number
  limits: DownloadOperationLimits
  counters: DownloadCounters
  start_generation: number
  end_generation: number
  root_start_counters: DownloadCounters
  root_end_counters: DownloadCounters
}
export interface DownloadBudgetView {
  measurement: string
  enabled: boolean
  coverage_prior_history: 'no_prior_artifact_evidence' | 'not_measured' | null
  policy_revision: number | null
  root_cap_body_bytes: number | null
  counters: DownloadCounters
  reserved_body_bytes: number
  remaining_body_bytes: number | null
  generation: number | null
  active_operation: string | null
  active_counters: DownloadCounters | null
  operation_remaining_body_bytes: number | null
  pending_reconciliation: boolean
}
export interface BudgetSnapshot {
  budget: DownloadBudgetView
  latest_receipt: OperationDownloadReceipt | null
}
export const getDownloadBudget = (root: string) => invoke<BudgetSnapshot>('get_download_budget', { root })
export const saveDownloadBudget = (root: string, expectedRevision: number | null, rootBodyCapBytes: number) =>
  invoke<BudgetSnapshot>('save_download_budget', { root, expectedRevision, rootBodyCapBytes })
export const reconcileDownloadBudget = (root: string) => invoke<BudgetSnapshot>('reconcile_download_budget', { root })
