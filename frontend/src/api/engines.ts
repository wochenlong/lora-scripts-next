import { animaFastApi, type AnimaFastState, type AnimaFastStatus, type InstallResult } from "./animaFast"
import { apiData } from "./client"
import type { EngineRuntimeState } from "../engines/catalog"
import type { TrainingEngine } from "../training/modules"

export interface EngineStatus {
  id: TrainingEngine
  state: EngineRuntimeState
  featureEnabled: boolean
  message?: string
  runtime?: {
    python?: string
    environmentPath?: string
    version?: string
    cuda?: string
    animaRoot?: string
    externalRuntimeExists?: boolean
  }
  facts?: AnimaFastStatus["facts"]
  raw?: AnimaFastStatus
}

export interface EngineActionResult {
  alreadyReady?: boolean
  taskId?: string
  logStream?: string
  progressStream?: string
  status?: EngineStatus
}

function mapAnimaState(state: AnimaFastState | string): EngineRuntimeState {
  if (state === "ready") return "ready"
  if (state === "installing") return "installing"
  if (state === "auditing") return "auditing"
  if (state === "broken") return "broken"
  if (state === "disabled") return "disabled"
  if (state === "installed_unverified") return "installed_unverified"
  if (state === "not_installed") return "not_installed"
  return "unknown"
}

function fromAnima(status: AnimaFastStatus): EngineStatus {
  const runtime = status.runtime || {}
  return {
    id: "anima-fast",
    state: mapAnimaState(status.state),
    featureEnabled: status.feature_enabled !== false,
    message: status.message,
    facts: status.facts,
    runtime: {
      python: runtime.python,
      environmentPath: runtime.environment_path,
      version: runtime.version,
      cuda: runtime.cuda,
      animaRoot: (runtime as { anima_root?: string }).anima_root,
      externalRuntimeExists: (runtime as { external_runtime_exists?: boolean }).external_runtime_exists,
    },
    raw: status,
  }
}

function fromInstall(result: InstallResult): EngineActionResult {
  return {
    alreadyReady: result.already_ready,
    taskId: result.task_id,
    logStream: result.log_stream || result.log_stream_url,
    progressStream: result.progress_stream || result.progress_stream_url,
    status: result.status ? fromAnima(result.status) : undefined,
  }
}

export const enginesApi = {
  async status(id: TrainingEngine): Promise<EngineStatus> {
    if (id === "kohya") {
      return { id: "kohya", state: "ready", featureEnabled: true }
    }
    if (id === "musubi") {
      return { id: "musubi", state: "coming_soon", featureEnabled: false }
    }
    if (id === "anima-fast") {
      return fromAnima(await animaFastApi.status())
    }
    return { id, state: "unknown", featureEnabled: false }
  },

  async list(): Promise<EngineStatus[]> {
    const ids: TrainingEngine[] = ["kohya", "anima-fast", "musubi"]
    return Promise.all(ids.map((id) => this.status(id)))
  },

  async install(id: TrainingEngine): Promise<EngineActionResult> {
    if (id !== "anima-fast") throw new Error(`Install is not supported for engine: ${id}`)
    return fromInstall(await animaFastApi.install())
  },

  async repair(id: TrainingEngine): Promise<EngineActionResult> {
    if (id !== "anima-fast") throw new Error(`Repair is not supported for engine: ${id}`)
    return fromInstall(await animaFastApi.repair())
  },

  async uninstall(id: TrainingEngine): Promise<EngineStatus> {
    if (id !== "anima-fast") throw new Error(`Uninstall is not supported for engine: ${id}`)
    const data = await apiData<{ status?: AnimaFastStatus }>("/api/plugins/anima-lora/uninstall", { method: "POST", body: "{}" })
    return data.status ? fromAnima(data.status) : { id: "anima-fast", state: "not_installed", featureEnabled: true }
  },
}
