import assert from "node:assert/strict"
import { copyFile, mkdir, mkdtemp, readdir, rm } from "node:fs/promises"
import { createServer } from "node:http"
import { spawn } from "node:child_process"
import { createInterface } from "node:readline"
import { tmpdir } from "node:os"
import path from "node:path"
import { fileURLToPath } from "node:url"

const packageRoot = path.resolve(fileURLToPath(new URL("..", import.meta.url)))
const sourceExe = path.join(packageRoot, "dist", "bin", "next-trainer-pi-agent.exe")
const temporaryRoot = await mkdtemp(path.join(tmpdir(), "next-trainer-sidecar-"))
const executableRoot = path.join(temporaryRoot, "executable-only")
const dataRoot = path.join(temporaryRoot, "data")
const executable = path.join(executableRoot, "next-trainer-pi-agent.exe")
const token = "isolated-sidecar-token-32-characters"
const hostToolToken = "isolated-host-tool-token-32-chars"

function sseChunk(value) {
  return `data: ${JSON.stringify(value)}\n\n`
}

async function startFixtureServers() {
  let providerRequests = 0
  let hostToolCalls = 0
  const provider = createServer((request, response) => {
    const chunks = []
    request.on("data", (chunk) => chunks.push(chunk))
    request.on("end", () => {
      providerRequests += 1
      const body = JSON.parse(Buffer.concat(chunks).toString("utf8"))
      const hasToolResult = Array.isArray(body.messages) && body.messages.some((message) => message.role === "tool")
      response.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-cache", Connection: "keep-alive" })
      const base = { id: `standalone-${providerRequests}`, object: "chat.completion.chunk", created: 1, model: "standalone-model" }
      if (!hasToolResult) {
        response.write(sseChunk({ ...base, choices: [{ index: 0, delta: { role: "assistant", tool_calls: [{ index: 0, id: "standalone-call", type: "function", function: { name: "host_echo", arguments: '{"value":"standalone"}' } }] }, finish_reason: null }] }))
        response.write(sseChunk({ ...base, choices: [{ index: 0, delta: {}, finish_reason: "tool_calls" }], usage: { prompt_tokens: 4, completion_tokens: 3, total_tokens: 7 } }))
      } else {
        response.write(sseChunk({ ...base, choices: [{ index: 0, delta: { role: "assistant", content: "standalone provider complete" }, finish_reason: null }] }))
        response.write(sseChunk({ ...base, choices: [{ index: 0, delta: {}, finish_reason: "stop" }], usage: { prompt_tokens: 8, completion_tokens: 4, total_tokens: 12 } }))
      }
      response.end("data: [DONE]\n\n")
    })
  })
  const host = createServer((request, response) => {
    if (request.method === "GET" && request.url === "/internal/agent-tools/definitions") {
      response.writeHead(200, { "Content-Type": "application/json" })
      response.end(JSON.stringify({ ok: true, data: { tools: [{ name: "host_echo", label: "Host Echo", description: "Verifier Host Tool", parameters: { type: "object", properties: { value: { type: "string", minLength: 1 } }, required: ["value"], additionalProperties: false } }] } }))
      return
    }
    if (request.method === "POST" && request.url === "/internal/agent-tools/host_echo") {
      hostToolCalls += 1
      response.writeHead(200, { "Content-Type": "application/json" })
      response.end(JSON.stringify({ ok: true, data: "host echo: standalone", audit_id: "audit-standalone" }))
      return
    }
    response.writeHead(404)
    response.end()
  })
  await Promise.all([listen(provider), listen(host)])
  const providerAddress = provider.address()
  const hostAddress = host.address()
  if (!providerAddress || typeof providerAddress === "string" || !hostAddress || typeof hostAddress === "string") throw new Error("fixture server did not bind")
  return {
    providerEndpoint: `http://127.0.0.1:${providerAddress.port}/v1/chat/completions`,
    hostBaseUrl: `http://127.0.0.1:${hostAddress.port}`,
    get providerRequests() { return providerRequests },
    get hostToolCalls() { return hostToolCalls },
    close: () => Promise.all([close(provider), close(host)]),
  }
}

function listen(server) {
  return new Promise((resolve, reject) => {
    server.once("error", reject)
    server.listen(0, "127.0.0.1", resolve)
  })
}

function close(server) {
  return new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()))
}

async function withTimeout(promise, timeoutMs, message) {
  let timeout
  try {
    return await Promise.race([
      promise,
      new Promise((_, reject) => {
        timeout = setTimeout(() => reject(new Error(message)), timeoutMs)
      }),
    ])
  } finally {
    clearTimeout(timeout)
  }
}

await mkdir(executableRoot, { recursive: true })
await mkdir(dataRoot, { recursive: true })
await copyFile(sourceExe, executable)
assert.deepEqual(await readdir(executableRoot), ["next-trainer-pi-agent.exe"])
const fixtures = await startFixtureServers()

