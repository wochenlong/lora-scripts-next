import { apiData } from "./client"

export interface LlmProfile {
  id: string
  name: string
  endpoint: string
  model: string
  source: "remote" | "local-endpoint" | "managed-local"
  capabilities: string[]
  languages: string[]
  api_key: string
  api_key_configured?: boolean
  asset_id?: string | null
  revision?: string | null
  enabled: boolean
  ready: boolean
  metadata?: Record<string, unknown>
}

export interface LlmConfig {
  version: number
  profiles: LlmProfile[]
  routes: Record<string, string>
  prompt_presets: Array<{ id?: string; name?: string; template?: string; language?: string }>
  cache: { translation?: boolean; caption?: boolean }
}

export interface LocalVisionStatus {
  state: string
  installed: boolean
  runtime_installed?: boolean
  downloaded_bytes: number
  total_bytes: number
  error?: string | null
  estimated_peak_rss_bytes?: number
}

export const llmApi = {
  profiles: () => apiData<LlmConfig>("/api/llm/profiles"),
  config: () => apiData<LlmConfig>("/api/llm/config"),
  saveConfig: (body: Partial<LlmConfig>) => apiData<LlmConfig>("/api/llm/config", { method: "PUT", body: JSON.stringify(body) }),
  connectionTest: (body: { capability: "text" | "vision"; profile_id?: string; image_path?: string; prompt?: string; language?: string }) =>
    apiData<Record<string, unknown>>("/api/llm/connection-test", { method: "POST", body: JSON.stringify(body) }),
  localVisionManifest: () => apiData<Record<string, unknown>>("/api/llm/local-vision/manifest"),
  localVisionStatus: () => apiData<LocalVisionStatus>("/api/llm/local-vision/status"),
  localVisionAction: (action: "setup" | "start" | "stop" | "cancel") =>
    apiData<LocalVisionStatus>("/api/llm/local-vision/" + action, { method: "POST" }),
}
