import { randomUUID } from "node:crypto"
import {
  BUILD_NODE_VERSION,
  PI_VERSION,
  SIDECAR_PROTOCOL,
  SIDECAR_PROTOCOL_VERSION,
  SIDECAR_VERSION,
  type ApiFailure,
  type ApiSuccess,
  type PromptRequest,
  type ProviderProfileInput,
  type SessionCreateRequest,
} from "./contracts.ts"
import { requireBearer } from "./auth.ts"
import { SidecarError, toPublicError } from "./errors.ts"
import { ProviderRegistry } from "./pi/provider-registry.ts"
import type { PiRuntimeAdapter } from "./pi/runtime-adapter.ts"
import { SessionRegistry } from "./pi/session-registry.ts"

export interface ServerDependencies {
  token: string
  instanceId: string
  parentPid: number
  parentAlive: () => boolean
  runtimeName: string
  runtimeVersion: string
  providers: ProviderRegistry
  sessions: SessionRegistry
  piRuntime: PiRuntimeAdapter
  startedAt: string
}

interface BridgeRequest {
  requestId: string
  method: string
  params: Record<string, unknown>
}

const CANONICAL_UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
}

function requireString(params: Record<string, unknown>, key: string): string {
  const value = params[key]
  if (typeof value !== "string" || !value.trim()) {
    throw new SidecarError(400, "BRIDGE_PARAMS_INVALID", `${key} must be a non-empty string.`)
  }
  return value
}

function uiState(snapshot: import("./contracts.ts").SessionSnapshot, request?: SessionCreateRequest): Record<string, unknown> {
  return {
    id: snapshot.sessionId,
    ...(snapshot.name ?? request?.purpose ? { name: snapshot.name ?? request?.purpose } : {}),
    runId: snapshot.runId,
    status: snapshot.state === "error" ? "failed" : snapshot.state === "cancelling" ? "cancelling" : snapshot.state === "running" || snapshot.state === "queued" ? "running" : "idle",
    model: { profileId: snapshot.profileId, modelId: snapshot.modelId ?? request?.modelId ?? "" },
    thinkingLevel: request?.thinkingLevel ?? "auto",
    queue: { steering: [], followUp: [] },
  }
}

function uiSummary(snapshot: import("./contracts.ts").SessionSnapshot): Record<string, unknown> {
  return { id: snapshot.sessionId, name: snapshot.name ?? snapshot.purpose, createdAt: snapshot.createdAt ?? new Date(0).toISOString(), updatedAt: snapshot.updatedAt ?? snapshot.createdAt ?? new Date(0).toISOString(), messageCount: 0, running: snapshot.state === "running" || snapshot.state === "queued", model: { profileId: snapshot.profileId, modelId: snapshot.modelId ?? "" } }
}

function uiProvider(profile: import("./contracts.ts").ProviderStatus): Record<string, unknown> {
  return { id: profile.profileId, label: profile.providerId, endpoint: profile.endpoint, modelId: profile.modelId, configured: profile.configured, fingerprint: profile.fingerprint, capabilities: ["text"], thinkingLevels: ["auto", "off", "minimal", "low", "medium", "high", "xhigh", "max"] }
}

function uiEvent(event: import("./contracts.ts").AgentEventEnvelope): Record<string, unknown> {
  const base = { eventId: String(event.eventId), sessionId: event.sessionId, runId: event.runId }
  const payload = event.payload
  if (event.type === "message_start" || event.type === "message_end") return { ...base, type: event.type, message: payload.message ?? payload }
  if (event.type === "message_update") return { ...base, type: event.type, assistantMessageEvent: payload.assistantMessageEvent ?? payload }
  if (event.type.startsWith("tool_execution_")) return { ...base, type: event.type, ...payload }
  if (event.type === "queue_update") return { ...base, type: event.type, queue: payload.queue ?? { steering: [], followUp: [] } }
  if (event.type === "usage") return { ...base, type: event.type, usage: payload.usage ?? payload }
  if (event.type === "agent_settled" || event.type === "prompt_done") return { ...base, type: event.type, payload }
  if (event.type === "error") return { ...base, type: "startup_error", message: String(payload.message ?? "Agent run failed") }
  return { ...base, type: event.type }
}

