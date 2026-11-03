// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest"
import {
  DOWNLOAD_SOURCES_KEY,
  applyPreset,
  chinaDownloadSources,
  defaultDownloadSources,
  readDownloadSources,
  resolveGithubPrefix,
  resolveHfEndpoint,
  resolvePipIndexUrl,
  resolvePytorchIndexUrl,
  prefsFromServerSources,
  resolvedDownloadSourcesPayload,
} from "./downloadSources"

afterEach(() => {
  localStorage.removeItem(DOWNLOAD_SOURCES_KEY)
})

describe("downloadSources", () => {
  it("defaults to auto (engine installer defaults) and sends an empty payload", () => {
    const prefs = readDownloadSources()
    expect(prefs.preset).toBe("auto")
    expect(prefs.pip.choice).toBe("auto")
    expect(prefs.pytorch.choice).toBe("auto")
    expect(prefs.huggingface.choice).toBe("auto")
    expect(prefs.github.choice).toBe("auto")
    expect(resolvePipIndexUrl(prefs)).toBe("")
    expect(resolveHfEndpoint(prefs)).toBe("")
    expect(resolveGithubPrefix(prefs)).toBe("")
    expect(resolvedDownloadSourcesPayload()).toEqual({})
  })

  it("keeps explicit legacy official prefs instead of rewriting them to auto", () => {
    localStorage.setItem(
      DOWNLOAD_SOURCES_KEY,
      JSON.stringify({
        preset: "official",
        pip: { choice: "official", customUrl: "" },
        pytorch: { choice: "official", customUrl: "" },
        huggingface: { choice: "official", customUrl: "" },
        github: { choice: "official", customUrl: "" },
        proxy: { url: "" },
      }),
    )
    const prefs = readDownloadSources()
    expect(prefs.preset).toBe("official")
    expect(resolvePipIndexUrl(prefs)).toContain("pypi.org")
    expect(resolveHfEndpoint(prefs)).toContain("huggingface.co")
    expect(resolvedDownloadSourcesPayload()).toEqual({
      pip_index_url: "https://pypi.org/simple",
      pytorch_index_url: "https://download.pytorch.org/whl",
      hf_endpoint: "https://huggingface.co",
    })
  })

  it("falls back to auto for unknown stored values", () => {
    localStorage.setItem(
      DOWNLOAD_SOURCES_KEY,
      JSON.stringify({ preset: "mars", pip: { choice: "unknown-mirror" } }),
    )
    const prefs = readDownloadSources()
    expect(prefs.preset).toBe("auto")
    expect(prefs.pip.choice).toBe("auto")
  })

  it("applies china preset mirrors", () => {
    const prefs = applyPreset("china", defaultDownloadSources())
    expect(prefs).toEqual(chinaDownloadSources())
    expect(resolvePipIndexUrl(prefs)).toContain("tuna.tsinghua")
    expect(resolvePytorchIndexUrl(prefs)).toContain("aliyun.com/pytorch-wheels")
    expect(resolveHfEndpoint(prefs)).toContain("hf-mirror.com")
    expect(resolveGithubPrefix(prefs)).toBe("https://ghfast.top/")
  })

  it("applies auto preset as engine defaults", () => {
    const prefs = applyPreset("auto", chinaDownloadSources())
    expect(prefs).toEqual(defaultDownloadSources())
    expect(resolvedDownloadSourcesPayload(prefs)).toEqual({})
  })

  it("persists custom pip url", () => {
    const prefs = applyPreset("custom", defaultDownloadSources())
    prefs.pip = { choice: "custom", customUrl: "https://example.com/simple" }
    localStorage.setItem(DOWNLOAD_SOURCES_KEY, JSON.stringify(prefs))
    expect(resolvePipIndexUrl(readDownloadSources())).toBe("https://example.com/simple")
  })

  it("builds install API payload from china preset", () => {
    expect(resolvedDownloadSourcesPayload(chinaDownloadSources())).toEqual({
      pip_index_url: "https://pypi.tuna.tsinghua.edu.cn/simple",
      pytorch_index_url: "https://mirrors.aliyun.com/pytorch-wheels",
      hf_endpoint: "https://hf-mirror.com",
      github_url_prefix: "https://ghfast.top/",
    })
  })

  it("omits only the auto channels from a mixed payload", () => {
    const prefs = defaultDownloadSources()
    prefs.huggingface = { choice: "hf-mirror", customUrl: "" }
    prefs.github = { choice: "official", customUrl: "" }
    expect(resolvedDownloadSourcesPayload(prefs)).toEqual({
      hf_endpoint: "https://hf-mirror.com",
    })
  })

  it("includes proxy_url only when a proxy URL is set", () => {
    const prefs = defaultDownloadSources()
    expect(resolvedDownloadSourcesPayload(prefs)).toEqual({})
    prefs.proxy = { url: "  " }
    expect(resolvedDownloadSourcesPayload(prefs)).toEqual({})
    prefs.proxy = { url: "http://127.0.0.1:7890" }
    expect(resolvedDownloadSourcesPayload(prefs)).toEqual({ proxy_url: "http://127.0.0.1:7890" })
  })

  it("preserves the proxy config across preset switches", () => {
    const prefs = defaultDownloadSources()
    prefs.proxy = { url: "http://127.0.0.1:7890" }
    expect(applyPreset("china", prefs).proxy).toEqual(prefs.proxy)
    expect(applyPreset("official", prefs).proxy).toEqual(prefs.proxy)
    expect(applyPreset("auto", prefs).proxy).toEqual(prefs.proxy)
  })

  it("migrates legacy prefs without a proxy block to an empty proxy", () => {
    localStorage.setItem(
      DOWNLOAD_SOURCES_KEY,
      JSON.stringify({ preset: "china", huggingface: { choice: "hf-mirror", customUrl: "" } }),
    )
    const prefs = readDownloadSources()
    expect(prefs.proxy).toEqual({ url: "" })
    expect(prefs.huggingface.choice).toBe("hf-mirror")
  })

  it("migrates the legacy enabled/url proxy shape, dropping a disabled proxy", () => {
    localStorage.setItem(
      DOWNLOAD_SOURCES_KEY,
      JSON.stringify({ proxy: { enabled: true, url: "http://127.0.0.1:7890" } }),
    )
    expect(readDownloadSources().proxy).toEqual({ url: "http://127.0.0.1:7890" })
    localStorage.setItem(
      DOWNLOAD_SOURCES_KEY,
      JSON.stringify({ proxy: { enabled: false, url: "http://127.0.0.1:7890" } }),
    )
    expect(readDownloadSources().proxy).toEqual({ url: "" })
  })
})

