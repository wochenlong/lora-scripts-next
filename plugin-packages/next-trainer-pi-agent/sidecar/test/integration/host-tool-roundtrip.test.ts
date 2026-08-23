import assert from "node:assert/strict"
import { mkdtemp, rm } from "node:fs/promises"
import { createServer, type IncomingMessage, type ServerResponse } from "node:http"
import os from "node:os"
import path from "node:path"
import test from "node:test"
import { createHostToolFactory } from "../../src/host-tools.ts"
import { ProviderRegistry } from "../../src/pi/provider-registry.ts"
import { ProductionPiRuntimeAdapter } from "../../src/pi/runtime-adapter.ts"
import { installProviderFetchPolicy } from "../../src/provider-fetch-policy.ts"

async function bodyOf(request: IncomingMessage): Promise<Record<string, unknown>> {
  const chunks: Buffer[] = []
  for await (const chunk of request) chunks.push(Buffer.from(chunk))
  return JSON.parse(Buffer.concat(chunks).toString("utf8")) as Record<string, unknown>
}

function streamChunks(response: ServerResponse, chunks: Record<string, unknown>[]): void {
  response.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" })
  for (const chunk of chunks) response.write(`data: ${JSON.stringify(chunk)}\n\n`)
  response.end("data: [DONE]\n\n")
}

type RequestListener = (request: IncomingMessage, response: ServerResponse) => void

async function listen(handler: RequestListener): Promise<{ baseUrl: string; close(): Promise<void> }> {
  const server = createServer(handler)
  await new Promise<void>((resolve, reject) => {
    server.once("error", reject)
    server.listen(0, "127.0.0.1", resolve)
  })
  const address = server.address()
  if (!address || typeof address === "string") throw new Error("Server did not bind")
  return {
    baseUrl: `http://127.0.0.1:${address.port}`,
    close: () => new Promise<void>((resolve, reject) => server.close((error) => error ? reject(error) : resolve())),
  }
}