function parseBridgeRequest(value: unknown): BridgeRequest {
  if (!isRecord(value) || Object.keys(value).some((key) => !["requestId", "method", "params"].includes(key))) {
    throw new SidecarError(400, "BRIDGE_REQUEST_INVALID", "Bridge request fields are invalid.")
  }
  if (typeof value.requestId !== "string" || !CANONICAL_UUID.test(value.requestId)) {
    throw new SidecarError(400, "BRIDGE_REQUEST_INVALID", "Bridge requestId must be a canonical UUID.")
  }
  if (typeof value.method !== "string" || !isRecord(value.params)) {
    throw new SidecarError(400, "BRIDGE_REQUEST_INVALID", "Bridge method and params are required.")
  }
  return value as unknown as BridgeRequest
}

async function dispatchBridgeRequest(request: BridgeRequest, deps: ServerDependencies): Promise<unknown> {
  const params = request.params
  switch (request.method) {
    case "session.list": return deps.sessions.list().map(uiSummary)
    case "session.create": {
      const model = isRecord(params.model) ? params.model : null
      const profileId = model ? requireString(model, "profileId") : (typeof params.profileId === "string" && params.profileId.trim() ? params.profileId : deps.providers.defaultProfileId())
      if (!profileId) throw new SidecarError(409, "PROVIDER_NOT_CONFIGURED", "No Provider profile is configured.")
      const purpose = typeof params.purpose === "string" && params.purpose.trim() ? params.purpose : "assistant"
      const thinkingLevel = typeof params.thinkingLevel === "string" ? params.thinkingLevel as SessionCreateRequest["thinkingLevel"] : undefined
      const modelId = model ? requireString(model, "modelId") : deps.providers.status(profileId).modelId
      const requestData = { profileId, modelId, purpose, ...(thinkingLevel ? { thinkingLevel } : {}) }
      const created = await deps.sessions.create(requestData)
      const name = typeof params.name === "string" && params.name.trim() ? params.name.trim() : undefined
      if (name) await deps.sessions.rename(created.sessionId, name)
      return uiState(deps.sessions.snapshot(created.sessionId), requestData)
    }
    case "session.rename":
      await deps.sessions.rename(requireString(params, "sessionId"), requireString(params, "name")); return null
    case "session.delete":
      await deps.sessions.delete(requireString(params, "sessionId")); return null
    case "session.getState": return uiState(deps.sessions.snapshot(requireString(params, "sessionId")))
    case "session.getHistory": {
      const options = {
        ...(typeof params.cursor === "string" ? { cursor: params.cursor } : {}),
        ...(Number.isSafeInteger(params.limit) ? { limit: Number(params.limit) } : {}),
        ...(typeof params.deferThinking === "boolean" ? { deferThinking: params.deferThinking } : {}),
        ...(typeof params.deferMedia === "boolean" ? { deferMedia: params.deferMedia } : {}),
      }
      const historySessionId = requireString(params, "sessionId")
      const rawHistory = await deps.sessions.history(historySessionId, options)
      return { session: uiState(deps.sessions.snapshot(historySessionId)), messages: Array.isArray(rawHistory.entries) ? rawHistory.entries.filter((entry) => isRecord(entry) && entry.type === "message").map((entry) => (entry as Record<string, unknown>).message) : [], hasMore: rawHistory.hasMore === true, ...(typeof rawHistory.cursor === "string" ? { cursor: rawHistory.cursor } : {}) }
    }
    case "session.getThinking":
      if (!Number.isSafeInteger(params.blockIndex) || Number(params.blockIndex) < 0) throw new SidecarError(400, "BRIDGE_PARAMS_INVALID", "blockIndex is invalid.")
       return deps.sessions.thinking(requireString(params, "sessionId"), requireString(params, "entryId"), Number(params.blockIndex))
    case "session.prompt": {
      const input = isRecord(params.input) ? params.input : params
      const text = requireString(input, "text")
      const clientSubmissionId = requireString(input, "clientSubmissionId")
      const streamingBehavior = input.streamingBehavior
      if (streamingBehavior !== undefined && streamingBehavior !== "steer" && streamingBehavior !== "followUp") {
        throw new SidecarError(400, "BRIDGE_PARAMS_INVALID", "streamingBehavior is invalid.")
      }
      const receipt = await deps.sessions.submit(requireString(params, "sessionId"), {
        requestId: clientSubmissionId,
        text,
        ...(streamingBehavior ? { mode: streamingBehavior } : {}),
      })
      return { accepted: true, sessionId: receipt.sessionId, runId: receipt.runId, clientSubmissionId, disposition: streamingBehavior ? "queued" : "started" }
    }
    case "session.cancel": {
      const sessionId = requireString(params, "sessionId")
      const runId = deps.sessions.snapshot(sessionId).activeRunId
      return runId ? deps.sessions.cancel(sessionId, runId) : { cancelled: false, runId: 0 }
    }
    case "session.compact": return deps.sessions.compact(requireString(params, "sessionId"), typeof params.instructions === "string" ? params.instructions : undefined)
    case "session.setModel": {
      if (!isRecord(params.model)) throw new SidecarError(400, "BRIDGE_PARAMS_INVALID", "model is invalid.")
      await deps.sessions.assertModel(requireString(params, "sessionId"), requireString(params.model, "profileId"), requireString(params.model, "modelId"))
      return null
    }
    case "session.setThinkingLevel":
      await deps.sessions.setThinkingLevel(requireString(params, "sessionId"), requireString(params, "level") as SessionCreateRequest["thinkingLevel"]); return null
    case "session.recallQueue": return deps.sessions.recallQueue(requireString(params, "sessionId"))
    case "provider.list": return deps.providers.list().map(uiProvider)
    case "provider.status": return uiProvider(deps.providers.status(requireString(params, "profileId")))
    case "provider.saveKey": return uiProvider(await deps.providers.save(requireString(params, "profileId"), {
      providerId: requireString(params, "profileId"),
      modelId: requireString(params, "modelId"),
      endpoint: requireString(params, "endpoint"),
      apiKey: requireString(params, "key"),
    }))
    case "provider.removeKey": {
      const profileId = requireString(params, "profileId")
      const previous = deps.providers.status(profileId)
      await deps.providers.remove(profileId)
      return uiProvider({ ...previous, configured: false, fingerprint: "" })
    }
    case "provider.test": {
      if (!deps.piRuntime.testProvider) throw new SidecarError(501, "PROVIDER_TEST_UNAVAILABLE", "Provider testing is not available.")
      return deps.piRuntime.testProvider(requireString(params, "profileId"))
    }
    default: throw new SidecarError(404, "BRIDGE_METHOD_NOT_FOUND", "Bridge method was not found.")
  }
}