describe("prefsFromServerSources", () => {
  it("maps null / empty server state to all-auto defaults", () => {
    expect(prefsFromServerSources(null)).toEqual(defaultDownloadSources())
    expect(prefsFromServerSources({})).toEqual(defaultDownloadSources())
  })

  it("maps the china preset fields back to choices", () => {
    const prefs = prefsFromServerSources({
      pip_index_url: "https://pypi.tuna.tsinghua.edu.cn/simple",
      pytorch_index_url: "https://mirrors.aliyun.com/pytorch-wheels",
      hf_endpoint: "https://hf-mirror.com",
      github_url_prefix: "https://ghfast.top/",
      proxy_url: null,
    })
    expect(prefs.preset).toBe("china")
    expect(prefs.pip.choice).toBe("tsinghua")
    expect(prefs.pytorch.choice).toBe("aliyun")
    expect(prefs.huggingface.choice).toBe("hf-mirror")
    expect(prefs.github.choice).toBe("ghfast")
    expect(prefs.proxy.url).toBe("")
  })

  it("tolerates trailing slashes when matching known mirrors", () => {
    const prefs = prefsFromServerSources({ hf_endpoint: "https://hf-mirror.com/" })
    expect(prefs.huggingface.choice).toBe("hf-mirror")
  })

  it("maps unknown URLs to custom and marks the preset custom", () => {
    const prefs = prefsFromServerSources({
      pip_index_url: "https://pypi.example.com/simple",
      proxy_url: "http://127.0.0.1:7890",
    })
    expect(prefs.pip).toEqual({ choice: "custom", customUrl: "https://pypi.example.com/simple" })
    expect(prefs.preset).toBe("custom")
    expect(prefs.proxy.url).toBe("http://127.0.0.1:7890")
  })

  it("round-trips through resolvedDownloadSourcesPayload", () => {
    const saved = {
      pip_index_url: "https://pypi.tuna.tsinghua.edu.cn/simple",
      hf_endpoint: "https://hf-mirror.com",
      proxy_url: "http://127.0.0.1:7890",
    }
    expect(resolvedDownloadSourcesPayload(prefsFromServerSources(saved))).toEqual(saved)
  })
})
