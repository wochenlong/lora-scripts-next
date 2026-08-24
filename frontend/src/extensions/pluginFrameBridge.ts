import type { RouteLocationNormalizedLoaded, Router } from "vue-router"
import {
  isPluginConfirmationProjection,
  pluginsApi,
  type PluginConfirmationProjection,
  type PluginHostExtension,
} from "../api/plugins"
import { HostPluginBridge, type BridgeFrameTarget } from "./pluginBridge"
import {
  BRIDGE_REQUEST_TYPES,
  type BridgeCapability,
  type BridgeRequestEnvelope,
} from "./pluginBridgeSchemas"

export type PluginFramePlacement = "floating-panel" | "settings"

interface PluginFrameBridgeOptions {
  extension: PluginHostExtension
  placement: PluginFramePlacement
  instanceId: string
  frameTarget: BridgeFrameTarget
  router: Router
  route: RouteLocationNormalizedLoaded
  locale: () => string
  activeSession?: () => string | null
  onDiagnostic?: (message: string) => void
  onConfirmation?: (confirmation: PluginConfirmationProjection) => void
  requestCapability?: typeof pluginsApi.requestCapability
  streamCapability?: typeof pluginsApi.streamCapability
}

const requestTypeSet = new Set<string>(BRIDGE_REQUEST_TYPES)
const BASE_LOCAL_CAPABILITIES: readonly BridgeCapability[] = [
  "navigation.openExternal",
  "navigation.openPluginRoute",
  "theme.get",
  "locale.get",
  "context.get",
]
const SETTINGS_REMOTE_CAPABILITIES = new Set<BridgeCapability>([
  "provider.list",
  "provider.status",
  "provider.saveKey",
  "provider.removeKey",
  "provider.test",
])
const THEME_TOKEN_NAMES = [
  "--bg",
  "--surface",
  "--text",
  "--text-soft",
  "--border",
  "--accent",
  "--accent-contrast",
  "--danger",
  "--radius",
] as const

export function createPluginFrameInstanceId() {
  if (typeof globalThis.crypto.randomUUID === "function") return globalThis.crypto.randomUUID()
  const values = new Uint8Array(16)
  globalThis.crypto.getRandomValues(values)
  return Array.from(values, (value) => value.toString(16).padStart(2, "0")).join("")
}

function isBridgeCapability(value: string): value is BridgeCapability {
  return requestTypeSet.has(value)
}

export function bridgeCapabilitiesFor(extension: PluginHostExtension, placement: PluginFramePlacement): BridgeCapability[] {
  const local = [
    ...BASE_LOCAL_CAPABILITIES,
    ...(placement === "floating-panel" && extension.ui.artifactDetail ? (["artifact.open"] as const) : []),
  ]
  const remote = extension.capabilities.filter(
    (capability) => isBridgeCapability(capability) && (placement === "floating-panel" || SETTINGS_REMOTE_CAPABILITIES.has(capability)),
  )
  return [...new Set<BridgeCapability>([...local, ...remote])]
}

function themeTokens() {
  const styles = getComputedStyle(document.documentElement)
  return Object.fromEntries(THEME_TOKEN_NAMES.map((name) => [name, styles.getPropertyValue(name).trim()]))
}

function colorScheme(): "light" | "dark" {
  return document.documentElement.classList.contains("dark") ? "dark" : "light"
}

function safeExternalUrl(value: unknown) {
  if (typeof value !== "string") return null
  try {
    const url = new URL(value)
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) return null
    return url.href
  } catch {
    return null
  }
}

function isOwnedPluginRoute(pluginId: string, value: unknown): value is string {
  if (typeof value !== "string" || !value.startsWith("/")) return false
  const encoded = encodeURIComponent(pluginId)
  return value === `/settings/plugins/${encoded}` || value.startsWith(`/plugins/${encoded}/`)
}

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError"
}

export function createPluginFrameBridge(options: PluginFrameBridgeOptions): HostPluginBridge {
  const streams = new Map<string, AbortController>()
  const requestCapability = options.requestCapability ?? pluginsApi.requestCapability
  const streamCapability = options.streamCapability ?? pluginsApi.streamCapability
  let bridge: HostPluginBridge

  function closeStreams() {
    for (const controller of streams.values()) controller.abort()
    streams.clear()
  }

  async function handleRequest(request: BridgeRequestEnvelope) {
    if (request.type === "theme.get") return { tokens: themeTokens() }
    if (request.type === "locale.get") return { locale: options.locale() }
    if (request.type === "context.get") {
      return {
        route: options.route.path,
        locale: options.locale(),
        colorScheme: colorScheme(),
      }
    }
    if (request.type === "artifact.open") {
      await options.router.push({
        name: "plugin-artifact-detail",
        params: { pluginId: options.extension.pluginId, artifactId: String(request.payload.artifactId) },
      })
      return { opened: true }
    }
    if (request.type === "navigation.openPluginRoute") {
      const destination = request.payload.route
      if (!isOwnedPluginRoute(options.extension.pluginId, destination)) {
        throw new Error("Plugin route is outside this extension namespace.")
      }
      await options.router.push(destination)
      return { opened: true }
    }
    if (request.type === "navigation.openExternal") {
      const destination = safeExternalUrl(request.payload.url)
      if (!destination) throw new Error("External URL is not allowed.")
      window.open(destination, "_blank", "noopener,noreferrer")
      return { opened: true }
    }
    if (request.type === "session.subscribe") {
      const sessionId = String(request.payload.sessionId)
      streams.get(sessionId)?.abort()
      const controller = new AbortController()
      streams.set(sessionId, controller)
      void streamCapability(
        options.extension.pluginId,
        { type: request.type, payload: request.payload },
        (event) => bridge.postEvent(event),
        controller.signal,
      )
        .catch((error: unknown) => {
          if (!isAbortError(error)) options.onDiagnostic?.("Plugin event stream ended unexpectedly; details were withheld.")
        })
        .finally(() => {
          if (streams.get(sessionId) === controller) streams.delete(sessionId)
        })
      return { subscribed: true }
    }
    const result = await requestCapability(options.extension.pluginId, { type: request.type, payload: request.payload })
    if (
      request.type === "confirmation.request" &&
      isPluginConfirmationProjection(result, options.extension.pluginId) &&
      (result.state === "pending" || result.state === "presented")
    ) {
      options.onConfirmation?.(result)
    }
    return result
  }

  bridge = new HostPluginBridge({
    pluginId: options.extension.pluginId,
    instanceId: options.instanceId,
    frameTarget: options.frameTarget,
    grantedCapabilities: bridgeCapabilitiesFor(options.extension, options.placement),
    handleRequest,
    locale: options.locale,
    themeTokens,
    colorScheme,
    activeSession: options.activeSession,
    onDiagnostic: options.onDiagnostic,
    onConnectionClosed: closeStreams,
  })
  return bridge
}
