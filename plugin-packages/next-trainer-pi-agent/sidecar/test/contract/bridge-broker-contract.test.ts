import assert from "node:assert/strict"
import test from "node:test"
import { makeTestServer, sidecarRequest } from "../helpers/fake-runtime.ts"

const REQUEST_ID = "44444444-4444-4444-8444-444444444444"

function bridgeRequest(method: string, params: Record<string, unknown>, requestId = REQUEST_ID): Request {
  return sidecarRequest("/bridge/requests", { method: "POST" }, { json: { requestId, method, params } })
}

test("broker request endpoint uses the canonical envelope and never echoes Provider keys", async () => {
  const { handler } = makeTestServer()
  const key = "sk-bridge-contract-placeholder"
  const saved = await handler(bridgeRequest("provider.saveKey", {
    profileId: "bridge-profile",
    endpoint: "https://api.example.com/v1/chat/completions",
    modelId: "bridge-model",
    key,
  }))
  assert.equal(saved.status, 200)
  const savedText = await saved.text()
  assert.equal(savedText.includes(key), false)
  assert.deepEqual(Object.keys(JSON.parse(savedText)).sort(), ["data", "ok", "requestId"])
  assert.equal(JSON.parse(savedText).requestId, REQUEST_ID)

  const created = await handler(bridgeRequest("session.create", {
    model: { profileId: "bridge-profile", modelId: "bridge-model" },
    thinkingLevel: "auto",
  }))
  assert.equal(created.status, 200)
  const sessionId = (await created.json()).data.id as string
  const listed = await handler(bridgeRequest("session.list", {}))
  assert.equal((await listed.json()).data[0].id, sessionId)
})

test("broker rejects non-canonical request IDs and unknown methods with stable failures", async () => {
  const { handler } = makeTestServer()
  const invalidId = await handler(bridgeRequest("session.list", {}, "not-a-uuid"))
  assert.equal(invalidId.status, 400)
  assert.equal((await invalidId.json()).error.code, "BRIDGE_REQUEST_INVALID")

  const unknown = await handler(bridgeRequest("session.openArbitraryPath", { path: "C:\\sensitive" }))
  assert.equal(unknown.status, 404)
  const body = await unknown.json()
  assert.equal(body.requestId, REQUEST_ID)
  assert.equal(body.error.code, "BRIDGE_METHOD_NOT_FOUND")
})

test("broker stream endpoint emits only enveloped session subscription frames", async () => {
  const { handler } = makeTestServer()
  await handler(bridgeRequest("provider.saveKey", {
    profileId: "stream-profile",
    endpoint: "https://api.example.com/v1/chat/completions",
    modelId: "stream-model",
    key: "sk-stream-placeholder",
  }))
  const created = await handler(bridgeRequest("session.create", {
    model: { profileId: "stream-profile", modelId: "stream-model" },
  }))
  const sessionId = (await created.json()).data.id as string
  const streamRequest = sidecarRequest("/bridge/streams", { method: "POST" }, { json: {
    requestId: REQUEST_ID,
    method: "session.subscribe",
    params: { sessionId },
  } })
  const response = await handler(streamRequest)
  assert.equal(response.status, 200)
  const reader = response.body?.getReader()
  assert.ok(reader)
  const first = await reader.read()
  await reader.cancel()
  const frame = new TextDecoder().decode(first.value)
  assert.match(frame, /^data: /)
  const envelope = JSON.parse(frame.slice(6))
  assert.equal(envelope.ok, true)
  assert.equal(envelope.requestId, REQUEST_ID)
  assert.equal(envelope.data.type, "connected")
  assert.equal(typeof envelope.data.state.id, "string")
})

test("Bridge maps omitted model to the first configured profile and returns UI receipts", async () => {
  const { handler } = makeTestServer()
  await handler(bridgeRequest("provider.saveKey", { profileId: "dto-profile", endpoint: "https://api.example.com/v1/chat/completions", modelId: "dto-model", key: "sk-dto-placeholder" }))
  const created = await handler(bridgeRequest("session.create", { thinkingLevel: "auto" }))
  const state = (await created.json()).data
  assert.deepEqual(state.model, { profileId: "dto-profile", modelId: "dto-model" })
  assert.equal(state.status, "idle")
  const prompt = await handler(bridgeRequest("session.prompt", { sessionId: state.id, input: { text: "hello", clientSubmissionId: "client-1" } }))
  assert.deepEqual((await prompt.json()).data, { accepted: true, sessionId: state.id, runId: 1, clientSubmissionId: "client-1", disposition: "started" })
  const provider = (await (await handler(bridgeRequest("provider.list", {}))).json()).data[0]
  assert.deepEqual(provider.modelId, "dto-model")
  assert.deepEqual(provider.capabilities, ["text"])
})
