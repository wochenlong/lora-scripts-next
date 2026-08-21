import type { PromptMode, SessionCreateRequest, SessionSnapshot } from "../contracts.ts"
import type { RuntimeEvent } from "./terminal-reducer.ts"
import { SidecarError } from "../errors.ts"

export interface RuntimePrompt {
  text: string
  mode: PromptMode
  images: Array<{ resourceId: string; mediaType: string }>
  signal: AbortSignal
}

export interface PiSessionHandle {
  prompt(input: RuntimePrompt): Promise<void>
  cancel(): Promise<void>
  close(): Promise<void>
  snapshot(): Promise<Partial<SessionSnapshot>>
  subscribe(listener: (event: RuntimeEvent) => void): () => void
}

export interface PiRuntimeAdapter {
  readonly ready: boolean
  createSession(sessionId: string, request: SessionCreateRequest): Promise<PiSessionHandle>
}

export class UnavailablePiRuntimeAdapter implements PiRuntimeAdapter {
  readonly ready = false

  async createSession(_sessionId: string, _request: SessionCreateRequest): Promise<PiSessionHandle> {
    throw new SidecarError(503, "PI_RUNTIME_NOT_READY", "The production Pi runtime adapter has not been initialized.", true)
  }
}
