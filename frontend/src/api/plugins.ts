import { apiData } from "./client"
import type { BridgeCapability } from "../extensions/pluginBridgeSchemas"

export type PluginHostExtensionState = "absent" | "disabled" | "starting" | "ready" | "runtime_error" | "provider_error" | "broken"

export interface PluginUiEntry {
  entryUrl: string
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

const HOST_URL_PREFIX = "/api/plugin-host/"
const PLUGIN_ID_PATTERN = /^[a-z0-9][a-z0-9._-]{0,127}$/i

export function isValidPluginId(value: string): boolean {
  return PLUGIN_ID_PATTERN.test(value)
}

export function isSafePluginHostUrl(value: string | undefined): value is string {
  if (!value || !value.startsWith(HOST_URL_PREFIX) || value.startsWith("//")) return false
  if (/%(?:2e|2f|5c)/i.test(value)) return false
  try {
    const base = typeof window === "undefined" ? "http://localhost" : window.location.origin
    const resolved = new URL(value, base)
    return resolved.origin === base && resolved.pathname.startsWith(HOST_URL_PREFIX)
  } catch {
    return false
  }
}

export const pluginsApi = {
  listExtensions: () => apiData<{ extensions: PluginHostExtension[] }>("/api/plugin-host/extensions"),
  getArtifact: (pluginId: string, artifactId: string) =>
    apiData<PluginArtifactProjection>(`/api/plugin-host/artifacts/${encodeURIComponent(pluginId)}/${encodeURIComponent(artifactId)}`),
}
