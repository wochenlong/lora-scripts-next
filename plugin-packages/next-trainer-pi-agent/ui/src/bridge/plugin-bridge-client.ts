import type { AgentEvent } from "../contracts/agent-transport.ts";

export const PLUGIN_BRIDGE_PROTOCOL = "next-trainer.plugin-bridge/1" as const;

export const BRIDGE_REQUEST_TYPES = [
  "session.list", "session.create", "session.rename", "session.delete", "session.getState",
  "session.getHistory", "session.getThinking", "session.prompt", "session.cancel", "session.compact",
  "session.setModel", "session.setThinkingLevel", "session.recallQueue", "session.subscribe",
  "provider.list", "provider.status", "provider.saveKey", "provider.removeKey", "provider.test",
  "resource.pick", "resource.getSummary", "artifact.open", "artifact.download",
  "confirmation.request", "confirmation.getResult", "navigation.openExternal",
  "navigation.openPluginRoute", "theme.get", "locale.get", "context.get",
] as const;

export type BridgeRequestType = (typeof BRIDGE_REQUEST_TYPES)[number];

export interface BridgeWelcome {
  type: "WELCOME";
  protocolVersion: typeof PLUGIN_BRIDGE_PROTOCOL;
  pluginId: string;
  instanceId: string;
  grantedCapabilities: BridgeRequestType[];
  themeTokens: Record<string, string>;
  locale: string;
  activeSession: string | null;
}

interface BridgePort {
  onmessage: ((event: MessageEvent<unknown>) => void) | null;
  postMessage(message: unknown): void;
  start(): void;
  close(): void;
}

interface ParentTarget {
  postMessage(message: unknown, targetOrigin: string): void;
}

interface WindowScope {
  addEventListener(type: "message", listener: (event: MessageEvent<unknown>) => void): void;
  removeEventListener(type: "message", listener: (event: MessageEvent<unknown>) => void): void;
}

export interface PluginBridgeClientOptions {
  pluginId: string;
  scope?: WindowScope;
  parentTarget?: ParentTarget;
  requestIdFactory?: () => string;
  onDiagnostic?: (message: string) => void;
}

interface PendingRequest {
  resolve(value: unknown): void;
  reject(reason: Error): void;
}

interface BridgeResponse {
  protocol: typeof PLUGIN_BRIDGE_PROTOCOL;
  pluginId: string;
  instanceId: string;
  seq: number;
  requestId: string;
  replyTo: string;
  type: "RESPONSE";
  ok: boolean;
  data?: unknown;
  error?: { code?: string; message?: string };
}

interface BridgeEventEnvelope {
  protocol: typeof PLUGIN_BRIDGE_PROTOCOL;
  pluginId: string;
  instanceId: string;
  seq: number;
  requestId: string;
  type: "EVENT";
  eventId: string;
  sessionId: string;
  runId: number;
  data: AgentEvent;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isPositiveInteger(value: unknown): value is number {
  return Number.isSafeInteger(value) && Number(value) > 0;
}

function isBridgeResponse(value: Record<string, unknown>): boolean {
  if (
    value.type !== "RESPONSE" ||
    typeof value.requestId !== "string" ||
    !value.requestId ||
    typeof value.replyTo !== "string" ||
    !value.replyTo ||
    typeof value.ok !== "boolean"
  ) return false;
  if (value.ok) return !Object.hasOwn(value, "error");
  return isRecord(value.error) && typeof value.error.code === "string" && typeof value.error.message === "string";
}

function isBridgeEventEnvelope(value: Record<string, unknown>): boolean {
  if (
    value.type !== "EVENT" ||
    typeof value.requestId !== "string" ||
    !value.requestId ||
    typeof value.eventId !== "string" ||
    !value.eventId ||
    typeof value.sessionId !== "string" ||
    !value.sessionId ||
    !Number.isSafeInteger(value.runId) ||
    Number(value.runId) < 0 ||
    !isRecord(value.data)
  ) {
    return false;
  }
  return (
    typeof value.data.type === "string" &&
    value.data.eventId === value.eventId &&
    value.data.sessionId === value.sessionId &&
    value.data.runId === value.runId
  );
}

function randomRequestId(): string {
  if (typeof globalThis.crypto?.randomUUID === "function") return globalThis.crypto.randomUUID();
  const bytes = new Uint8Array(16);
  globalThis.crypto.getRandomValues(bytes);
  return Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("");
}

export class PluginBridgeError extends Error {
  readonly code: string;

