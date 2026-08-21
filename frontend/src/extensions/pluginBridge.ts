import {
  PLUGIN_BRIDGE_PROTOCOL,
  isBridgeHelloMessage,
  isBridgeReadyMessage,
  parseBridgeRequestEnvelope,
  type BridgeCapability,
  type BridgeErrorBody,
  type BridgeRequestEnvelope,
  type BridgeResponseEnvelope,
  type BridgeWelcomeMessage,
} from "./pluginBridgeSchemas"

export interface BridgeMessagePort {
  onmessage: ((event: MessageEvent<unknown>) => void) | null
  postMessage(message: unknown): void
  start(): void
  close(): void
}

export interface BridgeMessageChannel {
  port1: BridgeMessagePort
  port2: BridgeMessagePort
}

export interface BridgeFrameTarget {
  postMessage(message: unknown, targetOrigin: string, transfer?: Transferable[]): void
}

export type BridgeRequestHandler = (request: BridgeRequestEnvelope) => unknown | Promise<unknown>

export interface HostPluginBridgeOptions {
  pluginId: string
  instanceId: string
  frameTarget: BridgeFrameTarget
  grantedCapabilities: readonly BridgeCapability[]
  handleRequest: BridgeRequestHandler
  locale?: () => string
  themeTokens?: () => Record<string, string>
  activeSession?: () => string | null
  nonceFactory?: () => string
  requestIdFactory?: () => string
  channelFactory?: () => BridgeMessageChannel
  onDiagnostic?: (message: string) => void
}

function randomHex(bytes: number) {
  const values = new Uint8Array(bytes)
  globalThis.crypto.getRandomValues(values)
  return Array.from(values, (value) => value.toString(16).padStart(2, "0")).join("")
}

function browserChannelFactory(): BridgeMessageChannel {
  return new MessageChannel() as unknown as BridgeMessageChannel
}

export class HostPluginBridge {
  private readonly capabilities: Set<BridgeCapability>
  private readonly onWindowMessage = (event: MessageEvent<unknown>) => this.acceptWindowMessage(event)
  private port: BridgeMessagePort | null = null
  private nonce: string | null = null
  private lastIncomingSeq = 0
  private outgoingSeq = 0
  private readonly requestIds = new Set<string>()
  private started = false
  private connected = false

  constructor(private readonly options: HostPluginBridgeOptions) {
    this.capabilities = new Set(options.grantedCapabilities)
  }

  get isConnected() {
    return this.connected
  }

  get isStarted() {
    return this.started
  }

  start() {
    if (this.started) return
    this.started = true
    window.addEventListener("message", this.onWindowMessage)
  }

  acceptWindowMessage(event: MessageEvent<unknown>) {
    if (!this.started || event.source !== this.options.frameTarget) return
    if (!isBridgeReadyMessage(event.data)) return
    if (event.data.pluginId !== this.options.pluginId) {
      this.options.onDiagnostic?.("Ignored READY with an unexpected plugin identity.")
      return
    }
    this.beginHandshake()
  }

  private beginHandshake() {
    this.closeConnection()
    const channel = (this.options.channelFactory ?? browserChannelFactory)()
    const port = channel.port1
    this.port = port
    this.nonce = (this.options.nonceFactory ?? (() => randomHex(32)))()
    port.onmessage = (event) => this.acceptPortMessage(port, event)
    port.start()
    this.options.frameTarget.postMessage(
      {
        type: "CHALLENGE",
        protocolVersion: PLUGIN_BRIDGE_PROTOCOL,
        pluginId: this.options.pluginId,
        instanceId: this.options.instanceId,
        nonce: this.nonce,
      },
      "*",
      [channel.port2 as unknown as Transferable],
    )
  }

  private acceptPortMessage(port: BridgeMessagePort, event: MessageEvent<unknown>) {
    if (this.port !== port || !this.started) return
    if (!this.connected) {
      this.acceptHello(event.data)
      return
    }
    void this.acceptRequest(event.data)
  }

  private acceptHello(value: unknown) {
    if (
      !isBridgeHelloMessage(value) ||
      value.pluginId !== this.options.pluginId ||
      value.instanceId !== this.options.instanceId ||
      value.nonce !== this.nonce
    ) {
      this.options.onDiagnostic?.("Rejected invalid bridge HELLO.")
      this.closeConnection()
      return
    }
    this.connected = true
    const welcome: BridgeWelcomeMessage = {
      type: "WELCOME",
      protocolVersion: PLUGIN_BRIDGE_PROTOCOL,
      pluginId: this.options.pluginId,
      instanceId: this.options.instanceId,
      grantedCapabilities: [...this.capabilities],
      themeTokens: this.options.themeTokens?.() ?? {},
      locale: this.options.locale?.() ?? "zh-CN",
      activeSession: this.options.activeSession?.() ?? null,
    }
    this.port?.postMessage(welcome)
  }

  private async acceptRequest(value: unknown) {
    const parsed = parseBridgeRequestEnvelope(value)
    if (!parsed.ok) {
      if (parsed.requestId) this.sendError(parsed.requestId, parsed.code, parsed.message)
      return
    }
    const request = parsed.value
    if (request.pluginId !== this.options.pluginId || request.instanceId !== this.options.instanceId) {
      this.sendError(request.requestId, "BRIDGE_IDENTITY_MISMATCH", "Bridge request identity does not match this instance.")
      return
    }
    if (request.seq <= this.lastIncomingSeq || this.requestIds.has(request.requestId)) {
      this.sendError(request.requestId, "BRIDGE_REPLAY_REJECTED", "Bridge request sequence or requestId was already accepted.")
      return
    }
    this.lastIncomingSeq = request.seq
    this.requestIds.add(request.requestId)
    if (!this.capabilities.has(request.type)) {
      this.sendError(request.requestId, "BRIDGE_CAPABILITY_DENIED", `Capability was not granted: ${request.type}`)
      return
    }
    try {
      const data = await this.options.handleRequest(request)
      this.sendResponse(request.requestId, true, data)
    } catch (error) {
      void error
      this.options.onDiagnostic?.("Bridge request handler failed; details were withheld from the plugin frame.")
      this.sendError(request.requestId, "BRIDGE_REQUEST_FAILED", "The host could not complete this request.")
    }
  }

  private sendError(requestId: string, code: BridgeErrorBody["code"], message: string) {
    this.sendResponse(requestId, false, undefined, { code, message })
  }

  private sendResponse(requestId: string, ok: boolean, data?: unknown, error?: BridgeErrorBody) {
    if (!this.port || !this.connected) return
    const response: BridgeResponseEnvelope = {
      protocol: PLUGIN_BRIDGE_PROTOCOL,
      pluginId: this.options.pluginId,
      instanceId: this.options.instanceId,
      seq: ++this.outgoingSeq,
      requestId: (this.options.requestIdFactory ?? (() => globalThis.crypto.randomUUID()))(),
      replyTo: requestId,
      type: "RESPONSE",
      ok,
      ...(ok ? { data } : { error }),
    }
    this.port.postMessage(response)
  }

  reset() {
    this.closeConnection()
  }

  dispose() {
    if (!this.started) return
    window.removeEventListener("message", this.onWindowMessage)
    this.started = false
    this.closeConnection()
  }

  private closeConnection() {
    const port = this.port
    this.port = null
    if (port) {
      port.onmessage = null
      port.close()
    }
    this.nonce = null
    this.connected = false
    this.lastIncomingSeq = 0
    this.outgoingSeq = 0
    this.requestIds.clear()
  }
}
