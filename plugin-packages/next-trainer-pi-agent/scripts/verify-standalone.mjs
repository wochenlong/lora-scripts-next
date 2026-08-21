import assert from "node:assert/strict"
import { copyFile, mkdir, mkdtemp, readdir, rm } from "node:fs/promises"
import { spawn } from "node:child_process"
import { createInterface } from "node:readline"
import { tmpdir } from "node:os"
import path from "node:path"
import { fileURLToPath } from "node:url"

const packageRoot = path.resolve(fileURLToPath(new URL("..", import.meta.url)))
const sourceExe = path.join(packageRoot, "dist", "bin", "next-trainer-pi-sidecar.exe")
const temporaryRoot = await mkdtemp(path.join(tmpdir(), "next-trainer-sidecar-"))
const executableRoot = path.join(temporaryRoot, "executable-only")
const dataRoot = path.join(temporaryRoot, "data")
const executable = path.join(executableRoot, "next-trainer-pi-sidecar.exe")
const token = "isolated-sidecar-token-32-characters"
const hostToolToken = "isolated-host-tool-token-32-chars"

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
assert.deepEqual(await readdir(executableRoot), ["next-trainer-pi-sidecar.exe"])

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
  await rm(temporaryRoot, { recursive: true, force: true })
}
