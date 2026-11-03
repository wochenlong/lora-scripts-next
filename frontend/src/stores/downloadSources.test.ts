// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { createPinia, setActivePinia } from "pinia"
import { DOWNLOAD_SOURCES_KEY, chinaDownloadSources, defaultDownloadSources } from "../engines/downloadSources"
import { SOURCE_CHANNELS, statusOf, useDownloadSourcesStore } from "./downloadSources"

const checkMock = vi.fn()
const getMock = vi.fn()
const saveMock = vi.fn()
vi.mock("../api/downloadSources", () => ({
  downloadSourcesApi: {
    check: (...args: unknown[]) => checkMock(...args),
    get: () => getMock(),
    save: (payload: unknown) => saveMock(payload),
  },
}))

const OK_RESULT = { ok: true, status: 200, latency_ms: 120, url: "https://example.com", error: null }

function channelResult(channel: string, latency = 120) {
  return { [channel]: { ...OK_RESULT, latency_ms: latency } }
}

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.removeItem(DOWNLOAD_SOURCES_KEY)
  checkMock.mockReset()
  checkMock.mockImplementation((_payload: unknown, channel: string) => Promise.resolve(channelResult(channel)))
  getMock.mockReset()
  getMock.mockResolvedValue({ configured: false, sources: null })
  saveMock.mockReset()
  saveMock.mockResolvedValue({ configured: true, sources: null })
})

afterEach(() => {
  vi.useRealTimers()
})

describe("statusOf", () => {
  it("maps missing / failed / slow / ok results", () => {
    expect(statusOf(null)).toBe("unknown")
    expect(statusOf(undefined)).toBe("unknown")
    expect(statusOf({ ...OK_RESULT, ok: false, error: "boom" })).toBe("fail")
    expect(statusOf({ ...OK_RESULT, latency_ms: 5000 })).toBe("slow")
    expect(statusOf(OK_RESULT)).toBe("ok")
  })
})

describe("server hydration", () => {
  it("hydrates prefs from the persisted server config", async () => {
    getMock.mockResolvedValue({
      configured: true,
      sources: {
        pip_index_url: "https://pypi.tuna.tsinghua.edu.cn/simple",
        pytorch_index_url: "https://mirrors.aliyun.com/pytorch-wheels",
        hf_endpoint: "https://hf-mirror.com",
        github_url_prefix: "https://ghfast.top/",
        proxy_url: null,
      },
    })
    const store = useDownloadSourcesStore()
    await store.ensureLoaded()
    expect(store.prefs.pip.choice).toBe("tsinghua")
    expect(store.prefs.huggingface.choice).toBe("hf-mirror")
    expect(saveMock).not.toHaveBeenCalled()
  })

  it("migrates legacy localStorage prefs once when the server is unconfigured", async () => {
    localStorage.setItem(DOWNLOAD_SOURCES_KEY, JSON.stringify(chinaDownloadSources()))
    const store = useDownloadSourcesStore()
    await store.ensureLoaded()
    expect(saveMock).toHaveBeenCalledTimes(1)
    expect(saveMock).toHaveBeenCalledWith({
      pip_index_url: "https://pypi.tuna.tsinghua.edu.cn/simple",
      pytorch_index_url: "https://mirrors.aliyun.com/pytorch-wheels",
      hf_endpoint: "https://hf-mirror.com",
      github_url_prefix: "https://ghfast.top/",
    })
    expect(localStorage.getItem(DOWNLOAD_SOURCES_KEY)).toBeNull()
    expect(store.prefs.huggingface.choice).toBe("hf-mirror")
  })

  it("drops legacy localStorage without uploading when it only holds defaults", async () => {
    localStorage.setItem(DOWNLOAD_SOURCES_KEY, JSON.stringify(defaultDownloadSources()))
    const store = useDownloadSourcesStore()
    await store.ensureLoaded()
    expect(saveMock).not.toHaveBeenCalled()
    expect(localStorage.getItem(DOWNLOAD_SOURCES_KEY)).toBeNull()
  })

  it("ignores legacy localStorage when the server already has a config", async () => {
    localStorage.setItem(DOWNLOAD_SOURCES_KEY, JSON.stringify(chinaDownloadSources()))
    getMock.mockResolvedValue({
      configured: true,
      sources: { pip_index_url: "https://pypi.org/simple", pytorch_index_url: null, hf_endpoint: null, github_url_prefix: null, proxy_url: null },
    })
    const store = useDownloadSourcesStore()
    await store.ensureLoaded()
    expect(saveMock).not.toHaveBeenCalled()
    expect(localStorage.getItem(DOWNLOAD_SOURCES_KEY)).toBeNull()
    expect(store.prefs.pip.choice).toBe("official")
  })

  it("keeps defaults when the settings API is unreachable", async () => {
    getMock.mockRejectedValue(new Error("connection refused"))
    const store = useDownloadSourcesStore()
    await store.ensureLoaded()
    expect(store.prefs).toEqual(defaultDownloadSources())
  })

  it("savePrefs persists to the backend and adopts the saved prefs", async () => {
    const store = useDownloadSourcesStore()
    await store.savePrefs(chinaDownloadSources())
    expect(saveMock).toHaveBeenCalledWith({
      pip_index_url: "https://pypi.tuna.tsinghua.edu.cn/simple",
      pytorch_index_url: "https://mirrors.aliyun.com/pytorch-wheels",
      hf_endpoint: "https://hf-mirror.com",
      github_url_prefix: "https://ghfast.top/",
    })
    expect(store.prefs.preset).toBe("china")
  })
})