const windowsRoot = process.env.SystemRoot ?? "C:\\Windows"
const parentSentinel = spawn(process.execPath, ["-e", "setInterval(() => {}, 1000)"], {
  windowsHide: true,
  stdio: "ignore",
})
assert.ok(parentSentinel.pid)
const child = spawn(executable, [], {
  cwd: executableRoot,
  windowsHide: true,
  stdio: ["ignore", "pipe", "pipe"],
  env: {
    SystemRoot: windowsRoot,
    WINDIR: windowsRoot,
    PATH: `${windowsRoot}\\System32;${windowsRoot}`,
    NEXT_TRAINER_SIDECAR_TOKEN: token,
    NEXT_TRAINER_HOST_TOOL_TOKEN: hostToolToken,
    NEXT_TRAINER_HOST_TOOL_BASE_URL: fixtures.hostBaseUrl,
    NEXT_TRAINER_ALLOW_HTTP_LOOPBACK: "1",
    NEXT_TRAINER_PLUGIN_DATA_ROOT: dataRoot,
    NEXT_TRAINER_PARENT_PID: String(parentSentinel.pid),
    NEXT_TRAINER_SIDECAR_PORT: "0",
  },
})

let stderr = ""
child.stderr.setEncoding("utf8")
child.stderr.on("data", (chunk) => { stderr += chunk })

try {
  const lines = createInterface({ input: child.stdout })
  const ready = await withTimeout(
    new Promise((resolve, reject) => {
      lines.once("line", (line) => {
        try { resolve(JSON.parse(line)) } catch (error) { reject(error) }
      })
    }),
    15_000,
    `Sidecar READY timeout: ${stderr}`,
  )
  assert.equal(ready.type, "READY")
  assert.equal(ready.host, "127.0.0.1")
  assert.equal(ready.protocolVersion, "1")
  assert.equal(Number.isInteger(ready.port) && ready.port > 0, true)

  const healthUrl = `http://127.0.0.1:${ready.port}/health`
  const unauthorized = await fetch(healthUrl)
  assert.equal(unauthorized.status, 401)
  const health = await fetch(healthUrl, { headers: { authorization: `Bearer ${token}` } })
  assert.equal(health.status, 200)
  const healthText = await health.text()
  assert.equal(healthText.includes(token), false)
  const healthBody = JSON.parse(healthText)
  assert.equal(healthBody.data.runtime.name, "bun")
  assert.equal(healthBody.data.runtime.version, "1.4.0")
  assert.equal(healthBody.data.piVersion, "0.84.2")
  assert.equal(healthBody.data.piRuntimeReady, true)
  const provider = await fetch(`http://127.0.0.1:${ready.port}/providers/standalone`, {
    method: "PUT",
    headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
    body: JSON.stringify({ providerId: "fixture", modelId: "standalone-model", endpoint: fixtures.providerEndpoint, apiKey: "sk-standalone-fixture-key" }),
  })
  assert.equal(provider.status, 200)
  const session = await fetch(`http://127.0.0.1:${ready.port}/sessions`, {
    method: "POST",
    headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
    body: JSON.stringify({ profileId: "standalone", purpose: "standalone-verifier" }),
  })
  const sessionText = await session.text()
  assert.equal(session.status, 201, sessionText)
  const sessionId = JSON.parse(sessionText).data.sessionId
  const events = await fetch(`http://127.0.0.1:${ready.port}/sessions/${sessionId}/events`, { headers: { authorization: `Bearer ${token}` } })
  const prompt = await fetch(`http://127.0.0.1:${ready.port}/sessions/${sessionId}/prompts`, {
    method: "POST",
    headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
    body: JSON.stringify({ requestId: "11111111-1111-4111-8111-111111111111", text: "Use host_echo then finish." }),
  })
  assert.equal(prompt.status, 202)
  const eventReader = events.body.getReader()
  const eventDecoder = new TextDecoder()
  let eventText = ""
  for (let index = 0; index < 100 && !eventText.includes('"type":"agent_settled"'); index += 1) {
    const next = await withTimeout(eventReader.read(), 10_000, "standalone event stream timeout")
    if (next.done) break
    eventText += eventDecoder.decode(next.value, { stream: true })
  }
  await eventReader.cancel()
  assert.match(eventText, /agent_settled/)
  assert.ok(fixtures.providerRequests >= 2)
  assert.equal(fixtures.hostToolCalls, 1)
  parentSentinel.kill()
  const exitCode = await withTimeout(
    new Promise((resolve) => child.once("exit", resolve)),
    5_000,
    "Sidecar did not exit after parent death.",
  )
  assert.equal(exitCode, 0)
  process.stdout.write(`${JSON.stringify({
    isolatedExecutableFiles: 1,
    health: "pass",
    parentMonitor: "pass",
    runtime: "bun-1.4.0",
  })}\n`)
} finally {
  if (parentSentinel.exitCode === null) parentSentinel.kill()
  if (child.exitCode === null) {
    child.kill()
    await new Promise((resolve) => child.once("exit", resolve))
  }
  await fixtures.close()
  await rm(temporaryRoot, { recursive: true, force: true })
}
