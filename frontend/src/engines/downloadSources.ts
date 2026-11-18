/** Download-source prefs for engine installs. Persisted on the backend; the
 * localStorage key below survives only to migrate pre-persistence prefs once. */

export const DOWNLOAD_SOURCES_KEY = "nt.training.downloadSources"

export type SourcePreset = "auto" | "official" | "china" | "custom"

/** "auto" defers to the engine installer defaults (e.g. HF → hf-mirror.com). */
export type PipChoice = "auto" | "official" | "tsinghua" | "aliyun" | "douban" | "custom"
export type PytorchChoice = "auto" | "official" | "aliyun" | "tsinghua" | "bfsu" | "custom"
export type HfChoice = "auto" | "official" | "hf-mirror" | "modelscope" | "custom"
/** GitHub clone/download URL prefixes (same pattern as portable updater). */
export type GithubChoice = "auto" | "official" | "ghfast" | "ghproxy" | "custom"

export interface ChannelConfig<T extends string> {
  choice: T
  customUrl: string
}

/** Outgoing proxy for all four channels (applies to install subprocesses and probes). Empty URL = no proxy. */
export interface ProxyConfig {
  url: string
}

export interface DownloadSourcesPrefs {
  preset: SourcePreset
  pip: ChannelConfig<PipChoice>
  pytorch: ChannelConfig<PytorchChoice>
  huggingface: ChannelConfig<HfChoice>
  github: ChannelConfig<GithubChoice>
  proxy: ProxyConfig
}

export const PIP_URLS: Record<Exclude<PipChoice, "custom" | "auto">, string> = {
  official: "https://pypi.org/simple",
  tsinghua: "https://pypi.tuna.tsinghua.edu.cn/simple",
  aliyun: "https://mirrors.aliyun.com/pypi/simple",
  douban: "https://pypi.douban.com/simple",
}

/**
 * PyTorch wheel index bases. Installer should append `/cuXXX` (e.g. cu128)
 * to match the CUDA tag used by Fast / Musubi.
 */
export const PYTORCH_URLS: Record<Exclude<PytorchChoice, "custom" | "auto">, string> = {
  official: "https://download.pytorch.org/whl",
  aliyun: "https://mirrors.aliyun.com/pytorch-wheels",
  tsinghua: "https://mirrors.tuna.tsinghua.edu.cn/pytorch-wheels",
  bfsu: "https://mirrors.bfsu.edu.cn/pytorch-wheels",
}

export const HF_URLS: Record<Exclude<HfChoice, "custom" | "auto">, string> = {
  official: "https://huggingface.co",
  "hf-mirror": "https://hf-mirror.com",
  /** ModelScope's Hugging Face compatible endpoint (subset of models). */
  modelscope: "https://huggingface.modelscope.cn",
}

/** Prefix applied before https://github.com/... when cloning / fetching releases. */
export const GITHUB_PREFIXES: Record<Exclude<GithubChoice, "custom" | "auto">, string> = {
  official: "",
  ghfast: "https://ghfast.top/",
  ghproxy: "https://mirror.ghproxy.com/",
}

export function defaultDownloadSources(): DownloadSourcesPrefs {
  return {
    preset: "auto",
    pip: { choice: "auto", customUrl: "" },
    pytorch: { choice: "auto", customUrl: "" },
    huggingface: { choice: "auto", customUrl: "" },
    github: { choice: "auto", customUrl: "" },
    proxy: { url: "" },
  }
}

/** China-friendly preset: mirror pip / PyTorch / HF + GitHub proxy. */
export function chinaDownloadSources(): DownloadSourcesPrefs {
  return {
    preset: "china",
    pip: { choice: "tsinghua", customUrl: "" },
    pytorch: { choice: "aliyun", customUrl: "" },
    huggingface: { choice: "hf-mirror", customUrl: "" },
    github: { choice: "ghfast", customUrl: "" },
    proxy: { url: "" },
  }
}

function asChoice<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return typeof value === "string" && (allowed as readonly string[]).includes(value) ? (value as T) : fallback
}

/** Legacy localStorage prefs, read only for the one-time migration to the
 * backend-persisted config. Do not write new code against this. */
export function readDownloadSources(): DownloadSourcesPrefs {
  const fallback = defaultDownloadSources()
  try {
    const parsed = JSON.parse(localStorage.getItem(DOWNLOAD_SOURCES_KEY) || "null")
    if (!parsed || typeof parsed !== "object") return fallback
    const preset = asChoice(parsed.preset, ["auto", "official", "china", "custom"] as const, "auto")
    return {
      preset,
      pip: {
        choice: asChoice(parsed.pip?.choice, ["auto", "official", "tsinghua", "aliyun", "douban", "custom"] as const, "auto"),
        customUrl: typeof parsed.pip?.customUrl === "string" ? parsed.pip.customUrl : "",
      },
      pytorch: {
        choice: asChoice(
          parsed.pytorch?.choice,
          ["auto", "official", "aliyun", "tsinghua", "bfsu", "custom"] as const,
          "auto",
        ),
        customUrl: typeof parsed.pytorch?.customUrl === "string" ? parsed.pytorch.customUrl : "",
      },
      huggingface: {
        choice: asChoice(
          parsed.huggingface?.choice,
          ["auto", "official", "hf-mirror", "modelscope", "custom"] as const,
          "auto",
        ),
        customUrl: typeof parsed.huggingface?.customUrl === "string" ? parsed.huggingface.customUrl : "",
      },
      github: {
        choice: asChoice(parsed.github?.choice, ["auto", "official", "ghfast", "ghproxy", "custom"] as const, "auto"),
        customUrl: typeof parsed.github?.customUrl === "string" ? parsed.github.customUrl : "",
      },
      proxy: {
        // Legacy shape had { enabled, url }: a disabled proxy drops its URL.
        url: parsed.proxy?.enabled === false ? "" : typeof parsed.proxy?.url === "string" ? parsed.proxy.url : "",
      },
    }
  } catch {
    return fallback
  }
}

