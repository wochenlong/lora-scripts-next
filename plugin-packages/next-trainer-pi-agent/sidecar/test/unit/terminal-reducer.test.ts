import assert from "node:assert/strict"
import test from "node:test"
import { TerminalReducer } from "../../src/pi/terminal-reducer.ts"

test("agent_end never completes a prompt", () => {
  const reducer = new TerminalReducer()
  reducer.observe({ type: "agent_end" })
  assert.deepEqual(reducer.promptResolved(), {
    type: "prompt_done",
    payload: { ok: true, stopReason: "unknown" },
  })
})

test("assistant error and aborted stop reasons fail prompt_done", () => {
  for (const stopReason of ["error", "aborted"] as const) {
    const reducer = new TerminalReducer()
    reducer.observe({ type: "message_end", payload: { role: "assistant", stopReason } })
    assert.deepEqual(reducer.promptResolved(), {
      type: "prompt_done",
      payload: { ok: false, stopReason },
    })
    assert.equal(reducer.promptResolved(), null)
  }
})

test("runtime exceptions derive explicit error or aborted stop reasons", () => {
  for (const [aborted, stopReason] of [[false, "error"], [true, "aborted"]] as const) {
    const reducer = new TerminalReducer()
    reducer.observe({ type: "error", payload: { aborted } })
    assert.deepEqual(reducer.promptResolved(), {
      type: "prompt_done",
      payload: { ok: false, stopReason },
    })
  }
})

test("agent_settled is a distinct idempotent convergence event", () => {
  const reducer = new TerminalReducer()
  reducer.observe({ type: "message_end", payload: { role: "assistant", stopReason: "stop" } })
  assert.deepEqual(reducer.agentSettled(), {
    type: "agent_settled",
    payload: { stopReason: "stop" },
  })
  assert.equal(reducer.agentSettled(), null)
})
