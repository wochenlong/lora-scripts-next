import { randomUUID } from "node:crypto"
import { existsSync, readFileSync, rmSync, writeFileSync, renameSync } from "node:fs"
import path from "node:path"
import {
  SIDECAR_PROTOCOL,
  type AgentEventEnvelope,
  type PromptRequest,
  type SessionCreateRequest,
  type SessionSnapshot,
  type StopReason,
} from "../contracts.ts"
import { SidecarError } from "../errors.ts"
import type { PiRuntimeAdapter, PiSessionHandle } from "./runtime-adapter.ts"
import { TerminalReducer, type RuntimeEvent } from "./terminal-reducer.ts"

type EventListener = (event: AgentEventEnvelope) => void

interface SessionRecord {
  request: SessionCreateRequest
  handle: PiSessionHandle
  state: SessionSnapshot["state"]
  allocatedRunId: number
  activeRunId: number | null
  lastStopReason: StopReason | null
  eventId: number
  listeners: Set<EventListener>
  unsubscribeRuntime: () => void
  queue: Promise<void>
  activeAbort: AbortController | null
  activeReducer: TerminalReducer | null
}

interface StoredSession {
  sessionId: string
  request: SessionCreateRequest
  sessionFile?: string
  name?: string
  deleted?: boolean
  createdAt: string
  updatedAt: string
}

export interface PromptAccepted {
  accepted: true
  promptId: string
  sessionId: string
  runId: number
}

export const DEFAULT_SESSION_IDLE_TIMEOUT_MS = 10 * 60 * 1000

export class SessionRegistry {
  readonly #sessions = new Map<string, SessionRecord>()
  readonly #runtime: PiRuntimeAdapter
  readonly #storageDir: string | null
  readonly #indexPath: string | null
  readonly #index = new Map<string, StoredSession>()
  readonly #idleTimeoutMs: number
  readonly #idleTimers = new Map<string, ReturnType<typeof setTimeout>>()