export function clearLegacyDownloadSources() {
  localStorage.removeItem(DOWNLOAD_SOURCES_KEY)
}

export function applyPreset(preset: SourcePreset, current: DownloadSourcesPrefs): DownloadSourcesPrefs {
  if (preset === "auto") return { ...defaultDownloadSources(), proxy: current.proxy }
  if (preset === "official") {
    return {
      preset: "official",
      pip: { choice: "official", customUrl: "" },
      pytorch: { choice: "official", customUrl: "" },
      huggingface: { choice: "official", customUrl: "" },
      github: { choice: "official", customUrl: "" },
      proxy: current.proxy,
    }
  }
  if (preset === "china") return { ...chinaDownloadSources(), proxy: current.proxy }
  return { ...current, preset: "custom" }
}

/** Explicit URL for a channel; "" when the channel defers to engine defaults ("auto"). */
export function resolvePipIndexUrl(prefs: DownloadSourcesPrefs): string {
  if (prefs.pip.choice === "auto") return ""
  if (prefs.pip.choice === "custom") return prefs.pip.customUrl.trim() || PIP_URLS.official
  return PIP_URLS[prefs.pip.choice]
}

export function resolvePytorchIndexUrl(prefs: DownloadSourcesPrefs): string {
  if (prefs.pytorch.choice === "auto") return ""
  if (prefs.pytorch.choice === "custom") return prefs.pytorch.customUrl.trim() || PYTORCH_URLS.official
  return PYTORCH_URLS[prefs.pytorch.choice]
}

export function resolveHfEndpoint(prefs: DownloadSourcesPrefs): string {
  if (prefs.huggingface.choice === "auto") return ""
  if (prefs.huggingface.choice === "custom") return prefs.huggingface.customUrl.trim() || HF_URLS.official
  return HF_URLS[prefs.huggingface.choice]
}

export function resolveGithubPrefix(prefs: DownloadSourcesPrefs): string {
  if (prefs.github.choice === "auto") return ""
  if (prefs.github.choice === "custom") return prefs.github.customUrl.trim()
  return GITHUB_PREFIXES[prefs.github.choice]
}

/** Payload fields sent with Fast / Musubi install & repair requests. */
export interface DownloadSourcesPayload {
  pip_index_url?: string
  pytorch_index_url?: string
  hf_endpoint?: string
  github_url_prefix?: string
  proxy_url?: string
}

/**
 * Channels left on "auto" are omitted so the backend keeps the engine
 * installer defaults (see mikazuki/download_sources.py: empty → None).
 */
export function resolvedDownloadSourcesPayload(prefs: DownloadSourcesPrefs = readDownloadSources()): DownloadSourcesPayload {
  const payload: DownloadSourcesPayload = {}
  const pip = resolvePipIndexUrl(prefs)
  const pytorch = resolvePytorchIndexUrl(prefs)
  const hf = resolveHfEndpoint(prefs)
  const github = resolveGithubPrefix(prefs)
  if (pip) payload.pip_index_url = pip
  if (pytorch) payload.pytorch_index_url = pytorch
  if (hf) payload.hf_endpoint = hf
  if (github) payload.github_url_prefix = github
  if (prefs.proxy.url.trim()) payload.proxy_url = prefs.proxy.url.trim()
  return payload
}

/** Summary chips for the collapsed header (resolved choice labels, not URLs). */
export function activeSourceSummary(prefs: DownloadSourcesPrefs): {
  pip: string
  pytorch: string
  huggingface: string
  github: string
} {
  return {
    pip: prefs.pip.choice,
    pytorch: prefs.pytorch.choice,
    huggingface: prefs.huggingface.choice,
    github: prefs.github.choice,
  }
}

function trimSlash(url: string): string {
  return url.replace(/\/+$/, "")
}

function channelFromUrl<T extends string>(
  url: string | null | undefined,
  table: Record<string, string>,
): ChannelConfig<T> {
  const value = (url ?? "").trim()
  if (!value) return { choice: "auto" as T, customUrl: "" }
  const match = Object.entries(table).find(([, known]) => known && trimSlash(known) === trimSlash(value))
  if (match) return { choice: match[0] as T, customUrl: "" }
  return { choice: "custom" as T, customUrl: value }
}

/** Reverse-map server-persisted fields to UI choices; unknown URLs become "custom". */
export function prefsFromServerSources(sources: {
  pip_index_url?: string | null
  pytorch_index_url?: string | null
  hf_endpoint?: string | null
  github_url_prefix?: string | null
  proxy_url?: string | null
} | null): DownloadSourcesPrefs {
  const prefs = defaultDownloadSources()
  if (!sources) return prefs
  prefs.pip = channelFromUrl<PipChoice>(sources.pip_index_url, PIP_URLS)
  prefs.pytorch = channelFromUrl<PytorchChoice>(sources.pytorch_index_url, PYTORCH_URLS)
  prefs.huggingface = channelFromUrl<HfChoice>(sources.hf_endpoint, HF_URLS)
  prefs.github = channelFromUrl<GithubChoice>(sources.github_url_prefix, GITHUB_PREFIXES)
  prefs.proxy = { url: (sources.proxy_url ?? "").trim() }
  const china = chinaDownloadSources()
  const matches = (target: DownloadSourcesPrefs) =>
    (["pip", "pytorch", "huggingface", "github"] as const).every((key) => prefs[key].choice === target[key].choice)
  prefs.preset = matches(defaultDownloadSources()) ? "auto" : matches(china) ? "china" : "custom"
  return prefs
}
