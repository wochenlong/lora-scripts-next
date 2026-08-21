import assert from "node:assert/strict"
import test from "node:test"
import { makeTestServer, sidecarRequest, waitFor } from "../helpers/fake-runtime.ts"

async function configureProvider(handler: (request: Request) => Promise<Response>): Promise<void> {
  const response = await handler(sidecarRequest("/providers/deepseek", { method: "PUT" }, { json: {
    providerId: "deepseek",
    modelId: "deepseek-v4-flash",
    endpoint: "https://api.deepseek.com/v1/chat/completions",
    apiKey: "sk-integration-placeholder",
  } }))
  assert.equal(response.status, 200)
}

test("authenticated session create, SSE snapshot, prompt and terminal flow", async () => {
  const { handler } = makeTestServer()
  await configureProvider(handler)

  const create = await handler(sidecarRequest("/sessions", { method: "POST" }, { json: {
    profileId: "deepseek",
    purpose: "test-only",
  } }))
  assert.equal(create.status, 201)
  const sessionId = (await create.json()).data.sessionId as string

  const events = await handler(sidecarRequest(`/sessions/${sessionId}/events`))
  assert.equal(events.status, 200)
  assert.equal(events.headers.get("content-type"), "text/event-stream")
  const reader = events.body?.getReader()
  assert.ok(reader)

  const prompt = await handler(sidecarRequest(`/sessions/${sessionId}/prompts`, { method: "POST" }, { json: {
    requestId: "prompt-1",
    text: "hello",
  } }))
  assert.equal(prompt.status, 202)

  const decoder = new TextDecoder()
  let transcript = ""
  for (let index = 0; index < 9 && !transcript.includes("agent_settled"); index += 1) {
    const result = await reader.read()
    if (result.done) break
    transcript += decoder.decode(result.value)
  }
  await reader.cancel()
  assert.match(transcript, /event: connected/)
  assert.match(transcript, /event: snapshot/)
  assert.match(transcript, /prompt_started/)
  assert.match(transcript, /message_end/)
  assert.match(transcript, /prompt_done/)
  assert.match(transcript, /agent_settled/)

  const snapshot = await handler(sidecarRequest(`/sessions/${sessionId}`))
  assert.equal((await snapshot.json()).data.state, "idle")
})

test("cancel propagates to the active runtime prompt and settles as aborted", async () => {
  const { handler, runtime } = makeTestServer()
  await configureProvider(handler)
  const create = await handler(sidecarRequest("/sessions", { method: "POST" }, { json: {
    profileId: "deepseek",
    purpose: "cancel-test",
  } }))
  const sessionId = (await create.json()).data.sessionId as string
  const handle = runtime.sessions.get(sessionId)
  assert.ok(handle)
  handle.blockPrompts = true

  const prompt = await handler(sidecarRequest(`/sessions/${sessionId}/prompts`, { method: "POST" }, { json: {
    requestId: "prompt-cancel",
    text: "wait",
  } }))
  const runId = (await prompt.json()).data.runId as number
  await waitFor(() => handle.prompts.length === 1)

  const cancel = await handler(sidecarRequest(`/sessions/${sessionId}/cancel`, { method: "POST" }, { json: { runId } }))
  assert.equal((await cancel.json()).data.cancelled, true)
  await waitFor(() => handle.cancelled && handle.prompts[0]?.signal.aborted === true)
  let state = "cancelling"
  for (let index = 0; index < 50 && state !== "idle"; index += 1) {
    const snapshot = await handler(sidecarRequest(`/sessions/${sessionId}`))
    state = (await snapshot.json()).data.state as string
    if (state !== "idle") await new Promise((resolve) => setTimeout(resolve, 5))
  }
  assert.equal(state, "idle")
  assert.equal(handle.cancelled, true)
})

test("steer and followUp enter the active Pi run instead of a sidecar queue", async () => {
  const { handler, runtime } = makeTestServer()
  await configureProvider(handler)
  const create = await handler(sidecarRequest("/sessions", { method: "POST" }, { json: {
    profileId: "deepseek",
    purpose: "queue-test",
  } }))
  const sessionId = (await create.json()).data.sessionId as string
  const handle = runtime.sessions.get(sessionId)
  assert.ok(handle)
  handle.blockPrompts = true

  const first = await handler(sidecarRequest(`/sessions/${sessionId}/prompts`, { method: "POST" }, { json: {
    requestId: "prompt-active",
    text: "start",
  } }))
  const activeRunId = (await first.json()).data.runId as number
  await waitFor(() => handle.prompts.length === 1)

  for (const mode of ["steer", "followUp"] as const) {
    const queued = await handler(sidecarRequest(`/sessions/${sessionId}/prompts`, { method: "POST" }, { json: {
      requestId: `prompt-${mode}`,
      text: mode,
      mode,
    } }))
    assert.equal(queued.status, 202)
    assert.equal((await queued.json()).data.runId, activeRunId)
  }
  await waitFor(() => handle.prompts.length === 3)
  assert.deepEqual(handle.prompts.map((prompt) => prompt.mode), ["prompt", "steer", "followUp"])
  handle.release()
})
