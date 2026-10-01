import { apiData } from "./client"

export interface DatasetItem { name: string; relative_path: string; category: string; caption: string; caption_exists: boolean; tags: string[]; image_url: string; thumb_url: string }
export interface DatasetScan { root: string; total: number; items: DatasetItem[]; tags: Array<{ tag: string; count: number }>; categories: Array<{ name: string; value: string; count: number }> }
export interface ChangedItem { image: string; caption: string; caption_exists: boolean; tags: string[] }
export interface TagReplacement { from: string; to: string }
export interface DatasetMutation { changed: number; items: ChangedItem[] }
export interface BatchEditRequest {
  root: string
  images: string[]
  append?: string[]
  append_position?: "front" | "back"
  remove?: string[]
  replace?: TagReplacement[]
  sort?: boolean
  clean?: boolean
  underscore_to_space?: boolean
  strip_escape_chars?: boolean
}
export interface HistoryItem { image: string; before: string; after: string; before_exists: boolean; after_exists: boolean }
export interface HistoryChange { label: string; count: number; items: HistoryItem[] }
export interface DatasetHistory { can_undo: boolean; can_redo: boolean; changes: HistoryChange[] }
export type TagTranslationProvider = "danbooru" | "mymemory" | "auto" | "llm"
export interface TagTranslation { tag: string; translation: string | null; source: string | null; status: "hit" | "missing" | "error"; cached?: boolean; error_code?: string | null; category?: number | null; post_count?: number | null }
export interface TagTranslationResponse { items: TagTranslation[]; provider: TagTranslationProvider; locale: string }
export interface LlmProfile { id: string; name: string; endpoint: string; model: string; api_key: string; api_key_configured?: boolean; reasoning_effort?: "disabled" | "high" | "max"; system_prompt?: string }
export interface TagTranslationConfig {
  deepseek: LlmProfile
  llm_mode: "remote" | "local"
  active_remote_id: string
  remote_profiles: LlmProfile[]
  local: { enabled: boolean; endpoint: string; runtime_path: string; port: number; context_length: number }
}
export interface TagTranslationCacheStatus { total: number; mymemory: number; llm: number }
export interface TagDictionaryStatus { state: string; installed: boolean; row_count: number; size_bytes: number; installed_sha?: string | null; remote_sha?: string | null; update_available?: boolean; downloaded_bytes?: number; total_bytes?: number; error?: string | null }
export interface LocalModelStatus { state: string; model_id: string; model_filename: string; model_url: string; model_path: string; installed: boolean; size_bytes: number; downloaded_bytes: number; total_bytes: number; runtime_path: string; endpoint: string; port: number; runtime_version?: string; runtime_installed?: boolean; runtime_state?: string; runtime_downloaded_bytes?: number; runtime_total_bytes?: number; error?: string | null }

const post = <T>(path: string, body: unknown) => apiData<T>(path, { method: "POST", body: JSON.stringify(body) })
export const datasetApi = {
  scan: (path: string) => post<DatasetScan>("/api/dataset-editor/scan", { path }),
  save: (root: string, image: string, caption: string) => post<ChangedItem>("/api/dataset-editor/caption", { root, image, caption }),
  batch: (body: BatchEditRequest) => post<DatasetMutation>("/api/dataset-editor/batch", body),
  undo: (root: string) => post<DatasetMutation>("/api/dataset-editor/undo", { root }),
  redo: (root: string) => post<DatasetMutation>("/api/dataset-editor/redo", { root }),
  history: (root: string) => post<DatasetHistory>("/api/dataset-editor/history", { root }),
  tagTranslations: (tags: string[], provider: TagTranslationProvider, locale = "zh-CN", options: { localOnly?: boolean; refresh?: boolean } = {}) =>
    post<TagTranslationResponse>("/api/tag-translation/resolve", { tags, provider, locale, local_only: options.localOnly ?? false, refresh: options.refresh ?? false }),
  tagTranslationConfig: () => apiData<TagTranslationConfig>("/api/tag-translation/config"),
  saveTagTranslationConfig: (payload: Partial<Omit<TagTranslationConfig, "local">> & { deepseek?: Partial<TagTranslationConfig["deepseek"]>; local?: Partial<TagTranslationConfig["local"]> }) =>
    apiData<TagTranslationConfig>("/api/tag-translation/config", { method: "PUT", body: JSON.stringify(payload) }),
  tagTranslationCache: () => apiData<TagTranslationCacheStatus>("/api/tag-translation/cache"),
  clearTagTranslationCache: (provider?: "mymemory" | "llm") => apiData<{ provider: string | null; total: number }>(`/api/tag-translation/cache${provider ? `?provider=${provider}` : ""}`, { method: "DELETE" }),
  tagDictionaryStatus: () => apiData<TagDictionaryStatus>("/api/tag-translation/dictionary/status"),
  checkTagDictionary: () => apiData<TagDictionaryStatus>("/api/tag-translation/dictionary/check", { method: "POST" }),
  updateTagDictionary: (force = false) => apiData<TagDictionaryStatus>(`/api/tag-translation/dictionary/update?force=${force ? "true" : "false"}`, { method: "POST" }),
  retryTagDictionary: () => apiData<TagDictionaryStatus>("/api/tag-translation/dictionary/retry", { method: "POST" }),
  cancelTagDictionary: () => apiData<TagDictionaryStatus>("/api/tag-translation/dictionary/cancel", { method: "POST" }),
  localModelStatus: () => apiData<LocalModelStatus>("/api/tag-translation/local-model/status"),
  setupLocalModel: (force = false) => apiData<LocalModelStatus>("/api/tag-translation/local-model/setup?force=" + (force ? "true" : "false"), { method: "POST" }),
  installLocalModel: (force = false) => apiData<LocalModelStatus>(`/api/tag-translation/local-model/install?force=${force ? "true" : "false"}`, { method: "POST" }),
  cancelLocalModel: () => apiData<LocalModelStatus>("/api/tag-translation/local-model/cancel", { method: "POST" }),
  startLocalModel: () => apiData<LocalModelStatus>("/api/tag-translation/local-model/start", { method: "POST" }),
  stopLocalModel: () => apiData<LocalModelStatus>("/api/tag-translation/local-model/stop", { method: "POST" }),
}
