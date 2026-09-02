import { apiData } from "./client"
import type { BridgeCapability, BridgeRequestEnvelope } from "../extensions/pluginBridgeSchemas"

export type PluginHostExtensionState = "absent" | "disabled" | "starting" | "ready" | "runtime_error" | "provider_error" | "broken"

export interface PluginUiEntry {
  entryUrl: string
  /** "static" (default): host-served plugin file. "server": live loopback
   * server reported by the plugin runtime (e.g. the embedded pi-web). */
  mode?: "static" | "server"
}

export interface PluginUiContributions {
  floatingPanel?: PluginUiEntry
  settings?: PluginUiEntry
  artifactDetail?: boolean
}

export interface PluginHostExtension {
  pluginId: string
  displayName: string
  version?: string
  enabled: boolean
  state: PluginHostExtensionState
  capabilities: BridgeCapability[]
  ui: PluginUiContributions
  unreadCount?: number
  statusText?: string
}

export interface PluginArtifactProjection {
  pluginId: string
  artifactId: string
  title: string
  kind: string
  status: "available" | "renderer_unavailable" | "missing"
  summary?: string
  downloadUrl?: string
}

export type PluginConfirmationState = "pending" | "presented" | "approved" | "rejected" | "expired"
export type PluginConfirmationDecision = "approved" | "rejected"

export interface PluginConfirmationProjection {
  ticketId: string
  pluginId: string
  toolCallId: string
  state: PluginConfirmationState
  permission: string
  action: string
  title: string
  summary: string
  details: Record<string, unknown>
  artifactIds?: string[]
  createdAt: string
  expiresAt: string
  resolvedAt: string | null
}

export interface MarketplaceEntry {
  id: string
  name: string
  publisher_id: string
  description: string
  icon?: string | null
  latest_version: string
  channel: "stable" | "beta"
  host_compatibility: string
  platforms: string[]
  package_size: number
  permissions_summary: string[]
  license: string
  release_notes_url?: string | null
  package_url: string
  sha256: string
  signature: string
  signing_key_id: string
  published_at: string
}

export interface MarketplacePluginStatus {
  id: string
  state: "not_installed" | "installed" | "enabled" | "runtime_error" | "broken"
  active_version: string | null
  previous_version: string | null
  enabled: boolean
  installed_versions: string[]
  reason: string
  runtime_state: "stopped" | "starting" | "running" | "crashed" | null
  runtime_pid: number | null
  /** The install operation still running server-side for this plugin, if any.
   *  The marketplace page re-attaches its progress UI to this snapshot after a
   *  navigation or host reload (the operation lives in the host process, not
   *  in the component). */
  activeOperation?: MarketplaceInstallOperation | null
  /** P0-3 update availability, computed host-side against the latest catalog.
   *  All keys are always present; a cold/offline catalog keeps them at their
   *  honest "unknown" defaults (no invented updates). */
  update_available?: boolean
  latest_version?: string | null
  update_size_bytes?: number | null
  /** Permission summary delta of the newest version versus the granted set,
   *  so the update confirmation can demand re-approval of changed grants. */
  update_permissions_added?: string[] | null
  update_permissions_removed?: string[] | null
}

export type MarketplaceInstallState = "running" | "succeeded" | "failed" | "cancelled"
export type MarketplaceInstallPhase =
  | "acquiring"
  | "verifying"
  | "extracting"
  | "health_check"
  | "committing"
  | "done"

export interface MarketplaceInstallProgress {
  current: number
  total: number
  percent: number | null
}

export interface MarketplaceInstallOperation {
  operationId: string
  pluginId: string
  version: string
  state: MarketplaceInstallState
  phase: MarketplaceInstallPhase
  progress: MarketplaceInstallProgress
  errorCode: string | null
  errorMessage: string | null
  status: MarketplacePluginStatus | null
  startedAt: string
  finishedAt: string | null
}

interface PluginHostAuthority {
  runToken: string
  header: "X-NextTrainer-Run-Token"
}