  constructor(runtime: PiRuntimeAdapter, options: { storageDir?: string; idleTimeoutMs?: number } = {}) {
    this.#runtime = runtime
    this.#idleTimeoutMs = options.idleTimeoutMs ?? DEFAULT_SESSION_IDLE_TIMEOUT_MS
    this.#storageDir = options.storageDir ? path.resolve(options.storageDir) : null
    this.#indexPath = this.#storageDir ? path.join(path.dirname(this.#storageDir), "session-index.json") : null
    if (this.#indexPath && existsSync(this.#indexPath)) {
      try {
        const parsed = JSON.parse(readFileSync(this.#indexPath, "utf8")) as unknown
        if (Array.isArray(parsed)) for (const item of parsed) {
          if (item && typeof item === "object" && typeof (item as StoredSession).sessionId === "string") this.#index.set((item as StoredSession).sessionId, item as StoredSession)
        }
      } catch { /* a corrupt index is rebuilt from newly opened sessions */ }
    }
  }

  async create(request: SessionCreateRequest): Promise<SessionSnapshot> {
    const sessionId = randomUUID()
    const handle = await this.#runtime.createSession(sessionId, request)
    const record: SessionRecord = {
      request: structuredClone(request),
      handle,
      state: "idle",
      allocatedRunId: 0,
      activeRunId: null,
      lastStopReason: null,
      eventId: 0,
      listeners: new Set(),
      unsubscribeRuntime: () => {},
      queue: Promise.resolve(),
      activeAbort: null,
      activeReducer: null,
    }
    record.unsubscribeRuntime = handle.subscribe((event) => this.#onRuntimeEvent(sessionId, record, event))
    this.#sessions.set(sessionId, record)
    this.#scheduleIdleRelease(sessionId)
    const sessionFile = handle.sessionFile?.()
    const now = new Date().toISOString()
    this.#index.set(sessionId, { sessionId, request: structuredClone(request), ...(sessionFile ? { sessionFile } : {}), createdAt: now, updatedAt: now })
    this.#persistIndex()
    return this.snapshot(sessionId)
  }

  list(): SessionSnapshot[] {
    return [...this.#index.values()].filter((item) => !item.deleted).map((item) => this.#sessions.has(item.sessionId)
      ? this.snapshot(item.sessionId)
      : { sessionId: item.sessionId, profileId: item.request.profileId, ...(item.request.modelId ? { modelId: item.request.modelId } : {}), ...(item.name ? { name: item.name } : {}), createdAt: item.createdAt, updatedAt: item.updatedAt, purpose: item.request.purpose, state: "idle", runId: 0, activeRunId: null, lastStopReason: null })
  }

  snapshot(sessionId: string): SessionSnapshot {
    const record = this.#sessions.get(sessionId)
    if (!record) {
      const stored = this.#index.get(sessionId)
      if (!stored || stored.deleted) throw new SidecarError(404, "SESSION_NOT_FOUND", "Session was not found.")
      return { sessionId, profileId: stored.request.profileId, ...(stored.request.modelId ? { modelId: stored.request.modelId } : {}), ...(stored.name ? { name: stored.name } : {}), createdAt: stored.createdAt, updatedAt: stored.updatedAt, purpose: stored.request.purpose, state: "idle", runId: 0, activeRunId: null, lastStopReason: null }
    }
    return {
      sessionId,
      profileId: record.request.profileId,
      ...(record.request.modelId ? { modelId: record.request.modelId } : {}),
      ...(this.#index.get(sessionId)?.createdAt ? { createdAt: this.#index.get(sessionId)!.createdAt, updatedAt: this.#index.get(sessionId)!.updatedAt } : {}),
      ...(this.#index.get(sessionId)?.name ? { name: this.#index.get(sessionId)!.name } : {}),
      purpose: record.request.purpose,
      state: record.state,
      runId: record.allocatedRunId,
      activeRunId: record.activeRunId,
      lastStopReason: record.lastStopReason,
    }
  }

  async rename(sessionId: string, name: string): Promise<void> {
    const record = await this.#ensureActive(sessionId)
    const handle = record.handle
    if (!handle.rename) throw new SidecarError(501, "SESSION_OPERATION_UNAVAILABLE", "Session rename is unavailable.")
    await handle.rename(name)
    const stored = this.#index.get(sessionId)
    if (stored) { stored.name = name; this.#persistIndex() }
    // The wrapper stays active; the idle timer owns the release so the
    // session remains subscribable and promptable right after a rename.
  }

  async history(sessionId: string, options: { cursor?: string; limit?: number; deferThinking?: boolean; deferMedia?: boolean } = {}): Promise<Record<string, unknown>> {
    const record = await this.#ensureActive(sessionId)
    const handle = record.handle
    if (!handle.history) throw new SidecarError(501, "SESSION_OPERATION_UNAVAILABLE", "Session history is unavailable.")
    try { return await handle.history(options) } finally { await this.#deactivate(sessionId) }
  }

  async thinking(sessionId: string, entryId: string, blockIndex: number): Promise<string> {
    const record = await this.#ensureActive(sessionId)
    if (!record.handle.thinking) throw new SidecarError(501, "SESSION_OPERATION_UNAVAILABLE", "Thinking content is unavailable.")
    try { return await record.handle.thinking(entryId, blockIndex) } finally { await this.#deactivate(sessionId) }
  }

  async compact(sessionId: string, instructions?: string): Promise<Record<string, unknown>> {
    const handle = this.#get(sessionId).handle
    if (!handle.compact) throw new SidecarError(501, "SESSION_OPERATION_UNAVAILABLE", "Session compaction is unavailable.")
    return handle.compact(instructions)
  }

  async setThinkingLevel(sessionId: string, level: SessionCreateRequest["thinkingLevel"]): Promise<void> {
    if (!level) throw new SidecarError(400, "THINKING_LEVEL_INVALID", "Thinking level is required.")
    const handle = this.#get(sessionId).handle
    if (!handle.setThinkingLevel) throw new SidecarError(501, "SESSION_OPERATION_UNAVAILABLE", "Thinking level changes are unavailable.")
    await handle.setThinkingLevel(level)
  }

  async recallQueue(sessionId: string): Promise<{ steering: string[]; followUp: string[] }> {
    const handle = this.#get(sessionId).handle
    if (!handle.recallQueue) throw new SidecarError(501, "SESSION_OPERATION_UNAVAILABLE", "Session queue recall is unavailable.")
    return handle.recallQueue()
  }

  async assertModel(sessionId: string, profileId: string, modelId: string): Promise<void> {
    const handle = this.#get(sessionId).handle
    if (!handle.assertModel) throw new SidecarError(501, "SESSION_OPERATION_UNAVAILABLE", "Session model validation is unavailable.")
    await handle.assertModel(profileId, modelId)
  }

  async submit(sessionId: string, request: PromptRequest): Promise<PromptAccepted> {
    // Resume a wrapper that was released by the idle policy from its JSONL.
    const record = await this.#ensureActive(sessionId)
    if (record.state === "closed") throw new SidecarError(409, "SESSION_CLOSED", "Session is closed.")

    const mode = request.mode ?? "prompt"
    if (mode !== "prompt") {
      if (record.activeRunId === null || !record.activeAbort || record.state === "cancelling") {
        throw new SidecarError(409, "SESSION_NOT_RUNNING", `${mode} requires an active Agent run.`)
      }
      const promptId = randomUUID()
      const runId = record.activeRunId
      this.#emit(sessionId, record, runId, "prompt_queued", { promptId, mode })
      void record.handle.prompt({
        text: request.text,
        mode,
        images: request.images ?? [],
        signal: record.activeAbort.signal,
      }).catch(() => {
        this.#emit(sessionId, record, runId, "error", {
          code: "PROMPT_QUEUE_FAILED",
          message: "The running Agent could not accept the queued input.",
        })
      })
      return { accepted: true, promptId, sessionId, runId }
    }

    const runId = ++record.allocatedRunId
    const promptId = randomUUID()
    const execute = async (): Promise<void> => {
      record.state = "running"
      record.activeRunId = runId
      record.activeAbort = new AbortController()
      const reducer = new TerminalReducer()
      record.activeReducer = reducer
      this.#emit(sessionId, record, runId, "prompt_started", { promptId, mode })
      try {
        await record.handle.prompt({
          text: request.text,
          mode,
          images: request.images ?? [],
          signal: record.activeAbort.signal,
        })
      } catch (error) {
        const aborted = record.activeAbort.signal.aborted
        reducer.observe({ type: "error", payload: { aborted } })
        this.#emit(sessionId, record, runId, "error", {
          code: aborted ? "PROMPT_ABORTED" : "PROMPT_FAILED",
          message: aborted ? "Prompt was cancelled." : "Prompt execution failed.",
        })
      } finally {
        const terminal = reducer.promptResolved()
        if (terminal) this.#emit(sessionId, record, runId, terminal.type, terminal.payload)
        record.lastStopReason = reducer.lastStopReason
        record.state = "idle"
        const settled = reducer.agentSettled()
        if (settled) this.#emit(sessionId, record, runId, settled.type, settled.payload)
        record.activeRunId = null
        record.activeAbort = null
        record.activeReducer = null
        this.#scheduleIdleRelease(sessionId)
      }
    }

    if (record.state !== "running") record.state = "queued"
    this.#clearIdleRelease(sessionId)
    record.queue = record.queue.then(execute, execute)
    return { accepted: true, promptId, sessionId, runId }
  }

  async cancel(sessionId: string, runId: number): Promise<{ cancelled: boolean; runId: number }> {
    const record = this.#sessions.get(sessionId)
    if (!record || record.activeRunId !== runId || !record.activeAbort) return { cancelled: false, runId }
    this.#clearIdleRelease(sessionId)
    record.state = "cancelling"
    record.activeAbort.abort()
    await record.handle.cancel()
    return { cancelled: true, runId }
  }

  async subscribe(sessionId: string, listener: EventListener): Promise<() => void> {
    const record = await this.#ensureActive(sessionId)
    record.listeners.add(listener)
    this.#scheduleIdleRelease(sessionId)
    return () => record.listeners.delete(listener)
  }

  async close(sessionId: string): Promise<void> {
    const record = this.#get(sessionId)
    this.#clearIdleRelease(sessionId)
    record.activeAbort?.abort()
    record.unsubscribeRuntime()
    await record.handle.close()
    record.state = "closed"
    record.listeners.clear()
    this.#sessions.delete(sessionId)
  }

  async delete(sessionId: string): Promise<void> {
    const stored = this.#index.get(sessionId)
    if (!stored || stored.deleted) throw new SidecarError(404, "SESSION_NOT_FOUND", "Session was not found.")
    if (this.#sessions.has(sessionId)) await this.close(sessionId)
    if (stored.sessionFile) await import("node:fs/promises").then((fs) => fs.rm(stored.sessionFile!, { force: true }))
    stored.deleted = true
    this.#persistIndex()
    this.#index.delete(sessionId)
    this.#persistIndex()
  }

  async closeAll(): Promise<void> {
    await Promise.all([...this.#sessions.keys()].map((sessionId) => this.close(sessionId)))
  }

  #onRuntimeEvent(sessionId: string, record: SessionRecord, event: RuntimeEvent): void {
    const runId = record.activeRunId ?? record.allocatedRunId
    record.activeReducer?.observe(event)
    if (event.type === "agent_settled" && record.activeReducer) return
    this.#emit(sessionId, record, runId, event.type, event.payload ?? {})
  }

  #emit(
    sessionId: string,
    record: SessionRecord,
    runId: number,
    type: string,
    payload: Record<string, unknown>,
  ): void {
    const envelope: AgentEventEnvelope = {
      protocol: SIDECAR_PROTOCOL,
      eventId: ++record.eventId,
      sessionId,
      runId,
      type,
      timestamp: new Date().toISOString(),
      payload,
    }
    for (const listener of record.listeners) listener(envelope)
  }

  #get(sessionId: string): SessionRecord {
    const record = this.#sessions.get(sessionId)
    if (!record) throw new SidecarError(404, "SESSION_NOT_FOUND", "Session was not found.")
    return record
  }

  /**
   * Release the in-process wrapper after the configured idle period.  The
   * JSONL session file and index entry are preserved; the next prompt or
   * history access resumes the wrapper from the persisted file.
   */
  #scheduleIdleRelease(sessionId: string): void {
    this.#clearIdleRelease(sessionId)
    if (this.#idleTimeoutMs <= 0) return
    const timer = setTimeout(() => {
      this.#idleTimers.delete(sessionId)
      const record = this.#sessions.get(sessionId)
      if (!record || record.state !== "idle" || record.activeRunId !== null) return
      void this.#deactivate(sessionId)
    }, this.#idleTimeoutMs)
    const unref = (timer as unknown as { unref?: () => void }).unref
    if (typeof unref === "function") unref.call(timer)
    this.#idleTimers.set(sessionId, timer)
  }

  #clearIdleRelease(sessionId: string): void {
    const timer = this.#idleTimers.get(sessionId)
    if (timer) {
      clearTimeout(timer)
      this.#idleTimers.delete(sessionId)
    }
  }

  async #ensureActive(sessionId: string): Promise<SessionRecord> {
    const active = this.#sessions.get(sessionId)
    if (active) return active
    const stored = this.#index.get(sessionId)
    if (!stored || stored.deleted || !stored.sessionFile || !this.#runtime.resumeSession) throw new SidecarError(404, "SESSION_NOT_FOUND", "Session was not found.")
    const handle = await this.#runtime.resumeSession(sessionId, stored.request, stored.sessionFile)
    const record: SessionRecord = { request: structuredClone(stored.request), handle, state: "idle", allocatedRunId: 0, activeRunId: null, lastStopReason: null, eventId: 0, listeners: new Set(), unsubscribeRuntime: () => {}, queue: Promise.resolve(), activeAbort: null, activeReducer: null }
    record.unsubscribeRuntime = handle.subscribe((event) => this.#onRuntimeEvent(sessionId, record, event))
    this.#sessions.set(sessionId, record)
    return record
  }

  async #deactivate(sessionId: string): Promise<void> {
    const record = this.#sessions.get(sessionId)
    if (!record) return
    this.#clearIdleRelease(sessionId)
    record.unsubscribeRuntime()
    await record.handle.close()
    this.#sessions.delete(sessionId)
  }

  #persistIndex(): void {
    if (!this.#indexPath) return
    const temporary = `${this.#indexPath}.${randomUUID()}.tmp`
    writeFileSync(temporary, `${JSON.stringify([...this.#index.values()])}\n`, { encoding: "utf8", mode: 0o600 })
    renameSync(temporary, this.#indexPath)
  }
}
