export const PLUGIN_BRIDGE_PROTOCOL = "next-trainer.plugin-bridge/1" as const

export const BRIDGE_REQUEST_TYPES = [
  "session.list",
  "session.create",
  "session.rename",
  "session.delete",
  "session.getState",
  "session.getHistory",
  "session.getThinking",
  "session.prompt",
  "session.cancel",
  "session.compact",
  "session.setModel",
  "session.setThinkingLevel",
  "session.recallQueue",
  "session.subscribe",
  "provider.list",
  "provider.status",
  "provider.saveKey",
  "provider.removeKey",
  "provider.test",
  "resource.pick",
  "resource.getSummary",
  "artifact.open",
  "artifact.download",
  "confirmation.request",
  "confirmation.getResult",
  "navigation.openExternal",
  "navigation.openPluginRoute",
  "theme.get",
  "locale.get",
  "context.get",
] as const

export type BridgeRequestType = (typeof BRIDGE_REQUEST_TYPES)[number]
export type BridgeCapability = BridgeRequestType

export interface BridgeReadyMessage {
  type: "READY"
  pluginId: string
  protocolVersion: typeof PLUGIN_BRIDGE_PROTOCOL
}

export interface BridgeHelloMessage {
  type: "HELLO"
  pluginId: string
  instanceId: string
  protocolVersion: typeof PLUGIN_BRIDGE_PROTOCOL
  nonce: string
}

export interface BridgeRequestEnvelope {
  protocol: typeof PLUGIN_BRIDGE_PROTOCOL
  pluginId: string
  instanceId: string
  seq: number
  requestId: string
  type: BridgeRequestType
  payload: Record<string, unknown>
}

export interface BridgeErrorBody {
  code:
    | "BRIDGE_SCHEMA_UNSUPPORTED"
    | "BRIDGE_IDENTITY_MISMATCH"
    | "BRIDGE_REPLAY_REJECTED"
    | "BRIDGE_CAPABILITY_DENIED"
    | "BRIDGE_REQUEST_FAILED"
    // Stable capability-broker contract codes (host broker or sidecar,
    // e.g. PROVIDER_NOT_CONFIGURED) are passed through verbatim so the
    // plugin UI can react to them. Only typed contract errors travel this
    // channel; host-internal failures stay sanitized as BRIDGE_REQUEST_FAILED.
    | (string & {})
  message: string
}

export interface BridgeResponseEnvelope {
  protocol: typeof PLUGIN_BRIDGE_PROTOCOL
  pluginId: string
  instanceId: string
  seq: number
  requestId: string
  replyTo: string
  type: "RESPONSE"
  ok: boolean
  data?: unknown
  error?: BridgeErrorBody
}

export interface BridgeEventEnvelope {
  protocol: typeof PLUGIN_BRIDGE_PROTOCOL
  pluginId: string
  instanceId: string
  seq: number
  requestId: string
  type: "EVENT"
  eventId: string
  sessionId: string
  runId: number
  data: Record<string, unknown>
}

export interface BridgeWelcomeMessage {
  type: "WELCOME"
  protocolVersion: typeof PLUGIN_BRIDGE_PROTOCOL
  pluginId: string
  instanceId: string
  grantedCapabilities: BridgeCapability[]
  themeTokens: Record<string, string>
  locale: string
  activeSession: string | null
}

const requestTypeSet = new Set<string>(BRIDGE_REQUEST_TYPES)

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
}

function hasExactKeys(value: Record<string, unknown>, keys: readonly string[]) {
  const actual = Object.keys(value).sort()
  const expected = [...keys].sort()
  return actual.length === expected.length && actual.every((key, index) => key === expected[index])
}

function hasOnlyKeys(value: Record<string, unknown>, required: readonly string[], optional: readonly string[] = []) {
  const keys = Object.keys(value)
  return required.every((key) => keys.includes(key)) && keys.every((key) => required.includes(key) || optional.includes(key))
}

function nonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0
}

export function isBridgeReadyMessage(value: unknown): value is BridgeReadyMessage {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["type", "pluginId", "protocolVersion"]) &&
    value.type === "READY" &&
    nonEmptyString(value.pluginId) &&
    value.protocolVersion === PLUGIN_BRIDGE_PROTOCOL
  )
}

export function isBridgeHelloMessage(value: unknown): value is BridgeHelloMessage {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["type", "pluginId", "instanceId", "protocolVersion", "nonce"]) &&
    value.type === "HELLO" &&
    nonEmptyString(value.pluginId) &&
    nonEmptyString(value.instanceId) &&
    value.protocolVersion === PLUGIN_BRIDGE_PROTOCOL &&
    nonEmptyString(value.nonce)
  )
}

