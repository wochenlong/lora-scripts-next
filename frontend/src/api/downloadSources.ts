import { apiData } from "./client"
import type { DownloadSourcesPayload } from "../engines/downloadSources"

export interface SourceCheckResult {
  ok: boolean
  status: number | null
  latency_ms: number | null
  url: string
  error: string | null
}

export type SourceCheckChannel = "pip" | "pytorch" | "huggingface" | "github"

export type SourceCheckMap = Record<SourceCheckChannel, SourceCheckResult>

/** Server-persisted source fields; null = channel stays on engine defaults. */
export interface ServerSources {
  pip_index_url: string | null
  pytorch_index_url: string | null
  hf_endpoint: string | null
  github_url_prefix: string | null
  proxy_url: string | null
}

export interface ServerSourcesState {
  configured: boolean
  sources: ServerSources | null
}

export const downloadSourcesApi = {
  /** Probe one channel (pass `channel`) or all four; per-channel calls keep a hanging mirror from delaying the rest. */
  check: (payload: DownloadSourcesPayload = {}, channel?: SourceCheckChannel) =>
    apiData<Partial<SourceCheckMap>>("/api/download-sources/check", {
      method: "POST",
      body: JSON.stringify(channel ? { ...payload, channel } : payload),
    }),

  get: () => apiData<ServerSourcesState>("/api/download-sources"),

  save: (payload: DownloadSourcesPayload) =>
    apiData<ServerSourcesState>("/api/download-sources", { method: "PUT", body: JSON.stringify(payload) }),
}
