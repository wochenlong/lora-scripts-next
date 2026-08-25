import assert from "node:assert/strict"
import test from "node:test"

import { uiHistoryMessage } from "../../src/server.ts"

test("history projection preserves an existing message id", () => {
  const projected = uiHistoryMessage({
    type: "message",
    id: "entry-id",
    message: { id: "message-id", role: "assistant", content: [] },
  }, "session-1", "start", 0)
  assert.equal(projected.id, "message-id")
})

test("history projection derives a stable id for legacy Pi JSONL messages", () => {
  const entry = {
    type: "message",
    message: { role: "assistant", timestamp: 1234, content: [{ type: "text", text: "answer" }] },
  }
  const first = uiHistoryMessage(entry, "session-1", "start", 2)
  const second = uiHistoryMessage(entry, "session-1", "start", 2)
  assert.equal(first.id, "history-session-1-start-2-assistant-1234")
  assert.equal(second.id, first.id)
})