interface BrokerResponse<T = unknown> {
  ok: boolean
  requestId: string
  data?: T
  error?: { code: string; message: string; retryable?: boolean }
}

export class PluginCapabilityError extends Error {
  constructor(
    public readonly code: string,
    message: string,
    public readonly retryable = false,
  ) {
    super(message)
    this.name = "PluginCapabilityError"
  }
}

const HOST_URL_PREFIX = "/api/plugin-host/"
const PLUGIN_ID_PATTERN = /^[a-z0-9][a-z0-9._-]{0,127}$/i
const ARTIFACT_ID_PATTERN = /^[a-z0-9][a-z0-9._:-]{0,255}$/i
const TICKET_ID_PATTERN = /^[a-z0-9_-]{1,256}$/i
let authority: PluginHostAuthority | null = null
let authorityRequest: Promise<PluginHostAuthority> | null = null

function requestId() {
  return globalThis.crypto.randomUUID()
}

async function pluginHostAuthority(): Promise<PluginHostAuthority> {
  if (authority) return authority
  if (!authorityRequest) {
    authorityRequest = apiData<PluginHostAuthority>("/api/plugin-host/bootstrap", { method: "POST", body: "{}" })
      .then((value) => {
        if (
          value.header !== "X-NextTrainer-Run-Token" ||
          typeof value.runToken !== "string" ||
          value.runToken.length < 16
        ) {
          throw new PluginCapabilityError("PLUGIN_AUTHORITY_INVALID", "Plugin host authority is unavailable.")
        }
        authority = value
        return value
      })
      .finally(() => {
        authorityRequest = null
      })
  }
  return authorityRequest
}

async function authorizedFetch(path: string, init: RequestInit, retryAuthority = true): Promise<Response> {
  const current = await pluginHostAuthority()
  const response = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      [current.header]: current.runToken,
      ...init.headers,
    },
  })
  if (response.status === 403 && retryAuthority) {
    authority = null
    return authorizedFetch(path, init, false)
  }
  return response
}

async function brokerResponse<T>(response: Response, expectedRequestId: string): Promise<T> {
  let payload: BrokerResponse<T>
  try {
    payload = (await response.json()) as BrokerResponse<T>
  } catch {
    throw new PluginCapabilityError("PLUGIN_CAPABILITY_FAILED", "The plugin capability request failed.")
  }
  if (payload.requestId !== expectedRequestId) {
    throw new PluginCapabilityError("PLUGIN_RESPONSE_MISMATCH", "The plugin capability response could not be correlated.")
  }
  if (!response.ok || !payload.ok) {
    throw new PluginCapabilityError(
      payload.error?.code || "PLUGIN_CAPABILITY_FAILED",
      payload.error?.message || "The plugin capability request failed.",
      payload.error?.retryable === true,
    )
  }
  return payload.data as T
}

async function hostData<T>(response: Response): Promise<T> {
  let payload: { status?: string; data?: T; detail?: { code?: string; message?: string } | string }
  try {
    payload = (await response.json()) as { status?: string; data?: T }
  } catch {
    throw new PluginCapabilityError("PLUGIN_HOST_RESPONSE_INVALID", "The plugin host returned an invalid response.")
  }
  if (!response.ok || payload.status !== "success" || payload.data === undefined) {
    // The host reports structured failures two ways: the `{status, error}`
    // envelope from successful-route handlers, and FastAPI's HTTPException
    // `{detail: {code, message}}` (e.g. the 409 install-in-progress). Surface
    // the real reason instead of the generic "request failed" text so the
    // user learns WHY the action did nothing.
    const detail = payload.detail
    const code =
      (typeof detail === "object" && detail?.code) ||
      "PLUGIN_HOST_REQUEST_FAILED"
    const message =
      (typeof detail === "object" && detail?.message) ||
      (typeof detail === "string" && detail) ||
      "The plugin host request failed."
    throw new PluginCapabilityError(code, message)
  }
  return payload.data
}

