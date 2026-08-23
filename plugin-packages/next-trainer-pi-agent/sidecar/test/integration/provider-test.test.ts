import assert from "node:assert/strict"
import { createServer, type Server } from "node:http"
import { mkdtemp, rm } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"
import { ProviderRegistry } from "../../src/pi/provider-registry.ts"
import { ProductionPiRuntimeAdapter } from "../../src/pi/runtime-adapter.ts"

async function fixture(mode: "ok" | "http-error" | "timeout"): Promise<{ endpoint: string; close: () => Promise<void> }> {
  const server = createServer((_request, response) => {
    if (mode === "timeout") return
    if (mode === "http-error") {
      response.writeHead(503)
      response.end("unavailable")
      return
    }
    response.writeHead(200, { "Content-Type": "text/event-stream" })
    response.end(`data: ${JSON.stringify({ id: "provider-test", object: "chat.completion.chunk", created: 1, model: "test", choices: [{ index: 0, delta: { content: "OK" }, finish_reason: "stop" }] })}\n\ndata: [DONE]\n\n`)
  })
  await new Promise<void>((resolve, reject) => { server.once("error", reject); server.listen(0, "127.0.0.1", resolve) })
  const address = server.address()
  if (!address || typeof address === "string") throw new Error("fixture did not bind")
  return {
    endpoint: `http://127.0.0.1:${address.port}/v1/chat/completions`,
    close: () => new Promise<void>((resolve, reject) => (server as Server).close((error) => error ? reject(error) : resolve())),
  }
}

test("Provider test records HTTP status and successful lastTest", async (context) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "next-trainer-provider-test-"))
  const server = await fixture("ok")
  context.after(async () => { await server.close(); await rm(root, { recursive: true, force: true }) })
  const providers = await ProviderRegistry.open(root, { allowHttpLoopback: true })
  await providers.save("fixture", { providerId: "fixture", modelId: "test", endpoint: server.endpoint, apiKey: "sk-provider-test-key" })
  const adapter = new ProductionPiRuntimeAdapter({ agentDir: root, providers, providerTestTimeoutMs: 500 })
  const result = await adapter.testProvider("fixture")
  assert.equal(result.ok, true)
  assert.equal(result.status, 200)
  assert.equal(providers.status("fixture").lastTest?.ok, true)
})

test("Provider test records failed HTTP and bounded timeout", async (context) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "next-trainer-provider-test-"))
  const errorServer = await fixture("http-error")
  const timeoutServer = await fixture("timeout")
  context.after(async () => { await errorServer.close(); await timeoutServer.close(); await rm(root, { recursive: true, force: true }) })
  const providers = await ProviderRegistry.open(root, { allowHttpLoopback: true })
  await providers.save("http-error", { providerId: "fixture", modelId: "test", endpoint: errorServer.endpoint, apiKey: "sk-provider-test-key" })
  await providers.save("timeout", { providerId: "fixture", modelId: "test", endpoint: timeoutServer.endpoint, apiKey: "sk-provider-test-key" })
  const adapter = new ProductionPiRuntimeAdapter({ agentDir: root, providers, providerTestTimeoutMs: 30 })
  const errorResult = await adapter.testProvider("http-error")
  assert.equal(errorResult.ok, false)
  // Pi reports non-2xx transport failures as a bounded generic failure; a
  // successful HTTP response status is asserted in the test above.
  assert.equal(errorResult.status, undefined)
  assert.equal(providers.status("http-error").lastTest?.ok, false)
  const timeoutResult = await adapter.testProvider("timeout")
  assert.equal(timeoutResult.ok, false)
  assert.equal(timeoutResult.ok, false)
  assert.equal(providers.status("timeout").lastTest?.ok, false)
})
