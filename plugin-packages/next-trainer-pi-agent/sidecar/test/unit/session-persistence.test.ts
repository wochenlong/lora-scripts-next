import assert from "node:assert/strict"
import { mkdtemp, rm } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"
import { SessionRegistry } from "../../src/pi/session-registry.ts"
import { FakeRuntimeAdapter, waitFor } from "../helpers/fake-runtime.ts"

test("reading history does not detach an already subscribed session", async () => {
  const runtime = new FakeRuntimeAdapter()
  const registry = new SessionRegistry(runtime)
  const created = await registry.create({ profileId: "profile", modelId: "model", purpose: "subscribed-history" })
  const eventTypes: string[] = []
  const unsubscribe = await registry.subscribe(created.sessionId, (event) => eventTypes.push(event.type))

  await registry.history(created.sessionId)
  await registry.submit(created.sessionId, { requestId: "after-history", text: "continue" })
  await waitFor(() => registry.snapshot(created.sessionId).state === "idle")

  assert.ok(eventTypes.includes("message_end"), JSON.stringify(eventTypes))
  assert.ok(eventTypes.includes("prompt_done"), JSON.stringify(eventTypes))
  assert.ok(eventTypes.includes("agent_settled"), JSON.stringify(eventTypes))
  unsubscribe()
  await registry.closeAll()
})

test("session index survives registry restart and delete removes the indexed session", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "next-trainer-session-index-"))
  try {
    const runtime = new FakeRuntimeAdapter()
    const first = new SessionRegistry(runtime, { storageDir: path.join(root, "sessions") })
    const created = await first.create({ profileId: "profile", modelId: "model", purpose: "persisted" })
    await first.close(created.sessionId)

    const second = new SessionRegistry(runtime, { storageDir: path.join(root, "sessions") })
    assert.equal(second.list()[0]?.sessionId, created.sessionId)
    const history = await second.history(created.sessionId)
    assert.deepEqual(history.entries, [])
    await second.delete(created.sessionId)
    assert.deepEqual(second.list(), [])
  } finally {
    await rm(root, { recursive: true, force: true })
  }
})
