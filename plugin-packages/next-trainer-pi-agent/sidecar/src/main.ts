import { randomUUID } from "node:crypto"
import { mkdir } from "node:fs/promises"
import { parseBootstrap } from "./bootstrap.ts"
import { ProviderRegistry } from "./pi/provider-registry.ts"
import { UnavailablePiRuntimeAdapter } from "./pi/runtime-adapter.ts"
import { SessionRegistry } from "./pi/session-registry.ts"
import { createRequestHandler, startServer } from "./server.ts"

declare const Bun: {
  version: string
  serve: Parameters<typeof startServer>[0]["serve"]
}

const bootstrap = parseBootstrap()
await mkdir(bootstrap.pluginDataRoot, { recursive: true })

const piRuntime = new UnavailablePiRuntimeAdapter()
const providers = new ProviderRegistry()
const sessions = new SessionRegistry(piRuntime)
const instanceId = randomUUID()
const startedAt = new Date().toISOString()

const parentAlive = (): boolean => {
  try {
    process.kill(bootstrap.parentPid, 0)
    return true
  } catch {
    return false
  }
}

const handler = createRequestHandler({
  token: bootstrap.token,
  instanceId,
  parentPid: bootstrap.parentPid,
  parentAlive,
  runtimeName: "bun",
  runtimeVersion: Bun.version,
  providers,
  sessions,
  piRuntime,
  startedAt,
})
const server = startServer(Bun, bootstrap.port, handler)

process.stdout.write(`${JSON.stringify({
  type: "READY",
  host: "127.0.0.1",
  port: server.port,
  instanceId,
  protocolVersion: "1",
})}\n`)

const parentMonitor = setInterval(() => {
  if (parentAlive()) return
  clearInterval(parentMonitor)
  void sessions.closeAll().finally(() => {
    server.stop(true)
    process.exit(0)
  })
}, 1_000)

for (const signal of ["SIGINT", "SIGTERM"] as const) {
  process.on(signal, () => {
    clearInterval(parentMonitor)
    void sessions.closeAll().finally(() => {
      server.stop(true)
      process.exit(0)
    })
  })
}