test("real Pi Tool call is schema-bound and executes only through the authenticated Host gateway", async (context) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "next-trainer-host-tool-"))
  const hostToken = "host-tool-token-at-least-32-characters"
  const hostCalls: Array<{ authorization: string | undefined; sessionId: string | undefined; body: Record<string, unknown> }> = []
  const host = await listen(async (request: IncomingMessage, response: ServerResponse) => {
    if (request.url === "/internal/agent-tools/definitions") {
      response.setHeader("content-type", "application/json")
      response.end(JSON.stringify({ ok: true, data: { tools: [{
        name: "host_echo",
        label: "Host Echo",
        description: "Echo a value through the Host capability gateway.",
        parameters: { type: "object", properties: { value: { type: "string" } }, required: ["value"], additionalProperties: false },
      }] } }))
      return
    }
    if (request.url === "/internal/agent-tools/host_echo" && request.method === "POST") {
      hostCalls.push({
        authorization: request.headers.authorization,
        sessionId: request.headers["x-next-trainer-session-id"] as string | undefined,
        body: await bodyOf(request),
      })
      response.setHeader("content-type", "application/json")
      response.end(JSON.stringify({ ok: true, data: { echoed: "from-model" }, audit_id: "audit-test" }))
      return
    }
    response.writeHead(404).end()
  })

  let providerCalls = 0
  const provider = await listen(async (request: IncomingMessage, response: ServerResponse) => {
    const body = await bodyOf(request)
    providerCalls += 1
    const base = { id: `chatcmpl-${providerCalls}`, object: "chat.completion.chunk", created: 1, model: "tool-model" }
    if (providerCalls === 1) {
      streamChunks(response, [
        { ...base, choices: [{ index: 0, delta: { role: "assistant", content: "" }, finish_reason: null }] },
        { ...base, choices: [{ index: 0, delta: { tool_calls: [{ index: 0, id: "call-1", type: "function", function: { name: "host_echo", arguments: "{\"value\":\"from-model\"}" } }] }, finish_reason: null }] },
        { ...base, choices: [{ index: 0, delta: {}, finish_reason: "tool_calls" }], usage: { prompt_tokens: 10, completion_tokens: 5, total_tokens: 15 } },
      ])
    } else {
      assert.ok(Array.isArray(body.messages) && body.messages.some((message) => (message as { role?: string }).role === "tool"))
      streamChunks(response, [
        { ...base, choices: [{ index: 0, delta: { role: "assistant", content: "Host Tool completed." }, finish_reason: null }] },
        { ...base, choices: [{ index: 0, delta: {}, finish_reason: "stop" }], usage: { prompt_tokens: 20, completion_tokens: 4, total_tokens: 24 } },
      ])
    }
  })
  context.after(async () => {
    await Promise.all([host.close(), provider.close()])
    await rm(root, { recursive: true, force: true })
  })

  const registry = await ProviderRegistry.open(root, { allowHttpLoopback: true })
  await registry.save("tool-profile", {
    providerId: "tool-provider",
    modelId: "tool-model",
    endpoint: `${provider.baseUrl}/v1/chat/completions`,
    apiKey: "sk-fake-tool-provider",
  })
  const policy = installProviderFetchPolicy(registry)
  context.after(() => policy.restore())
  const runtime = new ProductionPiRuntimeAdapter({
    agentDir: root,
    providers: registry,
    customToolsFactory: createHostToolFactory({ baseUrl: host.baseUrl, token: hostToken }),
  })
  const sessionId = "22222222-2222-4222-8222-222222222222"
  const handle = await runtime.createSession(sessionId, { profileId: "tool-profile", purpose: "tool-roundtrip" })
  assert.deepEqual(handle.activeToolNames?.(), ["host_echo"])
  await handle.prompt({ text: "Use host_echo.", mode: "prompt", images: [], signal: new AbortController().signal })
  await handle.close()

  assert.equal(providerCalls, 2)
  assert.equal(hostCalls.length, 1)
  assert.equal(hostCalls[0]?.authorization, `Bearer ${hostToken}`)
  assert.equal(hostCalls[0]?.sessionId, sessionId)
  assert.deepEqual(hostCalls[0]?.body, { arguments: { value: "from-model" } })
})

test("actual Pi Provider request rejects redirects before the credential can reach another origin", async (context) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "next-trainer-redirect-"))
  let redirectTargetHits = 0
  const target = await listen((_request: IncomingMessage, response: ServerResponse) => {
    redirectTargetHits += 1
    response.writeHead(500).end()
  })
  const redirector = await listen((_request: IncomingMessage, response: ServerResponse) => {
    response.writeHead(307, { location: `${target.baseUrl}/v1/chat/completions` }).end()
  })
  context.after(async () => {
    await Promise.all([target.close(), redirector.close()])
    await rm(root, { recursive: true, force: true })
  })
  const registry = await ProviderRegistry.open(root, { allowHttpLoopback: true })
  await registry.save("redirect-profile", {
    providerId: "redirect-provider",
    modelId: "redirect-model",
    endpoint: `${redirector.baseUrl}/v1/chat/completions`,
    apiKey: "sk-must-not-follow-redirect",
  })
  const policy = installProviderFetchPolicy(registry)
  context.after(() => policy.restore())
  const runtime = new ProductionPiRuntimeAdapter({ agentDir: root, providers: registry })
  const handle = await runtime.createSession("33333333-3333-4333-8333-333333333333", {
    profileId: "redirect-profile",
    purpose: "redirect-test",
  })
  const stopReasons: unknown[] = []
  handle.subscribe((event) => {
    if (event.type === "message_end") stopReasons.push(event.payload?.stopReason)
  })
  await handle.prompt({ text: "test", mode: "prompt", images: [], signal: new AbortController().signal })
  await handle.close()
  assert.equal(redirectTargetHits, 0)
  assert.ok(stopReasons.includes("error"))
})
