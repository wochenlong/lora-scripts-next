import { randomUUID } from "node:crypto"
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

export interface PromptAccepted {
  accepted: true
  promptId: string
  sessionId: string
  runId: number
}

export class SessionRegistry {
  readonly #sessions = new Map<string, SessionRecord>()
  readonly #runtime: PiRuntimeAdapter

  constructor(runtime: PiRuntimeAdapter) {
    this.#runtime = runtime
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
    return this.snapshot(sessionId)
  }

  list(): SessionSnapshot[] {
    return [...this.#sessions.keys()].map((id) => this.snapshot(id))
  }

  snapshot(sessionId: string): SessionSnapshot {
    const record = this.#get(sessionId)
    return {
      sessionId,
      profileId: record.request.profileId,
      purpose: record.request.purpose,
      state: record.state,
      runId: record.allocatedRunId,
      activeRunId: record.activeRunId,
      lastStopReason: record.lastStopReason,
    }
  }

  submit(sessionId: string, request: PromptRequest): PromptAccepted {
    const record = this.#get(sessionId)
    if (record.state === "closed") throw new SidecarError(409, "SESSION_CLOSED", "Session is closed.")

    const mode = request.mode ?? "prompt"
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
      }
    }

    if (record.state !== "running") record.state = "queued"
    record.queue = record.queue.then(execute, execute)
    return { accepted: true, promptId, sessionId, runId }
  }

  async cancel(sessionId: string, runId: number): Promise<{ cancelled: boolean; runId: number }> {
    const record = this.#get(sessionId)
    if (record.activeRunId !== runId || !record.activeAbort) return { cancelled: false, runId }
    record.state = "cancelling"
    record.activeAbort.abort()
    await record.handle.cancel()
    return { cancelled: true, runId }
  }

  subscribe(sessionId: string, listener: EventListener): () => void {
    const record = this.#get(sessionId)
    record.listeners.add(listener)
    return () => record.listeners.delete(listener)
  }

  async close(sessionId: string): Promise<void> {
    const record = this.#get(sessionId)
    record.activeAbort?.abort()
    record.unsubscribeRuntime()
    await record.handle.close()
    record.state = "closed"
    record.listeners.clear()
    this.#sessions.delete(sessionId)
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
}
