import assert from "node:assert/strict"
import { mkdtemp, rm } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"
import { SessionRegistry } from "../../src/pi/session-registry.ts"
import { FakeRuntimeAdapter } from "../helpers/fake-runtime.ts"

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
