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
  secret_revision?: number
  asset_id?: string | null
  revision?: string | null
  verified_capabilities?: string[]
  verification?: { fingerprint?: string; capabilities?: string[]; verified_at?: string }
  enabled: boolean
  ready: boolean
  metadata?: Record<string, unknown>
}

/** Only real backend capability verification makes a profile usable. */
export function isVerifiedProfile(profile: Pick<LlmProfile, "enabled" | "ready" | "capabilities" | "verified_capabilities">, capability: string): boolean {
  return Boolean(profile.enabled && profile.ready && profile.capabilities.includes(capability)
    && Array.isArray(profile.verified_capabilities) && profile.verified_capabilities.includes(capability))
}

export interface LlmConfig {
  version: number
  revision?: string
  profiles: LlmProfile[]
  routes: Record<string, string>
  prompt_presets: Array<{ id?: string; name?: string; template?: string; language?: string; max_length?: number; revision?: string }>
  cache: { translation?: boolean; caption?: boolean }
  local_fallback_enabled?: boolean
  caption_translation?: CaptionTranslationSettings
}

export interface CaptionTranslationSettings {
  concurrency: number
  max_tokens: number
  temperature: number
}

export interface CaptionTranslationSettingsResponse {
  settings: CaptionTranslationSettings
  revision: string
}

export const DEFAULT_CAPTION_TRANSLATION_SETTINGS: CaptionTranslationSettings = { concurrency: 3, max_tokens: 2048, temperature: 0.7 }

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
  settings: { default_caption_preset_id?: string | null; legacy_imported?: boolean }
}

export interface LocalVisionStatus {
  state: string
  model_id?: string
  model_filename?: string
  model_url?: string
  model_path?: string
  installed: boolean
  runtime_installed?: boolean
  runtime_state?: string
  runtime_downloaded_bytes?: number
  runtime_total_bytes?: number
  endpoint?: string
  port?: number
  runtime_version?: string
  size_bytes?: number
  downloaded_bytes: number
  total_bytes: number
  error?: string | null
  estimated_peak_rss_bytes?: number
}

export const llmApi = {
  // Omission inherits the shared backend policy; explicit false remains an opt-out.
  translateCaption: (text: string, allowLocalFallback?: boolean, signal?: AbortSignal) => apiData<{ translation: string; skipped: boolean; cached: boolean }>("/api/llm/caption-translation", {
    method: "POST",
    body: JSON.stringify({ text, ...(typeof allowLocalFallback === "boolean" ? { allow_local_fallback: allowLocalFallback } : {}) }),
    signal,
  }),
  captionTranslationSettings: () => apiData<CaptionTranslationSettingsResponse>("/api/llm/caption-translation/settings"),
  saveCaptionTranslationSettings: (settings: CaptionTranslationSettings, revision: string) => apiData<CaptionTranslationSettingsResponse>("/api/llm/caption-translation/settings", { method: "PUT", body: JSON.stringify({ settings, revision }) }),
  profiles: (signal?: AbortSignal) => apiData<LlmConfig>("/api/llm/profiles", { signal }),
  config: () => apiData<LlmConfig>("/api/llm/config"),
  saveConfig: (body: Partial<LlmConfig>) => apiData<LlmConfig>("/api/llm/config", { method: "PUT", body: JSON.stringify(body) }),
  promptPresets: (signal?: AbortSignal) => apiData<CaptionPromptPresetDocument>("/api/llm/prompt-presets", { signal }),
  savePromptPresets: (body: CaptionPromptPresetDocument) => apiData<CaptionPromptPresetDocument>("/api/llm/prompt-presets", { method: "PUT", body: JSON.stringify(body) }),
  importLegacyPromptPresets: (revision: string) => apiData<CaptionPromptPresetDocument>("/api/llm/prompt-presets/import-legacy", { method: "POST", body: JSON.stringify({ confirmed: true, revision }) }),
  connectionTest: (body: { capability?: "text" | "vision"; profile_id?: string; image_path?: string; prompt?: string; language?: string }) =>
    apiData<Record<string, unknown>>("/api/llm/connection-test", { method: "POST", body: JSON.stringify(body) }),
  localVisionManifest: () => apiData<Record<string, unknown>>("/api/llm/local-vision/manifest"),
  localVisionStatus: (signal?: AbortSignal) => apiData<LocalVisionStatus>("/api/llm/local-vision/status", { signal }),
  localVisionAction: (action: "setup" | "start" | "stop" | "cancel") =>
    apiData<LocalVisionStatus>("/api/llm/local-vision/" + action, { method: "POST" }),
}