  constructor(message: string, code: string) {
    super(message);
    this.name = "PluginBridgeError";
    this.code = code;
  }
}

export class PluginBridgeClient {
  private readonly options: PluginBridgeClientOptions;
  private readonly scope: WindowScope;
  private readonly parentTarget: ParentTarget;
  private readonly requestIdFactory: () => string;
  private readonly pending = new Map<string, PendingRequest>();
  private readonly eventListeners = new Set<(event: AgentEvent) => void>();
  private readonly onWindowMessage = (event: MessageEvent<unknown>) => this.acceptChallenge(event);
  private port: BridgePort | null = null;
  private instanceId: string | null = null;
  private granted = new Set<BridgeRequestType>();
  private outgoingSeq = 0;
  private incomingSeq = 0;
  private started = false;
  private connected = false;
  private resolveWelcome!: (welcome: BridgeWelcome) => void;
  private rejectWelcome!: (reason: Error) => void;
  private readonly welcomePromise: Promise<BridgeWelcome>;

  constructor(options: PluginBridgeClientOptions) {
    this.options = options;
    this.scope = options.scope ?? window;
    this.parentTarget = options.parentTarget ?? window.parent;
    this.requestIdFactory = options.requestIdFactory ?? randomRequestId;
    this.welcomePromise = new Promise<BridgeWelcome>((resolve, reject) => {
      this.resolveWelcome = resolve;
      this.rejectWelcome = reject;
    });
  }

  start(): Promise<BridgeWelcome> {
    if (!this.started) {
      this.started = true;
      this.scope.addEventListener("message", this.onWindowMessage);
      this.parentTarget.postMessage({
        type: "READY",
        pluginId: this.options.pluginId,
        protocolVersion: PLUGIN_BRIDGE_PROTOCOL,
      }, "*");
    }
    return this.welcomePromise;
  }

  private acceptChallenge(event: MessageEvent<unknown>): void {
    if (!this.started || event.source !== this.parentTarget || !isRecord(event.data)) return;
    const challenge = event.data;
    if (
      challenge.type !== "CHALLENGE" ||
      challenge.protocolVersion !== PLUGIN_BRIDGE_PROTOCOL ||
      challenge.pluginId !== this.options.pluginId ||
      typeof challenge.instanceId !== "string" ||
      !challenge.instanceId ||
      typeof challenge.nonce !== "string" ||
      !challenge.nonce ||
      event.ports.length !== 1
    ) {
      this.options.onDiagnostic?.("Ignored an invalid bridge challenge.");
      return;
    }
    this.disconnectPort(new PluginBridgeError("The bridge connection was replaced.", "BRIDGE_REPLACED"));
    this.instanceId = challenge.instanceId;
    this.port = event.ports[0] as unknown as BridgePort;
    this.port.onmessage = (portEvent) => this.acceptPortMessage(portEvent.data);
    this.port.start();
    this.port.postMessage({
      type: "HELLO",
      pluginId: this.options.pluginId,
      instanceId: challenge.instanceId,
      protocolVersion: PLUGIN_BRIDGE_PROTOCOL,
      nonce: challenge.nonce,
    });
  }

  private acceptPortMessage(value: unknown): void {
    if (!this.connected) {
      this.acceptWelcome(value);
      return;
    }
    if (!isRecord(value) || value.protocol !== PLUGIN_BRIDGE_PROTOCOL || value.pluginId !== this.options.pluginId) {
      this.options.onDiagnostic?.("Ignored a bridge message with an invalid identity.");
      return;
    }
    if (value.instanceId !== this.instanceId || !isPositiveInteger(value.seq)) {
      this.options.onDiagnostic?.("Ignored a bridge message with an invalid identity.");
      return;
    }
    const response = isBridgeResponse(value);
    const event = isBridgeEventEnvelope(value);
    if (!response && !event) {
      this.options.onDiagnostic?.("Ignored an unsupported or invalid bridge message.");
      return;
    }
    if (value.seq <= this.incomingSeq) {
      this.options.onDiagnostic?.("Ignored a replayed or stale bridge message.");
      return;
    }
    this.incomingSeq = value.seq;
    if (response) this.acceptResponse(value as unknown as BridgeResponse);
    else this.acceptEvent(value as unknown as BridgeEventEnvelope);
  }

