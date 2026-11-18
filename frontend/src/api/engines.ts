import { kohakuMossApi, type KohakuMossStatus } from "./kohakuMoss"
import { mossApi, type MossStatus } from "./moss"
import { diffsynthApi, type DiffSynthStatus } from "./diffsynth"
import { kohyaApi, type KohyaStatus } from "./kohya"
import { animaFastApi, type AnimaFastState, type AnimaFastStatus, type InstallResult } from "./animaFast"
import { musubiApi, type MusubiInstallResult, type MusubiStatus } from "./musubi"
import { aiToolkitApi, type AiToolkitInstallResult, type AiToolkitStatus } from "./aiToolkit"
import { apiData } from "./client"
import type { EngineRuntimeState } from "../engines/catalog"
import type { TrainingEngine } from "../training/modules"

export type EngineFacts = NonNullable<AnimaFastStatus["facts"]> & {
  mode?: "standalone" | "main_env"
  main_env_python?: string
  update_available?: boolean
  drift?: { name: string; spec: string; installed?: string | null }[]
}

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
  facts?: EngineFacts
  diagnosis?: DiffSynthStatus["diagnosis"]
  raw?: AnimaFastStatus | MusubiStatus | AiToolkitStatus | DiffSynthStatus | MossStatus
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

function fromKohya(status: KohyaStatus): EngineStatus {
  return { id: "kohya", state: mapAnimaState(status.state), featureEnabled: status.feature_enabled !== false,
    message: status.message || status.reason, facts: status.facts,
    runtime: { python: status.runtime?.python, environmentPath: status.runtime?.environment_path } }
}

function fromMoss(status: MossStatus): EngineStatus {
  return {
    id: "moss",
    state: mapAnimaState(status.state),
    featureEnabled: status.feature_enabled,
    message: status.message || status.reason,
    facts: status.facts,
    runtime: {
      python: status.runtime?.python,
      environmentPath: status.runtime?.environment_path,
      externalRuntimeExists: status.runtime?.external_runtime_exists,
    },
    raw: status,
  }
}

