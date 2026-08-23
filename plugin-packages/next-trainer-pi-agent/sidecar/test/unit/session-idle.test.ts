import assert from "node:assert/strict"
import { mkdtemp, rm } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"
import { FakeRuntimeAdapter, waitFor } from "../helpers/fake-runtime.ts"
import { DEFAULT_SESSION_IDLE_TIMEOUT_MS, SessionRegistry } from "../../src/pi/session-registry.ts"

test("default session idle timeout is ten minutes", () => {
  assert.equal(DEFAULT_SESSION_IDLE_TIMEOUT_MS, 10 * 60 * 1000)
})

test("idle wrapper is released, JSONL/index retained, and the next prompt resumes it", async (context) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "next-trainer-idle-"))
  context.after(async () => {
    await rm(root, { recursive: true, force: true })
  })

  const runtime = new FakeRuntimeAdapter()
  const sessions = new SessionRegistry(runtime, { storageDir: path.join(root, "sessions"), idleTimeoutMs: 150 })

  const created = await sessions.create({ profileId: "profile-a", purpose: "idle-test" })
  const sessionId = created.sessionId
  const handle = runtime.sessions.get(sessionId)
  assert.ok(handle, "fake runtime should hold the session wrapper")

  // A completed prompt returns the session to idle and arms the release timer.
  const receipt = await sessions.submit(sessionId, { requestId: "r1", text: "hello", mode: "prompt" })
  assert.equal(receipt.accepted, true)
  await waitFor(() => sessions.snapshot(sessionId).activeRunId === null && sessions.snapshot(sessionId).state === "idle")
  assert.equal(handle.closed, false)

  // After the idle timeout the in-process wrapper is released while the
  // session remains addressable (idle) with its persisted file intact.
  await waitFor(() => handle.closed === true, 2000)
  const afterRelease = sessions.snapshot(sessionId)
  assert.equal(afterRelease.state, "idle")

  // The next prompt resumes the wrapper from the persisted session.
  const resumed = await sessions.submit(sessionId, { requestId: "r2", text: "again", mode: "prompt" })
  assert.equal(resumed.accepted, true)
  await waitFor(() => sessions.snapshot(sessionId).activeRunId === null && sessions.snapshot(sessionId).state === "idle")
  assert.equal(handle.prompts.length, 2)

  // History still works after release + resume.
  const history = await sessions.history(sessionId)
  assert.ok(history)
})

test("an active run is never released by the idle timer", async (context) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "next-trainer-idle-"))
  context.after(async () => {
    await rm(root, { recursive: true, force: true })
  })

  const runtime = new FakeRuntimeAdapter()
  const sessions = new SessionRegistry(runtime, { storageDir: path.join(root, "sessions"), idleTimeoutMs: 50 })
  const created = await sessions.create({ profileId: "profile-a", purpose: "busy-test" })
  const handle = runtime.sessions.get(created.sessionId)
  assert.ok(handle)
  handle.blockPrompts = true

  const receipt = await sessions.submit(created.sessionId, { requestId: "r1", text: "hold", mode: "prompt" })
  assert.equal(receipt.accepted, true)
  await new Promise((resolve) => setTimeout(resolve, 300))
  assert.equal(handle.closed, false, "a running session must not be released")
  handle.release()
  await waitFor(() => sessions.snapshot(created.sessionId).activeRunId === null)
})