async function marketplaceMutation(
  pluginId: string,
  action: string,
  body: Record<string, unknown>,
): Promise<MarketplacePluginStatus> {
  if (!isValidPluginId(pluginId)) throw new PluginCapabilityError("PLUGIN_ID_INVALID", "Plugin identity is invalid.")
  const response = await authorizedFetch(
    `/api/marketplace/plugins/${encodeURIComponent(pluginId)}/${action}`,
    { method: "POST", body: JSON.stringify(body) },
  )
  return hostData<MarketplacePluginStatus>(response)
}

function installOperationPath(pluginId: string, operationId: string, suffix = "") {
  if (!isValidPluginId(pluginId)) throw new PluginCapabilityError("PLUGIN_ID_INVALID", "Plugin identity is invalid.")
  if (!/^[a-f0-9]{1,128}$/i.test(operationId)) {
    throw new PluginCapabilityError("PLUGIN_OPERATION_ID_INVALID", "The install operation id is invalid.")
  }
  return `/api/marketplace/plugins/${encodeURIComponent(pluginId)}/operations/${encodeURIComponent(operationId)}${suffix}`
}

async function streamInstallOperationImpl(
  pluginId: string,
  operationId: string,
  onSnapshot: (operation: MarketplaceInstallOperation) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await authorizedFetch(installOperationPath(pluginId, operationId, "/stream"), {
    method: "GET",
    signal,
  })
  if (!response.ok) {
    await hostData<never>(response)
    return
  }
  if (!response.body) return
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""
  let terminal = false

  const processFrames = (flush: boolean) => {
    // When the stream has closed, the tail of the buffer is a complete frame
    // (the server ends every frame with a blank line, but the final chunk may
    // carry the last frame together with EOF), so flush it unconditionally.
    const frames = buffer.split("\n\n")
    buffer = flush ? "" : (frames.pop() ?? "")
    for (const frame of frames) {
      const lines = frame.split("\n")
      const event = (lines.find((line) => line.startsWith("event:")) ?? "").slice(6).trim()
      const data = lines
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart())
        .join("\n")
      if (!data) continue
      try {
        const payload = JSON.parse(data) as { status?: string; data?: unknown }
        if (payload.status !== "success" || !payload.data || typeof payload.data !== "object") continue
        const snapshot = payload.data as MarketplaceInstallOperation
        if (!snapshot.operationId) continue
        if (event === "connected") continue
        onSnapshot(snapshot)
        if (snapshot.state !== "running") terminal = true
      } catch {
        // Skip malformed frames; the polling fallback recovers state.
      }
    }
  }

  while (!terminal) {
    const { done, value } = await reader.read()
    if (value) buffer = (buffer + decoder.decode(value, { stream: !done })).replace(/\r\n/g, "\n")
    processFrames(done)
    if (done) break
  }
}

function brokerBody(
  input: Pick<BridgeRequestEnvelope, "type" | "payload">,
  idFactory: () => string,
) {
  const id = idFactory()
  return {
    id,
    body: JSON.stringify({ requestId: id, method: input.type, params: input.payload }),
  }
}

async function parseSse(
  response: Response,
  expectedRequestId: string,
  onEvent: (event: unknown) => void,
): Promise<void> {
  if (!response.ok || !response.body) {
    await brokerResponse(response, expectedRequestId)
    return
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""

  const flushFrames = (final = false) => {
    buffer = buffer.replace(/\r\n/g, "\n")
    const frames = buffer.split("\n\n")
    buffer = final ? "" : (frames.pop() ?? "")
    for (const frame of frames) {
      const data = frame
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart())
        .join("\n")
      if (!data) continue
      let envelope: BrokerResponse
      try {
        envelope = JSON.parse(data) as BrokerResponse
      } catch {
        throw new PluginCapabilityError("PLUGIN_STREAM_INVALID", "The plugin event stream returned invalid data.", true)
      }
      if (envelope.requestId !== expectedRequestId) continue
      if (!envelope.ok) {
        throw new PluginCapabilityError(
          envelope.error?.code || "PLUGIN_STREAM_FAILED",
          envelope.error?.message || "The plugin event stream failed.",
          envelope.error?.retryable === true,
        )
      }
      onEvent(envelope.data)
    }
  }

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    flushFrames()
  }
  buffer += decoder.decode()
  if (buffer.trim()) buffer += "\n\n"
  flushFrames(true)
}

