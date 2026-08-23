import { mkdir } from "node:fs/promises"
import path from "node:path"
import {
  createAgentSession,
  DefaultResourceLoader,
  ModelRuntime,
  SessionManager,
  SettingsManager,
  type AgentSession,
  type AgentSessionEvent,
  type ToolDefinition,
} from "@earendil-works/pi-coding-agent"
import type { PromptMode, SessionCreateRequest, SessionSnapshot, ThinkingLevel } from "../contracts.ts"
import { SidecarError } from "../errors.ts"
import { decodeInlineImage } from "../image-resources.ts"
import type { ProviderRegistry } from "./provider-registry.ts"
import type { RuntimeEvent } from "./terminal-reducer.ts"

export interface RuntimeImage {
  type: "image"
  data: string
  mimeType: string
}

export interface RuntimeImageRef {
  resourceId?: string
  mediaType?: string
  data?: string
  mimeType?: string
  name?: string
}

export interface RuntimePrompt {
  text: string
  mode: PromptMode
  images: RuntimeImageRef[]
  signal: AbortSignal
}

export interface PiSessionHandle {
  prompt(input: RuntimePrompt): Promise<void>
  cancel(): Promise<void>
  close(): Promise<void>
  snapshot(): Promise<Partial<SessionSnapshot>>
  subscribe(listener: (event: RuntimeEvent) => void): () => void
  activeToolNames?(): string[]
  rename?(name: string): Promise<void>
  history?(options?: { cursor?: string; limit?: number; deferThinking?: boolean; deferMedia?: boolean }): Promise<Record<string, unknown>>
  thinking?(entryId: string, blockIndex: number): Promise<string>
  compact?(instructions?: string): Promise<Record<string, unknown>>
  setThinkingLevel?(level: ThinkingLevel): Promise<void>
  recallQueue?(): Promise<{ steering: string[]; followUp: string[] }>
  assertModel?(profileId: string, modelId: string): Promise<void>
  sessionFile?(): string | undefined
}

export interface PiRuntimeAdapter {
  readonly ready: boolean
  createSession(sessionId: string, request: SessionCreateRequest): Promise<PiSessionHandle>
  resumeSession?(sessionId: string, request: SessionCreateRequest, sessionFile: string): Promise<PiSessionHandle>
  testProvider?(profileId: string): Promise<Record<string, unknown>>
}

export interface ProductionPiRuntimeAdapterOptions {
  agentDir: string
  providers: ProviderRegistry
  customTools?: ToolDefinition[]
  customToolsFactory?: (sessionId: string) => Promise<ToolDefinition[]>
  skillPaths?: string[]
  resolveImage?: (resourceId: string, mediaType: string, signal: AbortSignal) => Promise<RuntimeImage>
  providerTestTimeoutMs?: number
}

const BUILTIN_TOOL_NAMES = new Set(["read", "bash", "edit", "write", "grep", "find", "ls"])

function toPlainRecord(event: AgentSessionEvent): Record<string, unknown> {
  const { type: _type, ...payload } = event
  if (event.type === "message_start" || event.type === "message_update" || event.type === "message_end") {
    const message = event.message
    return {
      ...payload,
      role: message.role,
      ...(message.role === "assistant" ? { stopReason: message.stopReason } : {}),
    }
  }
  return payload
}

function lastAssistantStopReason(session: AgentSession): SessionSnapshot["lastStopReason"] {
  const messages = session.state.messages
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index]
    if (message?.role !== "assistant") continue
    const reason = message.stopReason
    if (reason === "stop" || reason === "length" || reason === "toolUse" || reason === "error" || reason === "aborted") {
      return reason
    }
    return "unknown"
  }
  return null
}

function responseStatus(error: unknown): number | undefined {
  if (!error || typeof error !== "object") return undefined
  const value = error as { status?: unknown; statusCode?: unknown; response?: { status?: unknown }; cause?: unknown }
  for (const candidate of [value.status, value.statusCode, value.response?.status]) {
    if (typeof candidate === "number" && Number.isInteger(candidate) && candidate >= 100 && candidate <= 599) return candidate
  }
  return responseStatus(value.cause)
}