  private acceptWelcome(value: unknown): void {
    if (
      !isRecord(value) ||
      value.type !== "WELCOME" ||
      value.protocolVersion !== PLUGIN_BRIDGE_PROTOCOL ||
      value.pluginId !== this.options.pluginId ||
      value.instanceId !== this.instanceId ||
      !Array.isArray(value.grantedCapabilities) ||
      !value.grantedCapabilities.every((item) => BRIDGE_REQUEST_TYPES.includes(item as BridgeRequestType)) ||
      !isRecord(value.themeTokens) ||
      typeof value.locale !== "string" ||
      !(typeof value.activeSession === "string" || value.activeSession === null)
    ) {
      const error = new PluginBridgeError("The host returned an invalid bridge welcome.", "BRIDGE_HANDSHAKE_FAILED");
      this.rejectWelcome(error);
      this.close();
      return;
    }
    this.granted = new Set(value.grantedCapabilities as BridgeRequestType[]);
    this.connected = true;
    this.resolveWelcome(value as unknown as BridgeWelcome);
  }

  private acceptResponse(response: BridgeResponse): void {
    if (typeof response.replyTo !== "string") return;
    const pending = this.pending.get(response.replyTo);
    if (!pending) {
      this.options.onDiagnostic?.("Ignored a bridge response without a pending request.");
      return;
    }
    this.pending.delete(response.replyTo);
    if (response.ok) pending.resolve(response.data);
    else pending.reject(new PluginBridgeError(
      response.error?.message || "The host could not complete this request.",
      response.error?.code || "BRIDGE_REQUEST_FAILED",
    ));
  }

  private acceptEvent(envelope: BridgeEventEnvelope): void {
    for (const listener of this.eventListeners) listener(envelope.data);
  }

  request<T>(type: BridgeRequestType, payload: Record<string, unknown>): Promise<T> {
    if (!this.connected || !this.port || !this.instanceId) {
      return Promise.reject(new PluginBridgeError("The plugin bridge is not connected.", "BRIDGE_NOT_CONNECTED"));
    }
    if (!this.granted.has(type)) {
      return Promise.reject(new PluginBridgeError("The host did not grant this capability.", "BRIDGE_CAPABILITY_DENIED"));
    }
    const requestId = this.requestIdFactory();
    const promise = new Promise<T>((resolve, reject) => {
      this.pending.set(requestId, { resolve: resolve as (value: unknown) => void, reject });
    });
    this.port.postMessage({
      protocol: PLUGIN_BRIDGE_PROTOCOL,
      pluginId: this.options.pluginId,
      instanceId: this.instanceId,
      seq: ++this.outgoingSeq,
      requestId,
      type,
      payload,
    });
    return promise;
  }

  onEvent(listener: (event: AgentEvent) => void): () => void {
    this.eventListeners.add(listener);
    return () => this.eventListeners.delete(listener);
  }

  close(): void {
    if (this.started) this.scope.removeEventListener("message", this.onWindowMessage);
    this.started = false;
    this.connected = false;
    this.disconnectPort(new PluginBridgeError("The plugin bridge was closed.", "BRIDGE_CLOSED"));
  }

  private disconnectPort(error: Error): void {
    const port = this.port;
    this.port = null;
    this.connected = false;
    if (port) {
      port.onmessage = null;
      port.close();
    }
    for (const pending of this.pending.values()) pending.reject(error);
    this.pending.clear();
    this.instanceId = null;
    this.granted.clear();
    this.outgoingSeq = 0;
    this.incomingSeq = 0;
  }
}