function bridgeStreamResponse(request: BridgeRequest, deps: ServerDependencies): Response {
  if (request.method !== "session.subscribe") {
    throw new SidecarError(400, "BRIDGE_STREAM_INVALID", "Only session.subscribe is streamable.")
  }
  const sessionId = requireString(request.params, "sessionId")
  let unsubscribe = () => {}
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const encoder = new TextEncoder()
      const send = (data: unknown): void => {
        const mapped = isRecord(data) && typeof data.type === "string" && typeof data.eventId === "number" ? uiEvent(data as unknown as import("./contracts.ts").AgentEventEnvelope) : data
        controller.enqueue(encoder.encode(`data: ${JSON.stringify({ ok: true, requestId: request.requestId, data: mapped })}\n\n`))
      }
      unsubscribe = await deps.sessions.subscribe(sessionId, send)
      send({ type: "connected", state: uiState(deps.sessions.snapshot(sessionId)) })
    },
    cancel() { unsubscribe() },
  })
  return new Response(stream, { headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache, no-transform" } })
}

function jsonSuccess<T>(requestId: string, data: T, status = 200): Response {
  const body: ApiSuccess<T> = { ok: true, requestId, data }
  return Response.json(body, { status })
}

function jsonFailure(requestId: string, error: SidecarError): Response {
  const body: ApiFailure = {
    ok: false,
    requestId,
    error: { code: error.code, message: error.message, retryable: error.retryable },
  }
  return Response.json(body, { status: error.status })
}

async function readJson<T>(request: Request): Promise<T> {
  const contentType = request.headers.get("content-type")?.split(";", 1)[0]?.trim().toLowerCase()
  if (contentType !== "application/json") {
    throw new SidecarError(415, "JSON_REQUIRED", "Content-Type application/json is required.")
  }
  try {
    return (await request.json()) as T
  } catch {
    throw new SidecarError(400, "JSON_INVALID", "Request body is not valid JSON.")
  }
}

function requireLoopbackHost(request: Request): void {
  const url = new URL(request.url)
  if (url.hostname !== "127.0.0.1") {
    throw new SidecarError(403, "LOOPBACK_REQUIRED", "Sidecar requests must use the 127.0.0.1 loopback address.")
  }
}

function sseResponse(sessionId: string, sessions: SessionRegistry): Response {
  let unsubscribe = () => {}
  const stream = new ReadableStream<Uint8Array>({
    async start(controller) {
      const encoder = new TextEncoder()
      const enqueue = (type: string, data: unknown, id?: number): void => {
        const fields = [id === undefined ? "" : `id: ${id}`, `event: ${type}`, `data: ${JSON.stringify(data)}`]
          .filter(Boolean)
          .join("\n")
        controller.enqueue(encoder.encode(`${fields}\n\n`))
      }
      // Subscribe before publishing connected/snapshot so deltas cannot fall into a setup gap.
      unsubscribe = await sessions.subscribe(sessionId, (event) => enqueue("agent", event, event.eventId))
      enqueue("connected", { protocol: SIDECAR_PROTOCOL, sessionId })
      enqueue("snapshot", sessions.snapshot(sessionId))
    },
    cancel() {
      unsubscribe()
    },
  })

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  })
}

