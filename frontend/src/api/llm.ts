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
  prompt_presets: Array<{ id?: string; name?: string; template?: string; language?: string; max_length?: number; revision?: string }>
  cache: { translation?: boolean; caption?: boolean }
}

export interface CaptionPromptPreset {
  id: string
  kind: "caption_prompt"
  name: string
  template: string
  system_prompt?: string
  output_format: "plain_text"
  language: string
  max_length: number
  model_capabilities: string[]
  revision: string
}

export interface CaptionPromptPresetDocument {
  revision: string
  presets: CaptionPromptPreset[]
  settings: { default_caption_preset_id?: string | null }
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
  profiles: (signal?: AbortSignal) => apiData<LlmConfig>("/api/llm/profiles", { signal }),
  config: () => apiData<LlmConfig>("/api/llm/config"),
  saveConfig: (body: Partial<LlmConfig>) => apiData<LlmConfig>("/api/llm/config", { method: "PUT", body: JSON.stringify(body) }),
  promptPresets: (signal?: AbortSignal) => apiData<CaptionPromptPresetDocument>("/api/llm/prompt-presets", { signal }),
  savePromptPresets: (body: CaptionPromptPresetDocument) => apiData<CaptionPromptPresetDocument>("/api/llm/prompt-presets", { method: "PUT", body: JSON.stringify(body) }),
  connectionTest: (body: { capability: "text" | "vision"; profile_id?: string; image_path?: string; prompt?: string; language?: string }) =>
    apiData<Record<string, unknown>>("/api/llm/connection-test", { method: "POST", body: JSON.stringify(body) }),
  localVisionManifest: () => apiData<Record<string, unknown>>("/api/llm/local-vision/manifest"),
  localVisionStatus: (signal?: AbortSignal) => apiData<LocalVisionStatus>("/api/llm/local-vision/status", { signal }),
  localVisionAction: (action: "setup" | "start" | "stop" | "cancel") =>
    apiData<LocalVisionStatus>("/api/llm/local-vision/" + action, { method: "POST" }),
}
