import { animaFastApi, type AnimaFastState, type AnimaFastStatus, type InstallResult } from "./animaFast"
import { musubiApi, type MusubiInstallResult, type MusubiStatus } from "./musubi"
import { aiToolkitApi, type AiToolkitInstallResult, type AiToolkitStatus } from "./aiToolkit"
import { apiData } from "./client"
import type { EngineRuntimeState } from "../engines/catalog"
import { resolvedDownloadSourcesPayload } from "../engines/downloadSources"
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
    musubiRoot?: string
    toolkitRoot?: string
    externalRuntimeExists?: boolean
  }
  facts?: AnimaFastStatus["facts"]
  raw?: AnimaFastStatus | MusubiStatus | AiToolkitStatus
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

function fromMusubi(status: MusubiStatus): EngineStatus {
  const runtime = status.runtime || {}
  return {
    id: "musubi",
    state: mapAnimaState(status.state),
    featureEnabled: status.feature_enabled !== false,
    message: status.message || status.reason,
    facts: status.facts,
    runtime: {
      python: runtime.python || status.python,
      musubiRoot: runtime.musubi_root,
      externalRuntimeExists: runtime.external_runtime_exists,
    },
    raw: status,
  }
}

function fromAiToolkit(status: AiToolkitStatus): EngineStatus {
  const runtime = status.runtime || {}
  return {
    id: "ai-toolkit",
    state: mapAnimaState(status.state),
    featureEnabled: status.feature_enabled !== false,
    message: status.message || status.reason,
    facts: status.facts,
    runtime: {
      python: runtime.python || status.python,
      toolkitRoot: runtime.toolkit_root,
      externalRuntimeExists: runtime.external_runtime_exists,
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

function fromMusubiInstall(result: MusubiInstallResult): EngineActionResult {
  return {
    alreadyReady: result.already_ready,
    taskId: result.task_id,
    logStream: result.log_stream,
    progressStream: result.progress_stream,
    status: result.status ? fromMusubi(result.status) : undefined,
  }
}

function fromAiToolkitInstall(result: AiToolkitInstallResult): EngineActionResult {
  return {
    alreadyReady: result.already_ready,
    taskId: result.task_id,
    logStream: result.log_stream,
    progressStream: result.progress_stream,
    status: result.status ? fromAiToolkit(result.status) : undefined,
  }
}

export const enginesApi = {
  async status(id: TrainingEngine): Promise<EngineStatus> {
    if (id === "kohya") {
      const data = await apiData<{ state?: string; feature_enabled?: boolean }>("/api/engines/kohya/status")
      return {
        id: "kohya",
        state: mapAnimaState(data.state || "ready"),
        featureEnabled: data.feature_enabled !== false,
      }
    }
    if (id === "musubi") {
      return fromMusubi(await musubiApi.status())
    }
    if (id === "anima-fast") {
      return fromAnima(await animaFastApi.status())
    }
    if (id === "ai-toolkit") {
      return fromAiToolkit(await aiToolkitApi.status())
    }
    return { id, state: "unknown", featureEnabled: false }
  },

  async list(): Promise<EngineStatus[]> {
    const ids: TrainingEngine[] = ["kohya", "anima-fast", "musubi", "ai-toolkit"]
    return Promise.all(ids.map((id) => this.status(id)))
  },

  async install(id: TrainingEngine): Promise<EngineActionResult> {
    const downloadSources = resolvedDownloadSourcesPayload()
    if (id === "anima-fast") return fromInstall(await animaFastApi.install(downloadSources))
    if (id === "musubi") return fromMusubiInstall(await musubiApi.install(downloadSources))
    if (id === "ai-toolkit") return fromAiToolkitInstall(await aiToolkitApi.install(downloadSources))
    throw new Error(`Install is not supported for engine: ${id}`)
  },

  async repair(id: TrainingEngine): Promise<EngineActionResult> {
    const downloadSources = resolvedDownloadSourcesPayload()
    if (id === "anima-fast") return fromInstall(await animaFastApi.repair(downloadSources))
    if (id === "musubi") return fromMusubiInstall(await musubiApi.repair(downloadSources))
    if (id === "ai-toolkit") return fromAiToolkitInstall(await aiToolkitApi.repair(downloadSources))
    throw new Error(`Repair is not supported for engine: ${id}`)
  },

  async uninstall(id: TrainingEngine): Promise<EngineStatus> {
    if (id === "anima-fast") {
      const data = await apiData<{ status?: AnimaFastStatus }>("/api/engines/anima-fast/uninstall", { method: "POST", body: "{}" })
      return data.status ? fromAnima(data.status) : { id: "anima-fast", state: "not_installed", featureEnabled: true }
    }
    if (id === "musubi") {
      const data = await musubiApi.uninstall()
      return data.status ? fromMusubi(data.status) : { id: "musubi", state: "not_installed", featureEnabled: true }
    }
    if (id === "ai-toolkit") {
      const data = await aiToolkitApi.uninstall()
      return data.status ? fromAiToolkit(data.status) : { id: "ai-toolkit", state: "not_installed", featureEnabled: true }
    }
    throw new Error(`Uninstall is not supported for engine: ${id}`)
  },
}
