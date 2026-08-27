/**
 * Next Trainer Pi Agent — launcher (packaging glue only).
 *
 * Implements the host plugin-runtime contract (READY line + Bearer /health)
 * and supervises an unmodified pi-web server:
 *   - spawns  <package>/pi-web/bin/pi-web.js  via the bundled Node runtime
 *   - PI_CODING_AGENT_DIR is pinned to the plugin data root (config isolation)
 *   - parent (host) process liveness is monitored; on parent exit the pi-web
 *     process tree is removed
 *   - READY reports the host-contract port plus uiUrl/childPid extras so the
 *     host can project the live pi-web URL into the floating dialog
 *
 * No pi-web or pi source code is modified by this launcher.
 */
import { spawn, execSync } from "node:child_process"
import net from "node:net"
import path from "node:path"
import { appendFileSync, createWriteStream, mkdirSync } from "node:fs"
import type { WriteStream } from "node:fs"

const PROTOCOL_VERSION = "1"
const PLUGIN_VERSION = "0.2.0"

function fail(code: string, message: string): never {
  process.stderr.write(`[launcher] ${code}: ${message}\n`)
  process.exit(2)
}

function requiredEnv(env: NodeJS.ProcessEnv, name: string): string {
  const value = env[name]
  if (!value) fail("BOOTSTRAP_INVALID", `${name} is missing.`)
  return value
}

const dataRoot = path.resolve(requiredEnv(process.env, "NEXT_TRAINER_PLUGIN_DATA_ROOT"))
if (!path.isAbsolute(dataRoot)) fail("BOOTSTRAP_INVALID", "NEXT_TRAINER_PLUGIN_DATA_ROOT must be absolute.")
const sidecarToken = requiredEnv(process.env, "NEXT_TRAINER_SIDECAR_TOKEN")
if (sidecarToken.length < 32) fail("BOOTSTRAP_INVALID", "NEXT_TRAINER_SIDECAR_TOKEN is too short.")
const parentPid = Number(requiredEnv(process.env, "NEXT_TRAINER_PARENT_PID"))
if (!Number.isInteger(parentPid) || parentPid <= 0) fail("BOOTSTRAP_INVALID", "NEXT_TRAINER_PARENT_PID must be a positive integer.")
const requestedPort = Number(process.env.NEXT_TRAINER_SIDECAR_PORT ?? "0")
if (!Number.isInteger(requestedPort) || requestedPort < 0 || requestedPort > 65535) {
  fail("BOOTSTRAP_INVALID", "NEXT_TRAINER_SIDECAR_PORT must be an integer from 0 to 65535.")
}

const exeDir = path.dirname(process.execPath)
const packageRoot = path.resolve(exeDir, "..")
const nodeExe = path.join(packageRoot, "runtime", "node", "node.exe")
const piWebRoot = path.join(packageRoot, "pi-web")
const piWebEntry = path.join(piWebRoot, "bin", "pi-web.js")

function log(message: string): void {
  const line = `[${new Date().toISOString()}] ${message}\n`
  try {
    appendFileSync(logPath, line)
  } catch {
    /* logging must never crash the launcher */
  }
}

const agentDir = path.join(dataRoot, "pi-agent")
const homeDir = path.join(dataRoot, "home")
const logPath = path.join(dataRoot, "launcher.log")
mkdirSync(agentDir, { recursive: true })
mkdirSync(homeDir, { recursive: true })

let shuttingDown = false

function killTree(pid: number): void {
  if (process.platform === "win32") {
    try {
      execSync(`taskkill /F /T /PID ${pid}`, { stdio: "ignore" })
    } catch {
      /* process may already be gone */
    }
  } else {
    try {
      process.kill(-pid, "SIGKILL")
    } catch {
      try {
        process.kill(pid, "SIGKILL")
      } catch {
        /* already gone */
      }
    }
  }
}

let piWeb: ReturnType<typeof spawn> | null = null

function shutdown(reason: string): void {
  if (shuttingDown) return
  shuttingDown = true
  log(`shutdown: ${reason}`)
  if (piWeb && piWeb.exitCode === null && piWeb.signalCode === null) {
    killTree(piWeb.pid ?? -1)
  }
  process.exit(0)
}

function pickFreePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = net.createServer()
    server.unref()
    server.on("error", reject)
    server.listen(0, "127.0.0.1", () => {
      const address = server.address()
      const port = typeof address === "object" && address ? address.port : 0
      server.close(() => (port > 0 ? resolve(port) : reject(new Error("no free port"))))
    })
  })
}

