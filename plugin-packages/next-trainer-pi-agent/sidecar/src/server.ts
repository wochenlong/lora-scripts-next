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
    start(controller) {
      const encoder = new TextEncoder()
      const enqueue = (type: string, data: unknown, id?: number): void => {
        const fields = [id === undefined ? "" : `id: ${id}`, `event: ${type}`, `data: ${JSON.stringify(data)}`]
          .filter(Boolean)
          .join("\n")
        controller.enqueue(encoder.encode(`${fields}\n\n`))
      }
      // Subscribe before publishing connected/snapshot so deltas cannot fall into a setup gap.
      unsubscribe = sessions.subscribe(sessionId, (event) => enqueue("agent", event, event.eventId))
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
    const requestId = request.headers.get("x-request-id") ?? randomUUID()
    try {
      requireLoopbackHost(request)
      requireBearer(request, deps.token)
      const url = new URL(request.url)
      const path = url.pathname.replace(/\/+$/, "") || "/"

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
          return jsonSuccess(requestId, deps.providers.save(profileId, await readJson<ProviderProfileInput>(request)))
        }
        if (request.method === "DELETE") {
          return jsonSuccess(requestId, { removed: deps.providers.remove(profileId) })
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
        return jsonSuccess(requestId, deps.sessions.submit(decodeURIComponent(promptMatch[1] ?? ""), body), 202)
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
          await deps.sessions.close(sessionId)
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
