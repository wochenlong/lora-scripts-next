// @vitest-environment jsdom
import { mount } from "@vue/test-utils"
import { beforeEach, describe, expect, it, vi } from "vitest"
import DownloadSourcesPanel from "./DownloadSourcesPanel.vue"
import {
  DOWNLOAD_SOURCES_KEY,
  chinaDownloadSources,
  defaultDownloadSources,
  readDownloadSources,
} from "../engines/downloadSources"

vi.mock("vue-i18n", () => ({ useI18n: () => ({ t: (key: string) => key }) }))
vi.mock("element-plus", () => ({ ElMessage: { success: vi.fn(), error: vi.fn() } }))

describe("DownloadSourcesPanel", () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it("shows a settings card with channel summary when not compact", () => {
    const wrapper = mount(DownloadSourcesPanel)
    expect(wrapper.find('[data-testid="download-sources-card"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="download-sources-summary"]').text()).toContain("https://pypi.org/simple")
    expect(wrapper.get('[data-testid="download-sources-summary"]').text()).toContain("https://huggingface.co")
    expect(wrapper.find(".ds-compact").exists()).toBe(false)
    wrapper.unmount()
  })

  it("writes the china preset to localStorage when selected", async () => {
    const wrapper = mount(DownloadSourcesPanel)
    await wrapper.get('[data-testid="download-sources-preset-china"]').trigger("click")
    expect(readDownloadSources()).toEqual(chinaDownloadSources())
    expect(wrapper.get('[data-testid="download-sources-summary"]').text()).toContain("https://hf-mirror.com")
    wrapper.unmount()
  })

  it("keeps only region presets and marks custom via per-channel edits", async () => {
    localStorage.setItem(DOWNLOAD_SOURCES_KEY, JSON.stringify(defaultDownloadSources()))
    const wrapper = mount(DownloadSourcesPanel)
    expect(wrapper.find('[data-testid="download-sources-preset-custom"]').exists()).toBe(false)
    await wrapper.get('[data-testid="download-sources-channels-toggle"]').trigger("click")
    await wrapper.get('[data-testid="download-sources-hf"]').setValue("hf-mirror")
    expect(wrapper.get('[data-testid="download-sources-preset-note"]').attributes("data-custom")).toBe("true")
    expect(wrapper.get('[data-testid="download-sources-preset-official"]').classes()).not.toContain("selected")
    await wrapper.get("form.ds-channels-form").trigger("submit")
    expect(readDownloadSources().preset).toBe("custom")
    expect(readDownloadSources().huggingface.choice).toBe("hf-mirror")
    wrapper.unmount()
  })
})