async function waitForPiWeb(port: number, timeoutMs: number): Promise<void> {
  const deadline = Date.now() + timeoutMs
  let lastError = "no response"
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/`, { method: "GET" })
      // Any HTTP answer means the server process is serving; pi-web returns
      // 200 for "/" (or a redirect) once Next has booted.
      if (response.status > 0) {
        await response.body?.cancel().catch(() => {})
        return
      }
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error)
    }
    await new Promise((resolve) => setTimeout(resolve, 250))
  }
  throw new Error(`pi-web did not answer on 127.0.0.1:${port} within ${timeoutMs}ms (${lastError})`)
}

function startPiWeb(port: number): { pid: number } {
  const childEnv: NodeJS.ProcessEnv = {
    ...process.env,
    PI_CODING_AGENT_DIR: agentDir,
    PI_WEB_NO_OPEN: "1",
    // Contained home so homedir()-based pi-web features (~/pi-cwd-*, skill
    // discovery) stay inside the plugin data root.
    USERPROFILE: homeDir,
    HOME: homeDir,
    APPDATA: path.join(homeDir, "AppData", "Roaming"),
    LOCALAPPDATA: path.join(homeDir, "AppData", "Local"),
    TMP: path.join(dataRoot, "tmp"),
    TEMP: path.join(dataRoot, "tmp"),
  }
  mkdirSync(childEnv.TMP as string, { recursive: true })
  let outStream: WriteStream | null = null
  try {
    outStream = createWriteStream(path.join(dataRoot, "pi-web.log"), { flags: "a" })
  } catch {
    outStream = null
  }
  piWeb = spawn(
    nodeExe,
    [piWebEntry, "-H", "127.0.0.1", "-p", String(port), "--no-open"],
    {
      cwd: piWebRoot,
      env: childEnv,
      stdio: ["ignore", outStream ? "pipe" : "ignore", outStream ? "pipe" : "ignore"],
    },
  )
  if (outStream) {
    piWeb.stdout?.pipe(outStream)
    piWeb.stderr?.pipe(outStream)
  }
  piWeb.on("exit", (code, signal) => {
    log(`pi-web exited code=${String(code)} signal=${String(signal)}`)
    if (!shuttingDown) shutdown(`pi-web exited code=${String(code)} signal=${String(signal)}`)
  })
  if (!piWeb.pid) throw new Error("failed to spawn pi-web")
  return { pid: piWeb.pid }
}

async function main(): Promise<void> {
  // Host contract port (fixed by env; 0 means "pick a free one" via the
  // contract server listen below).
  const hostPort = requestedPort
  // pi-web port.
  const piWebPort = await pickFreePort()

  const child = startPiWeb(piWebPort)
  log(`pi-web spawned pid=${child.pid} port=${piWebPort}`)

  // Host-contract HTTP server (health only; the UI talks directly to pi-web).
  const server = await Bun.serve({
    hostname: "127.0.0.1",
    port: hostPort,
    idleTimeout: 60,
    async fetch(request: Request): Promise<Response> {
      const url = new URL(request.url)
      if (url.pathname !== "/health") {
        return Response.json(
          { ok: false, error: { code: "NOT_FOUND", message: "unknown path" } },
          { status: 404 },
        )
      }
      const authorization = request.headers.get("authorization") ?? ""
      const supplied = authorization.startsWith("Bearer ") ? authorization.slice(7) : ""
      if (!supplied || supplied.length < 32 || supplied !== sidecarToken) {
        return Response.json(
          { ok: false, error: { code: "UNAUTHORIZED", message: "invalid token" } },
          { status: 401 },
        )
      }
      const alive = piWeb !== null && piWeb.exitCode === null && piWeb.signalCode === null
      if (!alive) {
        return Response.json(
          { ok: true, data: { status: "crashed", protocolVersion: PROTOCOL_VERSION, version: PLUGIN_VERSION } },
          { status: 200 },
        )
      }
      return Response.json({
        ok: true,
        data: {
          status: "ok",
          protocolVersion: PROTOCOL_VERSION,
          version: PLUGIN_VERSION,
          runtime: "pi-web",
          piWebUrl: `http://127.0.0.1:${piWebPort}`,
        },
      })
    },
  })

  // Wait for pi-web to actually serve before announcing readiness, so the
  // host's immediate /health probe succeeds.
  await waitForPiWeb(piWebPort, 120_000)
  log(`pi-web ready on 127.0.0.1:${piWebPort}`)

  process.stdout.write(
    `${JSON.stringify({
      type: "READY",
      host: "127.0.0.1",
      port: server.port,
      protocolVersion: PROTOCOL_VERSION,
      version: PLUGIN_VERSION,
      uiUrl: `http://127.0.0.1:${piWebPort}`,
      piWebUrl: `http://127.0.0.1:${piWebPort}`,
      childPid: child.pid,
    })}\n`,
  )

  // Parent (host) liveness monitor: if the host process is gone, remove the
  // whole pi-web tree and exit.
  const parentAlive = (): boolean => {
    try {
      process.kill(parentPid, 0)
      return true
    } catch {
      return false
    }
  }
  const monitor = setInterval(() => {
    if (!parentAlive()) shutdown("host process exited")
  }, 1_000)
  monitor.unref?.()

  process.on("SIGINT", () => shutdown("SIGINT"))
  process.on("SIGTERM", () => shutdown("SIGTERM"))
}

main().catch((error) => {
  fail("LAUNCHER_FATAL", error instanceof Error ? error.message : String(error))
})