export function createRequestHandler(deps: ServerDependencies): (request: Request) => Promise<Response> {
  return async (request: Request): Promise<Response> => {
    let requestId = request.headers.get("x-request-id") ?? randomUUID()
    try {
      requireLoopbackHost(request)
      requireBearer(request, deps.token)
      const url = new URL(request.url)
      const path = url.pathname.replace(/\/+$/, "") || "/"

      if (request.method === "POST" && path === "/bridge/requests") {
        const bridgeRequest = parseBridgeRequest(await readJson<unknown>(request))
        requestId = bridgeRequest.requestId
        return jsonSuccess(bridgeRequest.requestId, await dispatchBridgeRequest(bridgeRequest, deps))
      }
      if (request.method === "POST" && path === "/bridge/streams") {
        const bridgeRequest = parseBridgeRequest(await readJson<unknown>(request))
        requestId = bridgeRequest.requestId
        return bridgeStreamResponse(bridgeRequest, deps)
      }

      if (request.method === "GET" && path === "/health") {
        return jsonSuccess(requestId, {
          status: "ok",
          service: "next-trainer-pi-sidecar",
          sidecarVersion: SIDECAR_VERSION,
          protocolVersion: SIDECAR_PROTOCOL_VERSION,
          piVersion: PI_VERSION,
          buildNode: BUILD_NODE_VERSION,
          runtime: { name: deps.runtimeName, version: deps.runtimeVersion },
          capabilities: ["session", "events", "custom-tools", "skills", "images", "scoped-workspaces"],
          instanceId: deps.instanceId,
          startedAt: deps.startedAt,
          parent: { pid: deps.parentPid, alive: deps.parentAlive() },
          providerConfigured: deps.providers.list().length > 0,
          providerReady: deps.providers.list().length > 0 && deps.piRuntime.ready,
          piRuntimeReady: deps.piRuntime.ready,
        })
      }

      if (request.method === "GET" && path === "/providers") {
        return jsonSuccess(requestId, deps.providers.list())
      }
      const providerMatch = /^\/providers\/([^/]+)$/.exec(path)
      if (providerMatch) {
        const profileId = decodeURIComponent(providerMatch[1] ?? "")
        if (request.method === "GET") return jsonSuccess(requestId, deps.providers.status(profileId))
        if (request.method === "PUT") {
          return jsonSuccess(requestId, await deps.providers.save(profileId, await readJson<ProviderProfileInput>(request)))
        }
        if (request.method === "DELETE") {
          return jsonSuccess(requestId, { removed: await deps.providers.remove(profileId) })
        }
      }

      if (request.method === "GET" && path === "/sessions") {
        return jsonSuccess(requestId, deps.sessions.list())
      }
      if (request.method === "POST" && path === "/sessions") {
        const body = await readJson<SessionCreateRequest>(request)
        if (!body.profileId || !body.purpose) {
          throw new SidecarError(400, "SESSION_REQUEST_INVALID", "profileId and purpose are required.")
        }
        if (!deps.providers.has(body.profileId)) {
          throw new SidecarError(409, "PROVIDER_NOT_CONFIGURED", "The selected Provider profile is not configured.")
        }
        return jsonSuccess(requestId, await deps.sessions.create(body), 201)
      }

      const eventsMatch = /^\/sessions\/([^/]+)\/events$/.exec(path)
      if (request.method === "GET" && eventsMatch) {
        return sseResponse(decodeURIComponent(eventsMatch[1] ?? ""), deps.sessions)
      }
      const promptMatch = /^\/sessions\/([^/]+)\/prompts$/.exec(path)
      if (request.method === "POST" && promptMatch) {
        const body = await readJson<PromptRequest>(request)
        if (!body.requestId || !body.text?.trim()) {
          throw new SidecarError(400, "PROMPT_REQUEST_INVALID", "requestId and non-empty text are required.")
        }
        return jsonSuccess(requestId, await deps.sessions.submit(decodeURIComponent(promptMatch[1] ?? ""), body), 202)
      }
      const cancelMatch = /^\/sessions\/([^/]+)\/cancel$/.exec(path)
      if (request.method === "POST" && cancelMatch) {
        const body = await readJson<{ runId: number }>(request)
        if (!Number.isInteger(body.runId) || body.runId <= 0) {
          throw new SidecarError(400, "CANCEL_REQUEST_INVALID", "A positive runId is required.")
        }
        return jsonSuccess(requestId, await deps.sessions.cancel(decodeURIComponent(cancelMatch[1] ?? ""), body.runId))
      }
      const sessionMatch = /^\/sessions\/([^/]+)$/.exec(path)
      if (sessionMatch) {
        const sessionId = decodeURIComponent(sessionMatch[1] ?? "")
        if (request.method === "GET") return jsonSuccess(requestId, deps.sessions.snapshot(sessionId))
        if (request.method === "DELETE") {
          await deps.sessions.delete(sessionId)
          return jsonSuccess(requestId, { closed: true })
        }
      }

      throw new SidecarError(404, "ROUTE_NOT_FOUND", "Sidecar route was not found.")
    } catch (error) {
      return jsonFailure(requestId, toPublicError(error))
    }
  }
}

interface BunServer {
  port: number
  stop(closeActiveConnections?: boolean): void
}

interface BunRuntime {
  version: string
  serve(options: {
    hostname: string
    port: number
    fetch(request: Request): Promise<Response>
  }): BunServer
}

export function startServer(bun: BunRuntime, port: number, handler: (request: Request) => Promise<Response>): BunServer {
  return bun.serve({ hostname: "127.0.0.1", port, fetch: handler })
}
