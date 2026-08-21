import assert from "node:assert/strict";
import test from "node:test";

import {
  conversationReducer,
  INITIAL_CONVERSATION_STATE,
} from "../src/events/conversation-reducer.ts";

const session = {
  id: "session-1",
  runId: 3,
  status: "running",
  model: { profileId: "provider", modelId: "model" },
  thinkingLevel: "auto",
  queue: { steering: [], followUp: [] },
};

const base = { eventId: "event-1", sessionId: "session-1", runId: 3 };

test("a reconnect snapshot replaces the same assistant message without duplication", () => {
  const initial = conversationReducer(INITIAL_CONVERSATION_STATE, {
    type: "history_loaded",
    history: {
      session,
      messages: [{ role: "assistant", id: "assistant-1", content: [{ type: "text", text: "old" }] }],
      hasMore: false,
    },
  });
  const reconnected = conversationReducer(initial, {
    type: "event",
    event: {
      ...base,
      type: "state_snapshot",
      state: session,
      snapshot: { role: "assistant", id: "assistant-1", content: [{ type: "text", text: "authoritative" }] },
    },
  });
  assert.equal(reconnected.messages.length, 1);
  assert.equal(reconnected.messages[0].content[0].text, "authoritative");
});

test("assistant deltas build text, thinking and tool input from one baseline", () => {
  let state = conversationReducer(INITIAL_CONVERSATION_STATE, {
    type: "event",
    event: {
      ...base,
      type: "message_start",
      message: { role: "assistant", id: "assistant-1", content: [] },
    },
  });
  for (const assistantMessageEvent of [
    { type: "thinking_delta", contentIndex: 0, delta: "reason" },
    { type: "text_delta", contentIndex: 1, delta: "answer" },
    { type: "toolcall_delta", contentIndex: 2, id: "tool-1", toolName: "draft_config", delta: "{\"a\":" },
    { type: "toolcall_delta", contentIndex: 2, id: "tool-1", toolName: "draft_config", delta: "1}" },
  ]) {
    state = conversationReducer(state, {
      type: "event",
      event: { ...base, eventId: `${assistantMessageEvent.type}-${Math.random()}`, type: "message_update", assistantMessageEvent },
    });
  }
  const assistant = state.messages[0];
  assert.equal(assistant.content[0].thinking, "reason");
  assert.equal(assistant.content[1].text, "answer");
  assert.equal(assistant.content[2].rawInput, "{\"a\":1}");
});

test("a delta without a message baseline is ignored", () => {
  const state = conversationReducer(INITIAL_CONVERSATION_STATE, {
    type: "event",
    event: {
      ...base,
      type: "message_update",
      assistantMessageEvent: { type: "text_delta", contentIndex: 0, delta: "orphan" },
    },
  });
  assert.deepEqual(state.messages, []);
});

test("tool progress is bounded to the active tool and completion appends its result", () => {
  let state = conversationReducer(INITIAL_CONVERSATION_STATE, {
    type: "event",
    event: { ...base, type: "tool_execution_start", toolCallId: "tool-1", toolName: "inspect_dataset" },
  });
  state = conversationReducer(state, {
    type: "event",
    event: {
      ...base,
      eventId: "event-2",
      type: "tool_execution_update",
      toolCallId: "tool-1",
      toolName: "inspect_dataset",
      progress: "20/100",
    },
  });
  assert.equal(state.runningTools[0].progress, "20/100");
  state = conversationReducer(state, {
    type: "event",
    event: {
      ...base,
      eventId: "event-3",
      type: "tool_execution_end",
      toolCallId: "tool-1",
      toolName: "inspect_dataset",
      result: {
        role: "toolResult",
        id: "result-1",
        toolCallId: "tool-1",
        toolName: "inspect_dataset",
        content: "done",
      },
    },
  });
  assert.equal(state.runningTools.length, 0);
  assert.equal(state.messages[0].role, "toolResult");
});
