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
  hasOnlyKeys(payload, [], ["name"]) && (payload.name === undefined || nonEmptyString(payload.name))
const sessionIdOnly: PayloadValidator = (payload) => hasExactKeys(payload, ["sessionId"]) && nonEmptyString(payload.sessionId)
const profileIdOnly: PayloadValidator = (payload) => hasExactKeys(payload, ["profileId"]) && nonEmptyString(payload.profileId)
const artifactIdOnly: PayloadValidator = (payload) => hasExactKeys(payload, ["artifactId"]) && nonEmptyString(payload.artifactId)
const nonNegativeInteger = (value: unknown) => Number.isSafeInteger(value) && Number(value) >= 0
const positiveInteger = (value: unknown) => Number.isSafeInteger(value) && Number(value) > 0

export const BRIDGE_PAYLOAD_VALIDATORS: Readonly<Record<BridgeRequestType, PayloadValidator>> = Object.freeze({
  "session.list": emptyPayload,
  "session.create": optionalSessionName,
  "session.rename": (payload) =>
    hasExactKeys(payload, ["sessionId", "name"]) && nonEmptyString(payload.sessionId) && nonEmptyString(payload.name),
  "session.delete": sessionIdOnly,
  "session.getState": sessionIdOnly,
  "session.getHistory": (payload) =>
    hasOnlyKeys(payload, ["sessionId"], ["cursor", "limit"]) &&
    nonEmptyString(payload.sessionId) &&
    (payload.cursor === undefined || nonEmptyString(payload.cursor)) &&
    (payload.limit === undefined || positiveInteger(payload.limit)),
  "session.getThinking": (payload) =>
    hasExactKeys(payload, ["sessionId", "entryId", "blockIndex"]) &&
    nonEmptyString(payload.sessionId) &&
    nonEmptyString(payload.entryId) &&
    nonNegativeInteger(payload.blockIndex),
  "session.prompt": (payload) =>
    hasExactKeys(payload, ["sessionId", "input"]) && nonEmptyString(payload.sessionId) && isRecord(payload.input),
  "session.cancel": sessionIdOnly,
  "session.compact": (payload) =>
    hasOnlyKeys(payload, ["sessionId"], ["instructions"]) &&
    nonEmptyString(payload.sessionId) &&
    (payload.instructions === undefined || nonEmptyString(payload.instructions)),
  "session.setModel": (payload) =>
    hasExactKeys(payload, ["sessionId", "model"]) &&
    nonEmptyString(payload.sessionId) &&
    isRecord(payload.model) &&
    hasExactKeys(payload.model, ["profileId", "modelId"]) &&
    nonEmptyString(payload.model.profileId) &&
    nonEmptyString(payload.model.modelId),
  "session.setThinkingLevel": (payload) =>
    hasExactKeys(payload, ["sessionId", "level"]) && nonEmptyString(payload.sessionId) && nonEmptyString(payload.level),
  "session.recallQueue": sessionIdOnly,
  "session.subscribe": (payload) =>
    hasOnlyKeys(payload, ["sessionId"], ["cursor"]) &&
    nonEmptyString(payload.sessionId) &&
    (payload.cursor === undefined || nonEmptyString(payload.cursor)),
  "provider.list": emptyPayload,
  "provider.status": (payload) =>
    hasOnlyKeys(payload, [], ["profileId"]) && (payload.profileId === undefined || nonEmptyString(payload.profileId)),
  "provider.saveKey": (payload) =>
    hasExactKeys(payload, ["profileId", "endpoint", "modelId", "key"]) &&
    nonEmptyString(payload.profileId) &&
    nonEmptyString(payload.endpoint) &&
    nonEmptyString(payload.modelId) &&
    nonEmptyString(payload.key),
  "provider.removeKey": profileIdOnly,
  "provider.test": profileIdOnly,
  "resource.pick": (payload) =>
    hasOnlyKeys(payload, ["kind"], ["multiple"]) &&
    nonEmptyString(payload.kind) &&
    (payload.multiple === undefined || typeof payload.multiple === "boolean"),
  "resource.getSummary": (payload) => hasExactKeys(payload, ["resourceId"]) && nonEmptyString(payload.resourceId),
  "artifact.open": artifactIdOnly,
  "artifact.download": artifactIdOnly,
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
