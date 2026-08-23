export const SIDECAR_PROTOCOL = "next-trainer.pi-sidecar/1"
export const SIDECAR_PROTOCOL_VERSION = "1"
export const SIDECAR_VERSION = "0.1.0"
export const PI_VERSION = "0.84.2"
export const BUILD_NODE_VERSION = "22.19.0"

export type PromptMode = "prompt" | "steer" | "followUp"
export type ThinkingLevel = "off" | "minimal" | "low" | "medium" | "high" | "xhigh" | "max" | "auto"
export type StopReason = "stop" | "length" | "toolUse" | "error" | "aborted" | "unknown"

export interface SessionCreateRequest {
  profileId: string
  modelId?: string
  purpose: string
  thinkingLevel?: ThinkingLevel
}

export interface PromptRequest {
  requestId: string
  text: string
  mode?: PromptMode
  images?: Array<{ resourceId: string; mediaType: string }>
}

export interface ProviderProfileInput {
  providerId: string
  modelId: string
  endpoint: string
  apiKey: string
}

export interface ProviderStatus {
  profileId: string
  providerId: string
  modelId: string
  endpoint: string
  baseUrl: string
  configured: boolean
  source: "plugin-auth"
  fingerprint: string
  lastTest: null | { ok: boolean; testedAt: string }
}

export interface SessionSnapshot {
  sessionId: string
  profileId: string
  modelId?: string
  createdAt?: string
  updatedAt?: string
  name?: string
  purpose: string
  state: "idle" | "queued" | "running" | "cancelling" | "closed" | "error"
  runId: number
  activeRunId: number | null
  lastStopReason: StopReason | null
}

export interface AgentEventEnvelope {
  protocol: typeof SIDECAR_PROTOCOL
  eventId: number
  sessionId: string
  runId: number
  type: string
  timestamp: string
  payload: Record<string, unknown>
}

export interface ApiSuccess<T> {
  ok: true
  requestId: string
  data: T
}

export interface ApiFailure {
  ok: false
  requestId: string
  error: {
    code: string
    message: string
    retryable: boolean
  }
}
