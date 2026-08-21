import assert from "node:assert/strict"
import { createServer } from "node:http"
import { mkdtemp, readdir, readFile, rm } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
import test from "node:test"
import { defineTool } from "@earendil-works/pi-coding-agent"
import { Type } from "typebox"
import { ProviderRegistry } from "../../src/pi/provider-registry.ts"
import { ProductionPiRuntimeAdapter } from "../../src/pi/runtime-adapter.ts"
import { installProviderFetchPolicy } from "../../src/provider-fetch-policy.ts"

async function startFakeChatProvider(): Promise<{
  endpoint: string
  close(): Promise<void>
  requests: Array<{ url: string; authorization: string | undefined; body: Record<string, unknown> }>
}> {
  const requests: Array<{ url: string; authorization: string | undefined; body: Record<string, unknown> }> = []
  const server = createServer((request, response) => {
    const chunks: Buffer[] = []
    request.on("data", (chunk: Buffer) => chunks.push(chunk))
    request.on("end", () => {
      requests.push({
        url: request.url ?? "",
        authorization: request.headers.authorization,
        body: JSON.parse(Buffer.concat(chunks).toString("utf8")) as Record<string, unknown>,
      })
      response.writeHead(200, {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        Connection: "keep-alive",
      })
      response.write(`data: ${JSON.stringify({
        id: "chatcmpl-test",
        object: "chat.completion.chunk",
        created: 1,
        model: "test-model",
        choices: [{ index: 0, delta: { role: "assistant", content: "" }, finish_reason: null }],
      })}\n\n`)
      response.write(`data: ${JSON.stringify({
        id: "chatcmpl-test",
        object: "chat.completion.chunk",
        created: 1,
        model: "test-model",
        choices: [{ index: 0, delta: { content: "real Pi adapter response" }, finish_reason: null }],
      })}\n\n`)
      response.write(`data: ${JSON.stringify({
        id: "chatcmpl-test",
        object: "chat.completion.chunk",
        created: 1,
        model: "test-model",
        choices: [{ index: 0, delta: {}, finish_reason: "stop" }],
        usage: { prompt_tokens: 8, completion_tokens: 4, total_tokens: 12 },
      })}\n\n`)
      response.end("data: [DONE]\n\n")
    })
  })
  await new Promise<void>((resolve, reject) => {
    server.once("error", reject)
    server.listen(0, "127.0.0.1", resolve)
  })
  const address = server.address()
  if (!address || typeof address === "string") throw new Error("Fake Provider did not bind a TCP port")
  return {
    endpoint: `http://127.0.0.1:${address.port}/v1/chat/completions`,
    requests,
    close: () => new Promise<void>((resolve, reject) => server.close((error) => error ? reject(error) : resolve())),
  }
}

test("production adapter uses Pi 0.84.2, persistent JSONL, and Host custom Tools only", async (context) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "next-trainer-real-pi-"))
  const provider = await startFakeChatProvider()
  context.after(async () => {
    await provider.close()
    await rm(root, { recursive: true, force: true })
  })

  const registry = await ProviderRegistry.open(root, { allowHttpLoopback: true })
  await registry.save("test-profile", {
    providerId: "test-provider",
    modelId: "test-model",
    endpoint: provider.endpoint,
    apiKey: "sk-fake-provider-key",
  })
  const fetchPolicy = installProviderFetchPolicy(registry)
  context.after(() => fetchPolicy.restore())
  const hostTool = defineTool({
    name: "host_echo",
    label: "Host Echo",
    description: "A test-only Host custom Tool.",
    parameters: Type.Object({ value: Type.String() }),
    execute: async (_toolCallId, params) => ({
      content: [{ type: "text", text: params.value }],
      details: {},
    }),
  })
  const runtime = new ProductionPiRuntimeAdapter({ agentDir: root, providers: registry, customTools: [hostTool] })
  const handle = await runtime.createSession("11111111-1111-4111-8111-111111111111", {
    profileId: "test-profile",
    purpose: "isolated-runtime-test",
    thinkingLevel: "auto",
  })
  assert.deepEqual(handle.activeToolNames?.(), ["host_echo"])

  const events: string[] = []
  const unsubscribe = handle.subscribe((event) => events.push(event.type))
  await handle.prompt({
    text: "Reply briefly.",
    mode: "prompt",
    images: [],
    signal: new AbortController().signal,
  })
  unsubscribe()
  await handle.close()

  assert.equal(provider.requests.length, 1)
  assert.equal(provider.requests[0]?.url, "/v1/chat/completions")
  assert.equal(provider.requests[0]?.authorization, "Bearer sk-fake-provider-key")
  assert.deepEqual((provider.requests[0]?.body.tools as Array<{ function: { name: string } }>).map((tool) => tool.function.name), ["host_echo"])
  assert.ok(events.includes("message_end"))
  assert.ok(events.includes("agent_settled"))
  const sessionFiles = await readdir(path.join(root, "sessions"))
  assert.equal(sessionFiles.length, 1)
  const jsonl = await readFile(path.join(root, "sessions", sessionFiles[0]!), "utf8")
  assert.match(jsonl, /real Pi adapter response/)
  assert.equal(jsonl.includes("sk-fake-provider-key"), false)
})
