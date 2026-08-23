import type { StopReason } from "../contracts.ts"

export interface RuntimeEvent {
  type: string
  payload?: Record<string, unknown>
}

export interface DerivedTerminalEvent {
  type: "prompt_done" | "agent_settled"
  payload: Record<string, unknown>
}

function isStopReason(value: unknown): value is StopReason {
  return ["stop", "length", "toolUse", "error", "aborted", "unknown"].includes(String(value))
}

export class TerminalReducer {
  #lastStopReason: StopReason = "unknown"
  #runtimeError = false
  #promptDone = false
  #settled = false

  observe(event: RuntimeEvent): void {
    if (event.type === "message_end" && event.payload?.role === "assistant") {
      const stopReason = event.payload.stopReason
      if (isStopReason(stopReason)) this.#lastStopReason = stopReason
    }
    if (event.type === "error") {
      this.#runtimeError = true
      this.#lastStopReason = event.payload?.aborted === true ? "aborted" : "error"
    }
    // `agent_end` deliberately has no terminal effect.
  }

  promptResolved(): DerivedTerminalEvent | null {
    if (this.#promptDone) return null
    this.#promptDone = true
    const failed = this.#runtimeError || this.#lastStopReason === "error" || this.#lastStopReason === "aborted"
    return {
      type: "prompt_done",
      payload: { ok: !failed, stopReason: this.#lastStopReason },
    }
  }

  agentSettled(): DerivedTerminalEvent | null {
    if (this.#settled) return null
    this.#settled = true
    return {
      type: "agent_settled",
      payload: { stopReason: this.#lastStopReason },
    }
  }

  get lastStopReason(): StopReason {
    return this.#lastStopReason
  }
}