describe("downloadSources store", () => {
  it("checks every channel with its own request", async () => {
    const store = useDownloadSourcesStore()
    await store.checkAll()
    expect(checkMock).toHaveBeenCalledTimes(4)
    for (const channel of SOURCE_CHANNELS) {
      expect(checkMock).toHaveBeenCalledWith({}, channel)
      expect(store.resultFor(channel)?.ok).toBe(true)
      expect(store.statusFor(channel)).toBe("ok")
    }
  })

  it("a hanging channel does not delay the others", async () => {
    let resolveHang: ((value: unknown) => void) | undefined
    checkMock.mockImplementation((_payload: unknown, channel: string) =>
      channel === "github" ? new Promise((resolve) => { resolveHang = resolve }) : Promise.resolve(channelResult(channel)),
    )
    const store = useDownloadSourcesStore()
    const all = store.checkAll()
    await vi.waitFor(() => {
      expect(store.statusFor("pip")).toBe("ok")
      expect(store.statusFor("huggingface")).toBe("ok")
    })
    expect(store.statusFor("github")).toBe("checking")
    resolveHang?.(channelResult("github"))
    await all
    expect(store.statusFor("github")).toBe("ok")
  })

  it("presumes fail after 1s without response, then flips back on a late success", async () => {
    vi.useFakeTimers()
    const resolvers: Array<() => void> = []
    checkMock.mockImplementation((_payload: unknown, channel: string) =>
      new Promise((resolve) => { resolvers.push(() => resolve(channelResult(channel))) }),
    )
    const store = useDownloadSourcesStore()
    const all = store.checkAll()

    expect(store.statusFor("pip")).toBe("checking")
    await vi.advanceTimersByTimeAsync(1100)
    expect(store.statusFor("pip")).toBe("fail")
    expect(store.presumedFail("pip")).toBe(true)

    resolvers.forEach((resolve) => resolve())
    await all
    expect(store.statusFor("pip")).toBe("ok")
  })

  it("checkOnce hydrates from the server and auto-checks at most once", async () => {
    const store = useDownloadSourcesStore()
    await store.checkOnce()
    await store.checkOnce()
    expect(getMock).toHaveBeenCalledTimes(1)
    expect(checkMock).toHaveBeenCalledTimes(4)
  })

  it("sends hydrated prefs with each per-channel request", async () => {
    getMock.mockResolvedValue({
      configured: true,
      sources: {
        pip_index_url: "https://pypi.tuna.tsinghua.edu.cn/simple",
        pytorch_index_url: "https://mirrors.aliyun.com/pytorch-wheels",
        hf_endpoint: "https://hf-mirror.com",
        github_url_prefix: "https://ghfast.top/",
        proxy_url: null,
      },
    })
    const store = useDownloadSourcesStore()
    await store.ensureLoaded()
    await store.checkAll()
    expect(checkMock).toHaveBeenCalledWith(
      {
        pip_index_url: "https://pypi.tuna.tsinghua.edu.cn/simple",
        pytorch_index_url: "https://mirrors.aliyun.com/pytorch-wheels",
        hf_endpoint: "https://hf-mirror.com",
        github_url_prefix: "https://ghfast.top/",
      },
      "pip",
    )
  })

  it("marks a channel fail when its probe request fails", async () => {
    checkMock.mockRejectedValue(new Error("network down"))
    const store = useDownloadSourcesStore()
    await store.checkAll()
    expect(store.statusFor("pip")).toBe("fail")
    expect(store.resultFor("pip")?.error).toContain("network down")
    expect(store.checking).toBe(false)
  })

  it("a stale overlapping check cannot overwrite the latest result", async () => {
    const staleResolvers = new Map<string, (value: unknown) => void>()
    let call = 0
    checkMock.mockImplementation((_payload: unknown, channel: string) => {
      call += 1
      return call <= 4
        ? new Promise((resolve) => { staleResolvers.set(channel, resolve) })
        : Promise.resolve(channelResult(channel, 55))
    })
    const store = useDownloadSourcesStore()
    const stale = store.checkAll()
    const fresh = store.checkAll()
    await fresh
    for (const channel of SOURCE_CHANNELS) {
      staleResolvers.get(channel)?.({ [channel]: { ok: false, status: null, latency_ms: null, url: "", error: "stale" } })
    }
    await stale
    expect(store.resultFor("pip")?.latency_ms).toBe(55)
    expect(store.statusFor("pip")).toBe("ok")
    expect(store.checking).toBe(false)
  })
})