type PayloadValidator = (payload: Record<string, unknown>) => boolean

const emptyPayload: PayloadValidator = (payload) => hasExactKeys(payload, [])
const optionalSessionName: PayloadValidator = (payload) =>
  hasOnlyKeys(payload, [], ["name", "model", "thinkingLevel"]) &&
  (payload.name === undefined || nonEmptyString(payload.name)) &&
  (payload.model === undefined || isModelSelection(payload.model)) &&
  (payload.thinkingLevel === undefined || isThinkingLevel(payload.thinkingLevel))
const sessionIdOnly: PayloadValidator = (payload) => hasExactKeys(payload, ["sessionId"]) && nonEmptyString(payload.sessionId)
const profileIdOnly: PayloadValidator = (payload) => hasExactKeys(payload, ["profileId"]) && nonEmptyString(payload.profileId)
const nonNegativeInteger = (value: unknown) => Number.isSafeInteger(value) && Number(value) >= 0
const positiveInteger = (value: unknown) => Number.isSafeInteger(value) && Number(value) > 0
const THINKING_LEVELS = new Set(["auto", "off", "minimal", "low", "medium", "high", "xhigh", "max"])
const RESOURCE_KINDS = new Set(["dataset", "training-config", "curve", "knowledge"])

function isThinkingLevel(value: unknown) {
  return nonEmptyString(value) && THINKING_LEVELS.has(value)
}

function isModelSelection(value: unknown) {
  return (
    isRecord(value) &&
    hasExactKeys(value, ["profileId", "modelId"]) &&
    nonEmptyString(value.profileId) &&
    nonEmptyString(value.modelId)
  )
}

function isStringArray(value: unknown) {
  return Array.isArray(value) && value.every(nonEmptyString)
}

function isImageAttachment(value: unknown) {
  return (
    isRecord(value) &&
    hasOnlyKeys(value, ["data", "mimeType"], ["name"]) &&
    nonEmptyString(value.data) &&
    nonEmptyString(value.mimeType) &&
    value.mimeType.startsWith("image/") &&
    (value.name === undefined || nonEmptyString(value.name))
  )
}

function isPromptInput(value: unknown) {
  if (!isRecord(value) || !hasOnlyKeys(value, ["text", "clientSubmissionId"], ["images", "streamingBehavior"])) return false
  if (typeof value.text !== "string" || !nonEmptyString(value.clientSubmissionId)) return false
  if (value.streamingBehavior !== undefined && value.streamingBehavior !== "steer" && value.streamingBehavior !== "followUp") {
    return false
  }
  if (value.images !== undefined && (!Array.isArray(value.images) || !value.images.every(isImageAttachment))) return false
  return value.text.trim().length > 0 || (Array.isArray(value.images) && value.images.length > 0)
}

function isArtifactReference(payload: Record<string, unknown>) {
  return (
    hasExactKeys(payload, ["artifactId", "title", "kind"]) &&
    nonEmptyString(payload.artifactId) &&
    nonEmptyString(payload.title) &&
    nonEmptyString(payload.kind)
  )
}

