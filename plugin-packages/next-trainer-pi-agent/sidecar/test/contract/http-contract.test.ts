import assert from "node:assert/strict"
import test from "node:test"
import { makeTestServer, sidecarRequest } from "../helpers/fake-runtime.ts"

test("all routes require the sidecar bearer credential", async () => {
  const { handler } = makeTestServer()
  const response = await handler(sidecarRequest("/health", {}, { authorize: false }))
  assert.equal(response.status, 401)
  assert.deepEqual((await response.json()).error, {
    code: "SIDECAR_AUTH_REQUIRED",
    message: "A valid sidecar bearer credential is required.",
    retryable: false,
  })
})

test("health is operational before Provider setup and exposes locked versions", async () => {
  const { handler } = makeTestServer()
  const response = await handler(sidecarRequest("/health"))
  assert.equal(response.status, 200)
  const body = await response.json()
  assert.equal(body.data.status, "ok")
  assert.equal(body.data.sidecarVersion, "0.1.0")
  assert.equal(body.data.protocolVersion, "1")
  assert.equal(body.data.piVersion, "0.84.2")
  assert.equal(body.data.buildNode, "22.19.0")
  assert.equal(body.data.runtime.version, "1.4.0")
  assert.equal(body.data.providerConfigured, false)
  assert.equal(body.data.providerReady, false)
})

test("JSON mutation routes reject missing content type", async () => {
  const { handler } = makeTestServer()
  const response = await handler(sidecarRequest("/providers/deepseek", {
    method: "PUT",
    body: JSON.stringify({}),
  }))
  assert.equal(response.status, 415)
  assert.equal((await response.json()).error.code, "JSON_REQUIRED")
})

test("Provider status contract never echoes credentials", async () => {
  const { handler } = makeTestServer()
  const apiKey = "sk-contract-secret"
  const save = await handler(sidecarRequest("/providers/deepseek", { method: "PUT" }, { json: {
    providerId: "deepseek",
    modelId: "deepseek-v4-flash",
    endpoint: "https://api.deepseek.com/v1/chat/completions",
    apiKey,
  } }))
  assert.equal(save.status, 200)
  assert.equal((await save.clone().text()).includes(apiKey), false)

  const status = await handler(sidecarRequest("/providers/deepseek"))
  assert.equal(status.status, 200)
  const text = await status.text()
  assert.equal(text.includes(apiKey), false)
  assert.equal(text.includes("apiKey"), false)
})
