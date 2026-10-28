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