export const BRIDGE_PAYLOAD_VALIDATORS: Readonly<Record<BridgeRequestType, PayloadValidator>> = Object.freeze({
  "session.list": emptyPayload,
  "session.create": optionalSessionName,
  "session.rename": (payload) =>
    hasExactKeys(payload, ["sessionId", "name"]) && nonEmptyString(payload.sessionId) && nonEmptyString(payload.name),
  "session.delete": sessionIdOnly,
  "session.getState": sessionIdOnly,
  "session.getHistory": (payload) =>
    hasOnlyKeys(payload, ["sessionId"], ["cursor", "limit", "deferThinking", "deferMedia"]) &&
    nonEmptyString(payload.sessionId) &&
    (payload.cursor === undefined || nonEmptyString(payload.cursor)) &&
    (payload.limit === undefined || positiveInteger(payload.limit)) &&
    (payload.deferThinking === undefined || typeof payload.deferThinking === "boolean") &&
    (payload.deferMedia === undefined || typeof payload.deferMedia === "boolean"),
  "session.getThinking": (payload) =>
    hasExactKeys(payload, ["sessionId", "entryId", "blockIndex"]) &&
    nonEmptyString(payload.sessionId) &&
    nonEmptyString(payload.entryId) &&
    nonNegativeInteger(payload.blockIndex),
  "session.prompt": (payload) =>
    hasExactKeys(payload, ["sessionId", "input"]) && nonEmptyString(payload.sessionId) && isPromptInput(payload.input),
  "session.cancel": sessionIdOnly,
  "session.compact": (payload) =>
    hasOnlyKeys(payload, ["sessionId"], ["instructions"]) &&
    nonEmptyString(payload.sessionId) &&
    (payload.instructions === undefined || nonEmptyString(payload.instructions)),
  "session.setModel": (payload) =>
    hasExactKeys(payload, ["sessionId", "model"]) && nonEmptyString(payload.sessionId) && isModelSelection(payload.model),
  "session.setThinkingLevel": (payload) =>
    hasExactKeys(payload, ["sessionId", "level"]) && nonEmptyString(payload.sessionId) && isThinkingLevel(payload.level),
  "session.recallQueue": sessionIdOnly,
  "session.subscribe": (payload) =>
    hasOnlyKeys(payload, ["sessionId"], ["cursor"]) &&
    nonEmptyString(payload.sessionId) &&
    (payload.cursor === undefined || nonEmptyString(payload.cursor)),
  "provider.list": emptyPayload,
  "provider.status": profileIdOnly,
  "provider.saveKey": (payload) =>
    hasExactKeys(payload, ["profileId", "endpoint", "modelId", "key"]) &&
    nonEmptyString(payload.profileId) &&
    nonEmptyString(payload.endpoint) &&
    nonEmptyString(payload.modelId) &&
    nonEmptyString(payload.key),
  "provider.removeKey": profileIdOnly,
  "provider.test": profileIdOnly,
  "resource.pick": (payload) =>
    hasExactKeys(payload, ["kinds"]) &&
    isStringArray(payload.kinds) &&
    payload.kinds.length > 0 &&
    new Set(payload.kinds).size === payload.kinds.length &&
    payload.kinds.every((kind) => RESOURCE_KINDS.has(kind)),
  "resource.getSummary": (payload) => hasExactKeys(payload, ["resourceId"]) && nonEmptyString(payload.resourceId),
  "artifact.open": isArtifactReference,
  "artifact.download": isArtifactReference,
  "confirmation.request": (payload) => hasExactKeys(payload, ["toolCallId"]) && nonEmptyString(payload.toolCallId),
  "confirmation.getResult": (payload) => hasExactKeys(payload, ["ticketId"]) && nonEmptyString(payload.ticketId),
  "navigation.openExternal": (payload) => hasExactKeys(payload, ["url"]) && nonEmptyString(payload.url),
  "navigation.openPluginRoute": (payload) => hasExactKeys(payload, ["route"]) && nonEmptyString(payload.route),
  "theme.get": emptyPayload,
  "locale.get": emptyPayload,
  "context.get": emptyPayload,
})

export type RequestEnvelopeParseResult =
  | { ok: true; value: BridgeRequestEnvelope }
  | { ok: false; code: BridgeErrorBody["code"]; message: string; requestId?: string; seq?: number }

export function parseBridgeRequestEnvelope(value: unknown): RequestEnvelopeParseResult {
  if (!isRecord(value)) return { ok: false, code: "BRIDGE_SCHEMA_UNSUPPORTED", message: "Bridge request must be an object." }
  const requestId = nonEmptyString(value.requestId) ? value.requestId : undefined
  const seq = Number.isSafeInteger(value.seq) && Number(value.seq) > 0 ? Number(value.seq) : undefined
  if (!hasExactKeys(value, ["protocol", "pluginId", "instanceId", "seq", "requestId", "type", "payload"])) {
    return {
      ok: false,
      code: "BRIDGE_SCHEMA_UNSUPPORTED",
      message: "Bridge request fields do not match the protocol schema.",
      requestId,
      seq,
    }
  }
  if (value.protocol !== PLUGIN_BRIDGE_PROTOCOL || !nonEmptyString(value.pluginId) || !nonEmptyString(value.instanceId)) {
    return { ok: false, code: "BRIDGE_IDENTITY_MISMATCH", message: "Bridge protocol or identity is invalid.", requestId, seq }
  }
  if (seq === undefined || requestId === undefined || !nonEmptyString(value.type) || !isRecord(value.payload)) {
    return { ok: false, code: "BRIDGE_SCHEMA_UNSUPPORTED", message: "Bridge request envelope is invalid.", requestId, seq }
  }
  if (!requestTypeSet.has(value.type)) {
    return { ok: false, code: "BRIDGE_SCHEMA_UNSUPPORTED", message: `Unsupported bridge request type: ${value.type}`, requestId, seq }
  }
  const type = value.type as BridgeRequestType
  if (!BRIDGE_PAYLOAD_VALIDATORS[type](value.payload)) {
    return { ok: false, code: "BRIDGE_SCHEMA_UNSUPPORTED", message: `Payload does not match schema for ${type}.`, requestId, seq }
  }
  return { ok: true, value: value as unknown as BridgeRequestEnvelope }
}
