/** Download-source prefs for engine installs (Fast / Musubi). UI-first; backend wires later. */

export const DOWNLOAD_SOURCES_KEY = "nt.training.downloadSources"

export type SourcePreset = "official" | "china" | "custom"

export type PipChoice = "official" | "tsinghua" | "aliyun" | "douban" | "custom"
export type PytorchChoice = "official" | "aliyun" | "tsinghua" | "bfsu" | "custom"
export type HfChoice = "official" | "hf-mirror" | "modelscope" | "custom"
/** GitHub clone/download URL prefixes (same pattern as portable updater). */
export type GithubChoice = "official" | "ghfast" | "ghproxy" | "custom"

export interface ChannelConfig<T extends string> {
  choice: T
  customUrl: string
}

export interface DownloadSourcesPrefs {
  preset: SourcePreset
  pip: ChannelConfig<PipChoice>
  pytorch: ChannelConfig<PytorchChoice>
  huggingface: ChannelConfig<HfChoice>
  github: ChannelConfig<GithubChoice>
}

export const PIP_URLS: Record<Exclude<PipChoice, "custom">, string> = {
  official: "https://pypi.org/simple",
  tsinghua: "https://pypi.tuna.tsinghua.edu.cn/simple",
  aliyun: "https://mirrors.aliyun.com/pypi/simple",
  douban: "https://pypi.douban.com/simple",
}

/**
 * PyTorch wheel index bases. Installer should append `/cuXXX` (e.g. cu128)
 * to match the CUDA tag used by Fast / Musubi.
 */
export const PYTORCH_URLS: Record<Exclude<PytorchChoice, "custom">, string> = {
  official: "https://download.pytorch.org/whl",
  aliyun: "https://mirrors.aliyun.com/pytorch-wheels",
  tsinghua: "https://mirrors.tuna.tsinghua.edu.cn/pytorch-wheels",
  bfsu: "https://mirrors.bfsu.edu.cn/pytorch-wheels",
}

export const HF_URLS: Record<Exclude<HfChoice, "custom">, string> = {
  official: "https://huggingface.co",
  "hf-mirror": "https://hf-mirror.com",
  /** ModelScope's Hugging Face compatible endpoint (subset of models). */
  modelscope: "https://huggingface.modelscope.cn",
}

/** Prefix applied before https://github.com/... when cloning / fetching releases. */
export const GITHUB_PREFIXES: Record<Exclude<GithubChoice, "custom">, string> = {
  official: "",
  ghfast: "https://ghfast.top/",
  ghproxy: "https://mirror.ghproxy.com/",
}

export function defaultDownloadSources(): DownloadSourcesPrefs {
  return {
    preset: "official",
    pip: { choice: "official", customUrl: "" },
    pytorch: { choice: "official", customUrl: "" },
    huggingface: { choice: "official", customUrl: "" },
    github: { choice: "official", customUrl: "" },
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
  }
}

function asChoice<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return typeof value === "string" && (allowed as readonly string[]).includes(value) ? (value as T) : fallback
}

export function readDownloadSources(): DownloadSourcesPrefs {
  const fallback = defaultDownloadSources()
  try {
    const parsed = JSON.parse(localStorage.getItem(DOWNLOAD_SOURCES_KEY) || "null")
    if (!parsed || typeof parsed !== "object") return fallback
    const preset = asChoice(parsed.preset, ["official", "china", "custom"] as const, "official")
    return {
      preset,
      pip: {
        choice: asChoice(parsed.pip?.choice, ["official", "tsinghua", "aliyun", "douban", "custom"] as const, "official"),
        customUrl: typeof parsed.pip?.customUrl === "string" ? parsed.pip.customUrl : "",
      },
      pytorch: {
        choice: asChoice(
          parsed.pytorch?.choice,
          ["official", "aliyun", "tsinghua", "bfsu", "custom"] as const,
          "official",
        ),
        customUrl: typeof parsed.pytorch?.customUrl === "string" ? parsed.pytorch.customUrl : "",
      },
      huggingface: {
        choice: asChoice(
          parsed.huggingface?.choice,
          ["official", "hf-mirror", "modelscope", "custom"] as const,
          "official",
        ),
        customUrl: typeof parsed.huggingface?.customUrl === "string" ? parsed.huggingface.customUrl : "",
      },
      github: {
        choice: asChoice(parsed.github?.choice, ["official", "ghfast", "ghproxy", "custom"] as const, "official"),
        customUrl: typeof parsed.github?.customUrl === "string" ? parsed.github.customUrl : "",
      },
    }
  } catch {
    return fallback
  }
}

export function writeDownloadSources(prefs: DownloadSourcesPrefs) {
  localStorage.setItem(DOWNLOAD_SOURCES_KEY, JSON.stringify(prefs))
}

export function applyPreset(preset: SourcePreset, current: DownloadSourcesPrefs): DownloadSourcesPrefs {
  if (preset === "official") return defaultDownloadSources()
  if (preset === "china") return chinaDownloadSources()
  return { ...current, preset: "custom" }
}

export function resolvePipIndexUrl(prefs: DownloadSourcesPrefs): string {
  if (prefs.pip.choice === "custom") return prefs.pip.customUrl.trim() || PIP_URLS.official
  return PIP_URLS[prefs.pip.choice]
}

export function resolvePytorchIndexUrl(prefs: DownloadSourcesPrefs): string {
  if (prefs.pytorch.choice === "custom") return prefs.pytorch.customUrl.trim() || PYTORCH_URLS.official
  return PYTORCH_URLS[prefs.pytorch.choice]
}

export function resolveHfEndpoint(prefs: DownloadSourcesPrefs): string {
  if (prefs.huggingface.choice === "custom") return prefs.huggingface.customUrl.trim() || HF_URLS.official
  return HF_URLS[prefs.huggingface.choice]
}

export function resolveGithubPrefix(prefs: DownloadSourcesPrefs): string {
  if (prefs.github.choice === "custom") return prefs.github.customUrl.trim()
  return GITHUB_PREFIXES[prefs.github.choice]
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
