import type { NetworkSettings } from './bridge'

export type ProxyField = 'http_proxy' | 'https_proxy' | 'no_proxy'
export interface NetworkDraft {
  mode: NonNullable<NetworkSettings['mode']>
  http_proxy: string
  https_proxy: string
  no_proxy: string
}

// Preserve absent/null/empty values until the user edits that field or requests inheritance.
export function settingsForSave(saved: NetworkSettings, draft: NetworkDraft, inherit: readonly ProxyField[]): NetworkSettings {
  const settings: NetworkSettings = { ...saved, mode: draft.mode }
  for (const key of ['http_proxy', 'https_proxy', 'no_proxy'] as const) {
    if (inherit.includes(key)) delete settings[key]
    else if (draft[key] !== (saved[key] ?? '')) settings[key] = draft[key].trim()
  }
  return settings
}
