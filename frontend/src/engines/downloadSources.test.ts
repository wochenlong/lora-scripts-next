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
  writeDownloadSources,
} from "./downloadSources"

afterEach(() => {
  localStorage.removeItem(DOWNLOAD_SOURCES_KEY)
})

describe("downloadSources", () => {
  it("defaults to official / native", () => {
    const prefs = readDownloadSources()
    expect(prefs.preset).toBe("official")
    expect(resolvePipIndexUrl(prefs)).toContain("pypi.org")
    expect(resolveHfEndpoint(prefs)).toContain("huggingface.co")
    expect(resolveGithubPrefix(prefs)).toBe("")
  })

  it("applies china preset mirrors", () => {
    const prefs = applyPreset("china", defaultDownloadSources())
    expect(prefs).toEqual(chinaDownloadSources())
    expect(resolvePipIndexUrl(prefs)).toContain("tuna.tsinghua")
    expect(resolvePytorchIndexUrl(prefs)).toContain("aliyun.com/pytorch-wheels")
    expect(resolveHfEndpoint(prefs)).toContain("hf-mirror.com")
    expect(resolveGithubPrefix(prefs)).toBe("https://ghfast.top/")
  })

  it("persists custom pip url", () => {
    const prefs = applyPreset("custom", defaultDownloadSources())
    prefs.pip = { choice: "custom", customUrl: "https://example.com/simple" }
    writeDownloadSources(prefs)
    expect(resolvePipIndexUrl(readDownloadSources())).toBe("https://example.com/simple")
  })
})
