import assert from "node:assert/strict";
import test from "node:test";

import {
  INITIAL_TERMINAL_STATE,
  isTerminal,
  reduceTerminalState,
} from "../src/events/terminal-state.ts";

const base = { eventId: "event-1", sessionId: "session-1", runId: 1 };

test("agent_end marks settlement but is not the request terminal", () => {
  const afterPass = reduceTerminalState(INITIAL_TERMINAL_STATE, { ...base, type: "agent_end" });
  assert.equal(afterPass.phase, "settling");
  assert.equal(afterPass.sawAgentEnd, true);
  assert.equal(isTerminal(afterPass), false);

  const completed = reduceTerminalState(afterPass, { ...base, eventId: "event-2", type: "prompt_done" });
  assert.equal(completed.outcome, "completed");
  assert.equal(isTerminal(completed), true);
});

test("agent_settled terminates a continued run", () => {
  const running = reduceTerminalState(INITIAL_TERMINAL_STATE, {
    ...base,
    type: "tool_execution_start",
    toolCallId: "tool-1",
    toolName: "inspect_dataset",
  });
  const settled = reduceTerminalState(running, { ...base, eventId: "event-2", type: "agent_settled" });
  assert.equal(settled.outcome, "completed");
  assert.equal(settled.phase, "terminal");
});

test("an error stop reason remains failed even when prompt_done follows", () => {
  const failedMessage = reduceTerminalState(INITIAL_TERMINAL_STATE, {
    ...base,
    type: "message_end",
    message: {
      id: "assistant-1",
      role: "assistant",
      content: [],
      stopReason: "error",
      errorMessage: "provider failure",
    },
  });
  const terminal = reduceTerminalState(failedMessage, { ...base, eventId: "event-2", type: "prompt_done" });
  assert.equal(terminal.outcome, "failed");
  assert.equal(terminal.error, "provider failure");
});

test("events from an older run cannot revive or alter the current run", () => {
  const current = reduceTerminalState(INITIAL_TERMINAL_STATE, {
    eventId: "event-new",
    sessionId: "session-1",
    runId: 7,
    type: "agent_settled",
  });
  const stale = reduceTerminalState(current, {
    eventId: "event-old",
    sessionId: "session-1",
    runId: 6,
    type: "tool_execution_start",
    toolCallId: "tool-old",
    toolName: "old_tool",
  });
  assert.deepEqual(stale, current);
});

test("an authoritative idle snapshot restores an idle UI", () => {
  const restored = reduceTerminalState(INITIAL_TERMINAL_STATE, {
    ...base,
    type: "connected",
    state: {
      id: "session-1",
      runId: 1,
      status: "idle",
      model: null,
      thinkingLevel: "auto",
      queue: { steering: [], followUp: [] },
    },
  });
  assert.equal(restored.phase, "idle");
  assert.equal(restored.outcome, null);
});
