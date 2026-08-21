/* Behavior adapted from agegr/pi-web's prompt settlement rules (MIT). */

import type { AgentEvent } from "../contracts/agent-transport.ts";

export type TerminalOutcome = "completed" | "failed" | "cancelled" | null;

export interface TerminalState {
  runId: number;
  phase: "idle" | "running" | "settling" | "terminal";
  outcome: TerminalOutcome;
  sawAgentEnd: boolean;
  finalStopReason?: string;
  error?: string;
}

export const INITIAL_TERMINAL_STATE: TerminalState = {
  runId: 0,
  phase: "idle",
  outcome: null,
  sawAgentEnd: false,
};

function beginRun(runId: number): TerminalState {
  return { runId, phase: "running", outcome: null, sawAgentEnd: false };
}

function isFailureStopReason(reason: string | undefined): boolean {
  return reason === "error" || reason === "aborted";
}

export function reduceTerminalState(state: TerminalState, event: AgentEvent): TerminalState {
  if (event.runId < state.runId) return state;
  let next = event.runId > state.runId ? beginRun(event.runId) : state;

  if (event.type === "connected" || event.type === "state_snapshot") {
    if (event.state.status === "running" || event.state.status === "cancelling") {
      return { ...next, phase: "running", outcome: null };
    }
    if (event.state.status === "failed") {
      return { ...next, phase: "terminal", outcome: "failed" };
    }
    return { runId: event.runId, phase: "idle", outcome: null, sawAgentEnd: false };
  }

  if (event.type === "message_end") {
    const stopReason = event.message.stopReason;
    if (isFailureStopReason(stopReason)) {
      return {
        ...next,
        finalStopReason: stopReason,
        outcome: "failed",
        error: event.message.errorMessage ?? `Model stopped with ${stopReason}`,
      };
    }
    return { ...next, finalStopReason: stopReason };
  }

  if (event.type === "agent_end") {
    // A Pi pass may end before a domain operation or continuation has settled.
    return { ...next, phase: "settling", sawAgentEnd: true };
  }

  if (event.type === "prompt_done" || event.type === "agent_settled") {
    return {
      ...next,
      phase: "terminal",
      outcome: next.outcome === "failed" ? "failed" : "completed",
    };
  }

  if (event.type === "cancelled") {
    return { ...next, phase: "terminal", outcome: "cancelled", finalStopReason: "aborted" };
  }

  if (event.type === "startup_error") {
    return { ...next, phase: "terminal", outcome: "failed", error: event.message };
  }

  if (next.phase === "idle") next = beginRun(event.runId);
  return next;
}

export function isTerminal(state: TerminalState): boolean {
  return state.phase === "terminal" && state.outcome !== null;
}
