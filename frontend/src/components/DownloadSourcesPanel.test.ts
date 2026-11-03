// @vitest-environment jsdom
import { createPinia, setActivePinia } from "pinia"
import { flushPromises, mount } from "@vue/test-utils"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import DownloadSourcesPanel from "./DownloadSourcesPanel.vue"
import { i18n } from "../i18n"
import { DOWNLOAD_SOURCES_KEY } from "../engines/downloadSources"

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

const OK = { ok: true, status: 200, latency_ms: 88, url: "https://example.com", error: null }

const CHINA_SOURCES = {
  pip_index_url: "https://pypi.tuna.tsinghua.edu.cn/simple",
  pytorch_index_url: "https://mirrors.aliyun.com/pytorch-wheels",
  hf_endpoint: "https://hf-mirror.com",
  github_url_prefix: "https://ghfast.top/",
  proxy_url: null,
}

beforeEach(() => {
  setActivePinia(createPinia())
  localStorage.removeItem(DOWNLOAD_SOURCES_KEY)
  checkMock.mockReset()
  checkMock.mockImplementation((_payload: unknown, channel: string) => Promise.resolve({ [channel]: OK }))
  getMock.mockReset()
  getMock.mockResolvedValue({ configured: false, sources: null })
  saveMock.mockReset()
  saveMock.mockResolvedValue({ configured: true, sources: CHINA_SOURCES })
})

afterEach(() => {
  document.body.innerHTML = ""
})

function sheetButton(text: string): HTMLButtonElement {
  const button = [...document.querySelectorAll<HTMLButtonElement>(".ds-sheet-foot button")].find((b) =>
    b.textContent?.includes(text),
  )
  if (!button) throw new Error(`sheet button not found: ${text}`)
  return button
}

describe("DownloadSourcesPanel connectivity check", () => {
  it("checks the unsaved draft and shows per-channel latency inline", async () => {
    getMock.mockResolvedValue({ configured: true, sources: CHINA_SOURCES })
    const wrapper = mount(DownloadSourcesPanel, { attachTo: document.body, global: { plugins: [i18n] } })
    await flushPromises()

    expect(wrapper.find(".ds-inline").exists()).toBe(true)
    expect(wrapper.find(".ds-modal-backdrop").exists()).toBe(false)

    sheetButton("检测全部源").click()
    await flushPromises()

    expect(checkMock).toHaveBeenCalledTimes(4)
    expect(checkMock).toHaveBeenCalledWith(
      {
        pip_index_url: "https://pypi.tuna.tsinghua.edu.cn/simple",
        pytorch_index_url: "https://mirrors.aliyun.com/pytorch-wheels",
        hf_endpoint: "https://hf-mirror.com",
        github_url_prefix: "https://ghfast.top/",
      },
      "pip",
    )
    const marks = document.querySelectorAll(".ds-check")
    expect(marks).toHaveLength(4)
    expect(document.querySelector('.ds-check[data-status="ok"]')?.textContent).toContain("88 ms")
    wrapper.unmount()
  })

  it("sends an empty payload for an all-auto draft", async () => {
    const wrapper = mount(DownloadSourcesPanel, { attachTo: document.body, global: { plugins: [i18n] } })
    await flushPromises()

    sheetButton("检测全部源").click()
    await flushPromises()

    expect(checkMock).toHaveBeenCalledTimes(4)
    expect(checkMock).toHaveBeenCalledWith({}, "pip")
    wrapper.unmount()
  })

  it("persists the draft to the backend on save", async () => {
    getMock.mockResolvedValue({ configured: true, sources: CHINA_SOURCES })
    const wrapper = mount(DownloadSourcesPanel, { attachTo: document.body, global: { plugins: [i18n] } })
    await flushPromises()

    sheetButton("保存下载源").click()
    await flushPromises()

    expect(saveMock).toHaveBeenCalledWith({
      pip_index_url: "https://pypi.tuna.tsinghua.edu.cn/simple",
      pytorch_index_url: "https://mirrors.aliyun.com/pytorch-wheels",
      hf_endpoint: "https://hf-mirror.com",
      github_url_prefix: "https://ghfast.top/",
    })
    wrapper.unmount()
  })
})