function fromDiffSynth(status: DiffSynthStatus): EngineStatus {
  return {
    id: "diffsynth",
    state: mapAnimaState(status.state),
    featureEnabled: status.feature_enabled,
    message: status.message || status.reason,
    facts: status.facts,
    diagnosis: status.diagnosis,
    runtime: { python: status.runtime?.python, environmentPath: status.runtime?.environment_path },
    raw: status,
  }
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

function fromKohakuMoss(status: KohakuMossStatus): EngineStatus {
  return { id: "kohaku-moss", state: mapAnimaState(status.state), featureEnabled: status.feature_enabled !== false,
    message: status.message || status.reason, facts: status.facts,
    runtime: { python: status.runtime?.python, environmentPath: status.runtime?.environment_path } }
}

export const enginesApi = {
  async status(id: TrainingEngine): Promise<EngineStatus> {
    if (id === "kohaku-moss") return fromKohakuMoss(await kohakuMossApi.status())
    if (id === "moss") return fromMoss(await mossApi.status())
    if (id === "diffsynth") return fromDiffSynth(await diffsynthApi.status())
    if (id === "kohya") {
      return fromKohya(await kohyaApi.status())
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
    const ids: TrainingEngine[] = ["kohya", "anima-fast", "musubi", "ai-toolkit", "diffsynth", "moss", "kohaku-moss"]
    return Promise.all(ids.map((id) => this.status(id)))
  },

  async install(id: TrainingEngine): Promise<EngineActionResult> {
    if (id === "kohaku-moss") {
      const result = await kohakuMossApi.install()
      return { alreadyReady: result.already_ready, taskId: result.task_id, logStream: result.log_stream,
        progressStream: result.progress_stream, status: result.status ? fromKohakuMoss(result.status) : undefined }
    }
    // Download sources come from the server-persisted settings (#310); optional
    // body fields still win when a caller passes them explicitly.
    if (id === "moss") {
      const result = await mossApi.install()
      return { alreadyReady: result.already_ready, taskId: result.task_id, logStream: result.log_stream,
        progressStream: result.progress_stream, status: result.status ? fromMoss(result.status) : undefined }
    }
    if (id === "kohya") {
      const result = await kohyaApi.install()
      return { alreadyReady: result.already_ready, taskId: result.task_id, logStream: result.log_stream,
        progressStream: result.progress_stream, status: result.status ? fromKohya(result.status) : undefined }
    }
    if (id === "diffsynth") {
      const result = await diffsynthApi.install()
      return { alreadyReady: result.already_ready, taskId: result.task_id, logStream: result.log_stream,
        progressStream: result.progress_stream, status: result.status ? fromDiffSynth(result.status) : undefined }
    }
    if (id === "anima-fast") return fromInstall(await animaFastApi.install())
    if (id === "musubi") return fromMusubiInstall(await musubiApi.install())
    if (id === "ai-toolkit") return fromAiToolkitInstall(await aiToolkitApi.install())
    throw new Error(`Install is not supported for engine: ${id}`)
  },

  async repair(id: TrainingEngine): Promise<EngineActionResult> {
    if (id === "kohaku-moss") {
      const result = await kohakuMossApi.repair()
      return { alreadyReady: result.already_ready, taskId: result.task_id, logStream: result.log_stream,
        progressStream: result.progress_stream, status: result.status ? fromKohakuMoss(result.status) : undefined }
    }
    if (id === "moss") {
      const result = await mossApi.repair()
      return { alreadyReady: result.already_ready, taskId: result.task_id, logStream: result.log_stream,
        progressStream: result.progress_stream, status: result.status ? fromMoss(result.status) : undefined }
    }
    if (id === "kohya") {
      const result = await kohyaApi.repair()
      return { alreadyReady: result.already_ready, taskId: result.task_id, logStream: result.log_stream,
        progressStream: result.progress_stream, status: result.status ? fromKohya(result.status) : undefined }
    }
    if (id === "diffsynth") {
      // Surgical repair (#462): diagnose and fix the broken component only.
      const result = await diffsynthApi.repair()
      return { alreadyReady: result.already_ready, taskId: result.task_id, logStream: result.log_stream,
        progressStream: result.progress_stream, status: result.status ? fromDiffSynth(result.status) : undefined }
    }
    if (id === "anima-fast") return fromInstall(await animaFastApi.repair())
    if (id === "musubi") return fromMusubiInstall(await musubiApi.repair())
    if (id === "ai-toolkit") return fromAiToolkitInstall(await aiToolkitApi.repair())
    throw new Error(`Repair is not supported for engine: ${id}`)
  },

  async reinstall(id: TrainingEngine): Promise<EngineActionResult> {
    if (id === "diffsynth") {
      const result = await diffsynthApi.reinstall()
      return { alreadyReady: result.already_ready, taskId: result.task_id, logStream: result.log_stream,
        progressStream: result.progress_stream, status: result.status ? fromDiffSynth(result.status) : undefined }
    }
    // Other engines: reinstall currently aliases force-repair.
    return this.repair(id)
  },

  async upgrade(id: TrainingEngine): Promise<EngineActionResult> {
    if (id === "kohya") {
      const result = await kohyaApi.upgrade()
      return { alreadyReady: result.already_up_to_date, taskId: result.task_id, logStream: result.log_stream,
        progressStream: result.progress_stream, status: result.status ? fromKohya(result.status) : undefined }
    }
    throw new Error(`Upgrade is not supported for engine: ${id}`)
  },

  async uninstall(id: TrainingEngine): Promise<EngineStatus> {
    if (id === "kohaku-moss") {
      const result = await kohakuMossApi.uninstall()
      return result.status ? fromKohakuMoss(result.status) : { id, state: "not_installed", featureEnabled: true }
    }
    if (id === "moss") {
      const result = await mossApi.uninstall()
      return result.status ? fromMoss(result.status) : { id, state: "not_installed", featureEnabled: true }
    }
    if (id === "kohya") {
      const result = await kohyaApi.uninstall()
      return result.status ? fromKohya(result.status) : { id, state: "not_installed", featureEnabled: true }
    }
    if (id === "diffsynth") {
      const result = await diffsynthApi.uninstall()
      return result.status ? fromDiffSynth(result.status) : { id, state: "not_installed", featureEnabled: true }
    }
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