export function resetPluginHostAuthorityForTests() {
  authority = null
  authorityRequest = null
}

export function isValidPluginId(value: string): boolean {
  return PLUGIN_ID_PATTERN.test(value)
}

export function isValidArtifactId(value: string): boolean {
  return ARTIFACT_ID_PATTERN.test(value)
}

export function isPluginConfirmationProjection(value: unknown, pluginId?: string): value is PluginConfirmationProjection {
  if (value === null || typeof value !== "object" || Array.isArray(value)) return false
  const projection = value as Record<string, unknown>
  return (
    typeof projection.ticketId === "string" &&
    TICKET_ID_PATTERN.test(projection.ticketId) &&
    typeof projection.pluginId === "string" &&
    isValidPluginId(projection.pluginId) &&
    (pluginId === undefined || projection.pluginId === pluginId) &&
    typeof projection.toolCallId === "string" &&
    projection.toolCallId.trim().length > 0 &&
    ["pending", "presented", "approved", "rejected", "expired"].includes(String(projection.state)) &&
    typeof projection.permission === "string" &&
    projection.permission.trim().length > 0 &&
    typeof projection.action === "string" &&
    projection.action.trim().length > 0 &&
    typeof projection.title === "string" &&
    projection.title.trim().length > 0 &&
    typeof projection.summary === "string" &&
    projection.details !== null &&
    typeof projection.details === "object" &&
    !Array.isArray(projection.details) &&
    (projection.artifactIds === undefined ||
      (Array.isArray(projection.artifactIds) &&
        new Set(projection.artifactIds).size === projection.artifactIds.length &&
        projection.artifactIds.every((id) => typeof id === "string" && isValidArtifactId(id)))) &&
    typeof projection.createdAt === "string" &&
    Number.isFinite(Date.parse(projection.createdAt)) &&
    typeof projection.expiresAt === "string" &&
    Number.isFinite(Date.parse(projection.expiresAt)) &&
    (projection.resolvedAt === null ||
      (typeof projection.resolvedAt === "string" && Number.isFinite(Date.parse(projection.resolvedAt))))
  )
}

export function isSafePluginHostUrl(value: string | undefined): value is string {
  if (!value || !value.startsWith(HOST_URL_PREFIX) || value.startsWith("//") || value.includes("\\")) return false
  if (/%(?:2e|2f|5c)/i.test(value)) return false
  try {
    const base = typeof window === "undefined" ? "http://localhost" : window.location.origin
    const resolved = new URL(value, base)
    return resolved.origin === base && resolved.pathname.startsWith(HOST_URL_PREFIX)
  } catch {
    return false
  }
}

export function isSafePluginUiUrl(value: string | undefined, pluginId: string): value is string {
  if (!isValidPluginId(pluginId) || !isSafePluginHostUrl(value)) return false
  const base = typeof window === "undefined" ? "http://localhost" : window.location.origin
  const resolved = new URL(value, base)
  const prefix = `/api/plugin-host/ui/${pluginId}/`
  return resolved.pathname.startsWith(prefix)
}

/**
 * A server-mode UI URL may carry exactly one query parameter, `cwd`, whose
 * value is an absolute filesystem path (Windows drive / UNC or POSIX). This is
 * the default-workspace hint pi-web reads via `getInitialNavigation`; the
 * pi-web still validates it against its own file-access policy. Anything else
 * (extra params, relative paths, traversal, embedded control chars) is refused.
 */
