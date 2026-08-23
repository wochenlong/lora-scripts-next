import { randomUUID } from "node:crypto"
import { mkdir } from "node:fs/promises"
import path from "node:path"
import { parseBootstrap } from "./bootstrap.ts"
import { createImageResolver } from "./image-resources.ts"
import { startParentMonitor } from "./parent-monitor.ts"
import { createHostToolFactory } from "./host-tools.ts"
import { installProviderFetchPolicy } from "./provider-fetch-policy.ts"
import { ProviderRegistry } from "./pi/provider-registry.ts"
import { ProductionPiRuntimeAdapter } from "./pi/runtime-adapter.ts"
import { SessionRegistry } from "./pi/session-registry.ts"
import { createRequestHandler, startServer } from "./server.ts"

declare const Bun: {
  version: string
  serve: Parameters<typeof startServer>[0]["serve"]
}

const bootstrap = parseBootstrap()
await mkdir(bootstrap.pluginDataRoot, { recursive: true })

const agentDir = path.join(bootstrap.pluginDataRoot, "pi-agent")
// HTTP is accepted only for explicit loopback verifier runs.  Production
// Provider profiles remain HTTPS-only; this keeps the standalone verifier
// self-contained without weakening the deployed endpoint policy.
const providers = await ProviderRegistry.open(agentDir, {
  allowHttpLoopback: process.env.NEXT_TRAINER_ALLOW_HTTP_LOOPBACK === "1",
})
installProviderFetchPolicy(providers)
const customToolsFactory = bootstrap.hostToolBaseUrl
  ? createHostToolFactory({ baseUrl: bootstrap.hostToolBaseUrl, token: bootstrap.hostToolToken })
  : undefined
const piRuntime = new ProductionPiRuntimeAdapter({
  agentDir,
  providers,
  resolveImage: createImageResolver(agentDir),
  ...(customToolsFactory ? { customToolsFactory } : {}),
})
const sessions = new SessionRegistry(piRuntime, { storageDir: path.join(agentDir, "sessions") })
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

let shutdownPromise: Promise<void> | null = null
const shutdown = (): Promise<void> => {
  if (shutdownPromise) return shutdownPromise
  shutdownPromise = sessions.closeAll().finally(() => {
    server.stop(true)
  })
  return shutdownPromise
}

const parentMonitor = startParentMonitor(parentAlive, async () => {
  await shutdown()
  process.exit(0)
})

for (const signal of ["SIGINT", "SIGTERM"] as const) {
  process.on(signal, () => {
    parentMonitor.stop()
    void shutdown().finally(() => {
      process.exit(0)
    })
  })
}
