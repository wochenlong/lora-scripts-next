import type { SessionCreateRequest } from "../../src/contracts.ts"
import type { PiRuntimeAdapter, PiSessionHandle, RuntimePrompt } from "../../src/pi/runtime-adapter.ts"
import type { RuntimeEvent } from "../../src/pi/terminal-reducer.ts"
import { ProviderRegistry } from "../../src/pi/provider-registry.ts"
import { SessionRegistry } from "../../src/pi/session-registry.ts"
import { createRequestHandler } from "../../src/server.ts"

export class FakeSessionHandle implements PiSessionHandle {
  readonly listeners = new Set<(event: RuntimeEvent) => void>()
  prompts: RuntimePrompt[] = []
  cancelled = false
  closed = false
  readonly filePath: string
  blockPrompts = false
  #releasePrompt: (() => void) | null = null

  constructor(filePath = "C:\\fake\\session.jsonl") { this.filePath = filePath }

  async prompt(input: RuntimePrompt): Promise<void> {
    this.prompts.push(input)
    this.emit({ type: "message_start", payload: { role: "assistant" } })
    if (this.blockPrompts && input.mode === "prompt") {
      await new Promise<void>((resolve) => { this.#releasePrompt = resolve })
    }
    this.emit({ type: "message_end", payload: { role: "assistant", stopReason: input.signal.aborted ? "aborted" : "stop" } })
  }

  release(): void {
    this.#releasePrompt?.()
    this.#releasePrompt = null
  }

  async cancel(): Promise<void> {
    this.cancelled = true
    this.release()
  }

  async close(): Promise<void> {
    this.closed = true
  }

  sessionFile(): string { return this.filePath }

  async history(): Promise<Record<string, unknown>> { return { entries: [], hasMore: false } }
  async thinking(): Promise<string> { return "" }

  async snapshot(): Promise<Record<string, never>> {
    return {}
  }

  subscribe(listener: (event: RuntimeEvent) => void): () => void {
    this.listeners.add(listener)
    return () => this.listeners.delete(listener)
  }

  emit(event: RuntimeEvent): void {
    for (const listener of this.listeners) listener(event)
  }
}

export class FakeRuntimeAdapter implements PiRuntimeAdapter {
  readonly ready = true
  readonly sessions = new Map<string, FakeSessionHandle>()

  async createSession(sessionId: string, _request: SessionCreateRequest): Promise<PiSessionHandle> {
    const handle = new FakeSessionHandle()
    this.sessions.set(sessionId, handle)
    return handle
  }

  async resumeSession(sessionId: string, _request: SessionCreateRequest, _sessionFile: string): Promise<PiSessionHandle> {
    const handle = this.sessions.get(sessionId)
    if (!handle) throw new Error("missing fake session")
    return handle
  }
}

export async function waitFor(predicate: () => boolean, timeoutMs = 1_000): Promise<void> {
  const deadline = Date.now() + timeoutMs
  while (!predicate()) {
    if (Date.now() >= deadline) throw new Error("Timed out waiting for condition")
    await new Promise((resolve) => setTimeout(resolve, 5))
  }
}

export const TEST_TOKEN = "sidecar-test-token-32-characters-ok"

export function makeTestServer(): {
  handler: (request: Request) => Promise<Response>
  runtime: FakeRuntimeAdapter
  providers: ProviderRegistry
  sessions: SessionRegistry
} {
  const runtime = new FakeRuntimeAdapter()
  const providers = new ProviderRegistry()
  const sessions = new SessionRegistry(runtime)
  const handler = createRequestHandler({
    token: TEST_TOKEN,
    instanceId: "test-instance",
    parentPid: 42,
    parentAlive: () => true,
    runtimeName: "bun",
    runtimeVersion: "1.4.0",
    providers,
    sessions,
    piRuntime: runtime,
    startedAt: "2026-08-21T00:00:00.000Z",
  })
  return { handler, runtime, providers, sessions }
}

export function sidecarRequest(
  path: string,
  init: RequestInit = {},
  options: { authorize?: boolean; json?: unknown } = {},
): Request {
  const headers = new Headers(init.headers)
  if (options.authorize !== false) headers.set("authorization", `Bearer ${TEST_TOKEN}`)
  let body = init.body
  if (options.json !== undefined) {
    headers.set("content-type", "application/json")
    body = JSON.stringify(options.json)
  }
  const requestInit: RequestInit = { ...init, headers }
  if (body !== undefined) requestInit.body = body
  return new Request(`http://127.0.0.1:39123${path}`, requestInit)
}