function isSafeCwdQuery(url: URL): boolean {
  if (url.search === "") return true
  if (url.searchParams.size !== 1 || !url.searchParams.has("cwd")) return false
  const cwd = url.searchParams.get("cwd") ?? ""
  if (!cwd) return false
  if (cwd.includes("://")) return false
  if (/[\r\n\t]/.test(cwd)) return false
  const windowsAbsolute = /^[A-Za-z]:[\\/]/.test(cwd) || cwd.startsWith("\\\\")
  const posixAbsolute = cwd.startsWith("/")
  if (!windowsAbsolute && !posixAbsolute) return false
  return !cwd.split(/[\\/]/).includes("..")
}

/**
 * Server-mode UI URLs are reported by the plugin runtime (READY line) and
 * validated by the host before projection.  The frontend re-validates: only
 * an explicit `http://127.0.0.1:<port>` root document is loadable in the
 * floating dialog.  A single `cwd` query param (the default workspace) is
 * permitted.  No other hosts, paths, credentials, or schemes pass.
 */
export function isSafePluginServerUiUrl(value: string | undefined): value is string {
  if (!value) return false
  try {
    const url = new URL(value)
    const port = Number(url.port)
    return (
      url.protocol === "http:" &&
      url.hostname === "127.0.0.1" &&
      url.port !== "" &&
      Number.isInteger(port) &&
      port >= 1 &&
      port <= 65535 &&
      url.username === "" &&
      url.password === "" &&
      // Root document only (trailing slash included): no path or hash; at most
      // a single validated `cwd` query param.
      url.pathname === "/" &&
      isSafeCwdQuery(url) &&
      url.hash === ""
    )
  } catch {
    return false
  }
}