class ProductionPiSessionHandle implements PiSessionHandle {
  readonly #session: AgentSession
  readonly #unsubscribe: () => void
  readonly #listeners = new Set<(event: RuntimeEvent) => void>()
  readonly #resolveImage?: ProductionPiRuntimeAdapterOptions["resolveImage"]
  readonly #profileId: string

  constructor(session: AgentSession, profileId: string, resolveImage?: ProductionPiRuntimeAdapterOptions["resolveImage"]) {
    this.#session = session
    this.#profileId = profileId
    this.#resolveImage = resolveImage
    this.#unsubscribe = session.subscribe((event) => {
      const runtimeEvent: RuntimeEvent = { type: event.type, payload: toPlainRecord(event) }
      for (const listener of this.#listeners) listener(runtimeEvent)
    })
  }

  async prompt(input: RuntimePrompt): Promise<void> {
    if (input.signal.aborted) throw new SidecarError(409, "PROMPT_ABORTED", "Prompt was cancelled.")
    const images = await this.#resolveImages(input)
    const abort = (): void => { void this.#session.abort() }
    input.signal.addEventListener("abort", abort, { once: true })
    try {
      if (input.mode === "steer") {
        await this.#session.steer(input.text, images)
      } else if (input.mode === "followUp") {
        await this.#session.followUp(input.text, images)
      } else {
        await this.#session.prompt(input.text, { images })
      }
    } finally {
      input.signal.removeEventListener("abort", abort)
    }
  }

  async cancel(): Promise<void> {
    await this.#session.abort()
  }

  async close(): Promise<void> {
    if (!this.#session.isIdle) await this.#session.abort()
    this.#unsubscribe()
    this.#session.dispose()
  }

  async snapshot(): Promise<Partial<SessionSnapshot>> {
    return { lastStopReason: lastAssistantStopReason(this.#session) }
  }

  subscribe(listener: (event: RuntimeEvent) => void): () => void {
    this.#listeners.add(listener)
    return () => this.#listeners.delete(listener)
  }

  activeToolNames(): string[] {
    return [...this.#session.getActiveToolNames()].sort()
  }

  async rename(name: string): Promise<void> {
    this.#session.setSessionName(name)
  }

  async history(options: { cursor?: string; limit?: number; deferThinking?: boolean; deferMedia?: boolean } = {}): Promise<Record<string, unknown>> {
    const entries = this.#session.sessionManager.getEntries()
    const end = options.cursor === undefined ? entries.length : Number(options.cursor)
    if (!Number.isSafeInteger(end) || end < 0 || end > entries.length) {
      throw new SidecarError(400, "HISTORY_CURSOR_INVALID", "Session history cursor is invalid.")
    }
    const limit = Math.max(1, Math.min(options.limit ?? 200, 1_000))
    const start = Math.max(0, end - limit)
    const selected = structuredClone(entries.slice(start, end)) as unknown as Array<Record<string, unknown>>
    const deferredThinking: Record<string, string> = {}
    if (options.deferThinking) {
      for (const entry of selected) {
        if (entry.type !== "message" || typeof entry.id !== "string") continue
        const message = entry.message as { content?: unknown } | undefined
        if (!Array.isArray(message?.content)) continue
        message.content = message.content.map((block, blockIndex) => {
          if (!block || typeof block !== "object" || (block as { type?: unknown }).type !== "thinking") return block
          const content = (block as { thinking?: unknown }).thinking
          if (typeof content === "string") deferredThinking[`${entry.id}:${blockIndex}`] = content
          return { type: "thinking", deferred: true }
        })
      }
    }
    return {
      entries: selected,
      hasMore: start > 0,
      ...(start > 0 ? { cursor: String(start) } : {}),
      deferredThinking,
    }
  }

  async thinking(entryId: string, blockIndex: number): Promise<string> {
    const entry = this.#session.sessionManager.getEntry(entryId)
    if (!entry || entry.type !== "message" || !("content" in entry.message) || !Array.isArray(entry.message.content)) {
      throw new SidecarError(404, "THINKING_NOT_FOUND", "Thinking content was not found.")
    }
    const block = entry.message.content[blockIndex]
    if (!block || block.type !== "thinking") {
      throw new SidecarError(404, "THINKING_NOT_FOUND", "Thinking content was not found.")
    }
    return block.thinking
  }

  async compact(instructions?: string): Promise<Record<string, unknown>> {
    const result = await this.#session.compact(instructions)
    return structuredClone(result) as unknown as Record<string, unknown>
  }

  async setThinkingLevel(level: ThinkingLevel): Promise<void> {
    if (level === "auto") {
      throw new SidecarError(409, "THINKING_LEVEL_IMMUTABLE", "Auto thinking is resolved when the session is created.")
    }
    this.#session.setThinkingLevel(level)
  }

  async recallQueue(): Promise<{ steering: string[]; followUp: string[] }> {
    return this.#session.clearQueue()
  }

  async assertModel(profileId: string, modelId: string): Promise<void> {
    if (profileId !== this.#profileId || modelId !== this.#session.model?.id) {
      throw new SidecarError(409, "SESSION_MODEL_IMMUTABLE", "A session cannot switch its active Provider model.")
    }
  }

  sessionFile(): string | undefined {
    return this.#session.sessionManager.getSessionFile()
  }

  async #resolveImages(input: RuntimePrompt): Promise<RuntimeImage[]> {
    if (input.images.length === 0) return []
    if (!this.#session.model?.input.includes("image")) {
      throw new SidecarError(409, "MODEL_CAPABILITY_UNAVAILABLE", "The active model does not support image input.")
    }
    return Promise.all(input.images.map(async (image) => {
      if (typeof image.data === "string" && typeof image.mimeType === "string") {
        const bytes = decodeInlineImage(image.data, image.mimeType)
        return { type: "image" as const, data: Buffer.from(bytes).toString("base64"), mimeType: image.mimeType }
      }
      if (typeof image.resourceId === "string" && typeof image.mediaType === "string") {
        if (!this.#resolveImage) {
          throw new SidecarError(409, "IMAGE_RESOURCE_UNAVAILABLE", "The selected image resource is unavailable to the sidecar.")
        }
        return this.#resolveImage(image.resourceId, image.mediaType, input.signal)
      }
      throw new SidecarError(409, "IMAGE_RESOURCE_UNAVAILABLE", "The selected image resource is unavailable to the sidecar.")
    }))
  }
}

export class ProductionPiRuntimeAdapter implements PiRuntimeAdapter {
  readonly ready = true
  readonly #agentDir: string
  readonly #providers: ProviderRegistry
  readonly #customTools: ToolDefinition[]
  readonly #customToolsFactory?: ProductionPiRuntimeAdapterOptions["customToolsFactory"]
  readonly #skillPaths: string[]
  readonly #resolveImage?: ProductionPiRuntimeAdapterOptions["resolveImage"]
  readonly #providerTestTimeoutMs: number

  constructor(options: ProductionPiRuntimeAdapterOptions) {
    this.#agentDir = path.resolve(options.agentDir)
    this.#providers = options.providers
    this.#customTools = [...(options.customTools ?? [])]
    this.#customToolsFactory = options.customToolsFactory
    this.#skillPaths = [...(options.skillPaths ?? [])]
    this.#resolveImage = options.resolveImage
    this.#providerTestTimeoutMs = Number.isFinite(options.providerTestTimeoutMs) && (options.providerTestTimeoutMs ?? 0) > 0
      ? Math.floor(options.providerTestTimeoutMs!)
      : 20_000
    for (const tool of this.#customTools) {
      if (BUILTIN_TOOL_NAMES.has(tool.name)) {
        throw new SidecarError(500, "PI_TOOL_POLICY_INVALID", `Host custom Tool name is reserved: ${tool.name}.`)
      }
    }
  }

  async testProvider(profileId: string): Promise<Record<string, unknown>> {
    const authPath = this.#providers.authPath
    const modelsPath = this.#providers.modelsPath
    if (!authPath || !modelsPath) throw new SidecarError(503, "PI_RUNTIME_NOT_READY", "Persistent Provider storage is required.")
    const binding = this.#providers.binding(profileId)
    const runtime = await ModelRuntime.create({ authPath, modelsPath, allowModelNetwork: false, refreshOnCreate: false })
    const model = runtime.getModel(binding.runtimeProviderId, binding.modelId)
    if (!model) throw new SidecarError(409, "PROVIDER_MODEL_UNAVAILABLE", "The selected Provider model is not available.")
    const controller = new AbortController()
    const timeout = setTimeout(() => controller.abort(), this.#providerTestTimeoutMs)
    const startedAt = performance.now()
    let status: number | undefined
    try {
      const message = await runtime.completeSimple(model, {
        messages: [{ role: "user", content: "Reply with OK.", timestamp: Date.now() }],
      }, {
        signal: controller.signal,
        maxTokens: 16,
        maxRetries: 0,
        cacheRetention: "none",
        onResponse: (response) => { status = response.status },
      })
      const responseText = message.content
        .filter((block) => block.type === "text")
        .map((block) => block.text)
        .join("")
        .slice(0, 256)
      const ok = message.stopReason !== "error" && message.stopReason !== "aborted"
      await this.#providers.recordTest(profileId, ok)
      return {
        ok,
        ...(status !== undefined ? { status } : {}),
        latencyMs: Math.round(performance.now() - startedAt),
        responseText,
        stopReason: message.stopReason,
      }
    } catch (error) {
      // Keep the public response bounded; status extraction is best-effort
      // because Pi may wrap transport failures in an Error.cause chain.
      status ??= responseStatus(error)
      await this.#providers.recordTest(profileId, false)
      return {
        ok: false,
        ...(status !== undefined ? { status } : {}),
        latencyMs: Math.round(performance.now() - startedAt),
        error: controller.signal.aborted ? "Provider test timed out." : "Provider test failed.",
      }
    } finally {
      clearTimeout(timeout)
    }
  }

  async createSession(sessionId: string, request: SessionCreateRequest): Promise<PiSessionHandle> {
    const authPath = this.#providers.authPath
    const modelsPath = this.#providers.modelsPath
    if (!authPath || !modelsPath) {
      throw new SidecarError(503, "PI_RUNTIME_NOT_READY", "Persistent Provider storage is required.", true)
    }

    const binding = this.#providers.binding(request.profileId)
    const customTools = [
      ...this.#customTools,
      ...(this.#customToolsFactory ? await this.#customToolsFactory(sessionId) : []),
    ]
    for (const tool of customTools) {
      if (BUILTIN_TOOL_NAMES.has(tool.name)) {
        throw new SidecarError(500, "PI_TOOL_POLICY_INVALID", `Host custom Tool name is reserved: ${tool.name}.`)
      }
    }
    const cwd = path.join(this.#agentDir, "runtime-cwd")
    const sessionDir = path.join(this.#agentDir, "sessions")
    await Promise.all([
      mkdir(cwd, { recursive: true }),
      mkdir(sessionDir, { recursive: true }),
    ])

    const modelRuntime = await ModelRuntime.create({
      authPath,
      modelsPath,
      allowModelNetwork: false,
      refreshOnCreate: false,
    })
    const model = modelRuntime.getModel(binding.runtimeProviderId, binding.modelId)
    if (!model) {
      throw new SidecarError(409, "PROVIDER_MODEL_UNAVAILABLE", "The selected Provider model is not available.")
    }
    if (!await modelRuntime.getAuth(binding.runtimeProviderId)) {
      throw new SidecarError(409, "PROVIDER_NOT_CONFIGURED", "The selected Provider credential is unavailable.")
    }

    const settingsManager = SettingsManager.inMemory()
    const resourceLoader = new DefaultResourceLoader({
      cwd,
      agentDir: this.#agentDir,
      settingsManager,
      noExtensions: true,
      noContextFiles: true,
      noPromptTemplates: true,
      noThemes: true,
      noSkills: this.#skillPaths.length === 0,
      additionalSkillPaths: this.#skillPaths,
    })
    await resourceLoader.reload()
    const sessionManager = SessionManager.create(cwd, sessionDir, { id: sessionId })
    const thinkingLevel = request.thinkingLevel && request.thinkingLevel !== "auto"
      ? request.thinkingLevel as Exclude<ThinkingLevel, "auto">
      : undefined
    const result = await createAgentSession({
      cwd,
      agentDir: this.#agentDir,
      modelRuntime,
      model,
      ...(thinkingLevel ? { thinkingLevel } : {}),
      noTools: "builtin",
      customTools,
      resourceLoader,
      sessionManager,
      settingsManager,
    })

    const activeTools = result.session.getActiveToolNames()
    const forbidden = activeTools.filter((name) => BUILTIN_TOOL_NAMES.has(name))
    if (forbidden.length > 0) {
      result.session.dispose()
      throw new SidecarError(500, "PI_TOOL_POLICY_VIOLATION", "Pi activated a forbidden built-in Tool.")
    }
    const allowed = new Set(customTools.map((tool) => tool.name))
    if (activeTools.some((name) => !allowed.has(name))) {
      result.session.dispose()
      throw new SidecarError(500, "PI_TOOL_POLICY_VIOLATION", "Pi activated a Tool outside the Host custom Tool allowlist.")
    }
    return new ProductionPiSessionHandle(result.session, request.profileId, this.#resolveImage)
  }

  async resumeSession(sessionId: string, request: SessionCreateRequest, sessionFile: string): Promise<PiSessionHandle> {
    const authPath = this.#providers.authPath
    const modelsPath = this.#providers.modelsPath
    if (!authPath || !modelsPath) throw new SidecarError(503, "PI_RUNTIME_NOT_READY", "Persistent Provider storage is required.", true)
    const binding = this.#providers.binding(request.profileId)
    const customTools = [
      ...this.#customTools,
      ...(this.#customToolsFactory ? await this.#customToolsFactory(sessionId) : []),
    ]
    const cwd = path.join(this.#agentDir, "runtime-cwd")
    const sessionDir = path.join(this.#agentDir, "sessions")
    const modelRuntime = await ModelRuntime.create({ authPath, modelsPath, allowModelNetwork: false, refreshOnCreate: false })
    const model = modelRuntime.getModel(binding.runtimeProviderId, binding.modelId)
    if (!model) throw new SidecarError(409, "PROVIDER_MODEL_UNAVAILABLE", "The selected Provider model is not available.")
    const settingsManager = SettingsManager.inMemory()
    const resourceLoader = new DefaultResourceLoader({ cwd, agentDir: this.#agentDir, settingsManager, noExtensions: true, noContextFiles: true, noPromptTemplates: true, noThemes: true, noSkills: this.#skillPaths.length === 0, additionalSkillPaths: this.#skillPaths })
    await resourceLoader.reload()
    const sessionManager = SessionManager.open(sessionFile, sessionDir, cwd)
    const thinkingLevel = request.thinkingLevel && request.thinkingLevel !== "auto" ? request.thinkingLevel as Exclude<ThinkingLevel, "auto"> : undefined
    const result = await createAgentSession({ cwd, agentDir: this.#agentDir, modelRuntime, model, ...(thinkingLevel ? { thinkingLevel } : {}), noTools: "builtin", customTools, resourceLoader, sessionManager, settingsManager })
    const activeTools = result.session.getActiveToolNames()
    const forbidden = activeTools.filter((name) => BUILTIN_TOOL_NAMES.has(name))
    const allowed = new Set(customTools.map((tool) => tool.name))
    if (forbidden.length > 0 || activeTools.some((name) => !allowed.has(name))) {
      result.session.dispose()
      throw new SidecarError(500, "PI_TOOL_POLICY_VIOLATION", "Pi activated a Tool outside the Host custom Tool allowlist.")
    }
    return new ProductionPiSessionHandle(result.session, request.profileId, this.#resolveImage)
  }
}

export class UnavailablePiRuntimeAdapter implements PiRuntimeAdapter {
  readonly ready = false

  async createSession(_sessionId: string, _request: SessionCreateRequest): Promise<PiSessionHandle> {
    throw new SidecarError(503, "PI_RUNTIME_NOT_READY", "The production Pi runtime adapter has not been initialized.", true)
  }
}