export const pluginsApi = {
  ensureHostAuthority: async (): Promise<void> => {
    await pluginHostAuthority()
  },
  listExtensions: () => apiData<{ extensions: PluginHostExtension[] }>("/api/plugin-host/extensions"),
  getArtifact: (pluginId: string, artifactId: string) => {
    if (!isValidPluginId(pluginId) || !isValidArtifactId(artifactId)) {
      return Promise.reject(new Error("Invalid plugin artifact identity."))
    }
    return apiData<PluginArtifactProjection>(
      `/api/plugin-host/artifacts/${encodeURIComponent(pluginId)}/${encodeURIComponent(artifactId)}`,
    )
  },
  requestCapability: async <T = unknown>(
    pluginId: string,
    input: Pick<BridgeRequestEnvelope, "type" | "payload">,
    idFactory: () => string = requestId,
  ): Promise<T> => {
    if (!isValidPluginId(pluginId)) throw new PluginCapabilityError("PLUGIN_ID_INVALID", "Plugin identity is invalid.")
    const request = brokerBody(input, idFactory)
    const response = await authorizedFetch(`/api/plugin-host/extensions/${encodeURIComponent(pluginId)}/requests`, {
      method: "POST",
      body: request.body,
    })
    return brokerResponse<T>(response, request.id)
  },
  streamCapability: async (
    pluginId: string,
    input: Pick<BridgeRequestEnvelope, "type" | "payload">,
    onEvent: (event: unknown) => void,
    signal?: AbortSignal,
    idFactory: () => string = requestId,
  ): Promise<void> => {
    if (!isValidPluginId(pluginId)) throw new PluginCapabilityError("PLUGIN_ID_INVALID", "Plugin identity is invalid.")
    const request = brokerBody(input, idFactory)
    const response = await authorizedFetch(`/api/plugin-host/extensions/${encodeURIComponent(pluginId)}/streams`, {
      method: "POST",
      body: request.body,
      signal,
    })
    await parseSse(response, request.id, onEvent)
  },
  resolveConfirmation: async (
    ticketId: string,
    decision: PluginConfirmationDecision,
  ): Promise<PluginConfirmationProjection> => {
    if (!TICKET_ID_PATTERN.test(ticketId)) {
      throw new PluginCapabilityError("CONFIRMATION_TICKET_INVALID", "The confirmation ticket is invalid.")
    }
    const response = await authorizedFetch(
      `/api/plugin-host/confirmations/${encodeURIComponent(ticketId)}/resolve`,
      { method: "POST", body: JSON.stringify({ decision }) },
    )
    const projection = await hostData<PluginConfirmationProjection>(response)
    if (!isPluginConfirmationProjection(projection)) {
      throw new PluginCapabilityError("CONFIRMATION_RESPONSE_INVALID", "The confirmation response is invalid.")
    }
    return projection
  },
  listPendingConfirmations: async (): Promise<PluginConfirmationProjection[]> => {
    const response = await authorizedFetch("/api/plugin-host/confirmations/pending", { method: "GET" })
    const result = await hostData<{ confirmations: unknown[] }>(response)
    return result.confirmations.filter((value): value is PluginConfirmationProjection => isPluginConfirmationProjection(value))
  },
  listMarketplacePlugins: async (): Promise<MarketplacePluginStatus[]> => {
    const response = await authorizedFetch("/api/marketplace/plugins", { method: "GET" })
    return hostData<MarketplacePluginStatus[]>(response)
  },
  listMarketplaceCatalog: async (): Promise<MarketplaceEntry[]> => {
    const response = await authorizedFetch("/api/marketplace/catalog", { method: "GET" })
    const data = await hostData<MarketplaceEntry[] | null>(response)
    return data ?? []
  },
  // GET /catalog only reads the on-disk cache; a fresh host that has never
  // polled its channel returns MARKETPLACE_CATALOG_OFFLINE (503). This forces
  // the host to poll its configured channel once, then the next list succeeds.
  refreshMarketplaceCatalog: async (): Promise<number> => {
    const response = await authorizedFetch("/api/marketplace/catalog/refresh", { method: "POST", body: "{}" })
    const data = await hostData<{ entries?: number }>(response)
    return data?.entries ?? 0
  },
  // The backend install contract is strict (extra="forbid"): only version /
  // approvedPermissions are accepted. The catalog entry is server-trusted
  // (signature verified) and must not be echoed back in the request body.
  // Install is asynchronous: the endpoint returns 202 with the operation
  // snapshot; follow it via getInstallOperation / streamInstallOperation.
  installMarketplacePlugin: async (entry: MarketplaceEntry, approvedPermissions: string[]) => {
    if (!isValidPluginId(entry.id)) throw new PluginCapabilityError("PLUGIN_ID_INVALID", "Plugin identity is invalid.")
    const response = await authorizedFetch(`/api/marketplace/plugins/${encodeURIComponent(entry.id)}/install`, {
      method: "POST",
      body: JSON.stringify({ approvedPermissions }),
    })
    return hostData<MarketplaceInstallOperation>(response)
  },
  getInstallOperation: async (pluginId: string, operationId: string) =>
    hostData<MarketplaceInstallOperation>(
      await authorizedFetch(installOperationPath(pluginId, operationId), { method: "GET" }),
    ),
  cancelInstallOperation: async (pluginId: string, operationId: string) =>
    hostData<MarketplaceInstallOperation>(
      await authorizedFetch(installOperationPath(pluginId, operationId), { method: "DELETE", body: "{}" }),
    ),
  streamInstallOperation: (
    pluginId: string,
    operationId: string,
    onSnapshot: (operation: MarketplaceInstallOperation) => void,
    signal?: AbortSignal,
  ) => streamInstallOperationImpl(pluginId, operationId, onSnapshot, signal),
  enableMarketplacePlugin: (pluginId: string, permissions: string[]) =>
    marketplaceMutation(pluginId, "enable", { permissions }),
  disableMarketplacePlugin: (pluginId: string) => marketplaceMutation(pluginId, "disable", {}),
  restartMarketplacePlugin: (pluginId: string) => marketplaceMutation(pluginId, "restart", {}),
  rollbackMarketplacePlugin: (pluginId: string, version?: string) =>
    marketplaceMutation(pluginId, "rollback", { version: version ?? null }),
  uninstallMarketplacePlugin: (pluginId: string) => marketplaceMutation(pluginId, "uninstall", {}),
}
