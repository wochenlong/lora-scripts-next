// @vitest-environment jsdom
import { createPinia, setActivePinia } from "pinia"
import { flushPromises, mount } from "@vue/test-utils"
import { beforeEach, describe, expect, it, vi } from "vitest"
import MarketplaceSettingsPage from "./MarketplaceSettingsPage.vue"
import {
  pluginsApi,
  type MarketplaceEntry,
  type MarketplacePluginStatus,
} from "../api/plugins"
import { i18n } from "../i18n"

const entry: MarketplaceEntry = {
  id: "sample-plugin",
  name: "Sample Assistant",
  publisher_id: "approved-publisher",
  description: "A generic extension.",
  icon: null,
  latest_version: "1.2.0",
  channel: "stable",
  host_compatibility: ">=2.9.2 <3.0.0",
  platforms: ["win32-x64"],
  package_size: 1024 * 1024,
  permissions_summary: ["model-provider", "training-config"],
  license: "MIT",
  release_notes_url: null,
  package_url: "https://market.example/sample.zip",
  sha256: "a".repeat(64),
  signature: "b".repeat(64),
  signing_key_id: "test-key",
  published_at: "2026-08-21T00:00:00Z",
}

function status(overrides: Partial<MarketplacePluginStatus> = {}): MarketplacePluginStatus {
  return {
    id: "sample-plugin",
    state: "not_installed",
    active_version: null,
    previous_version: null,
    enabled: false,
    installed_versions: [],
    reason: "",
    runtime_state: null,
    runtime_pid: null,
    granted_permissions: [],
    ...overrides,
  }
}

beforeEach(() => {
  setActivePinia(createPinia())
  i18n.global.locale.value = "zh-CN"
  vi.spyOn(pluginsApi, "ensureHostAuthority").mockResolvedValue()
  vi.spyOn(pluginsApi, "listMarketplacePlugins").mockResolvedValue([status()])
  vi.spyOn(pluginsApi, "refreshCatalog").mockResolvedValue([])
  vi.spyOn(pluginsApi, "reloadCatalog").mockResolvedValue([entry])
  vi.spyOn(pluginsApi, "installMarketplacePlugin").mockResolvedValue(status({ state: "installed", active_version: "1.2.0" }))
  vi.spyOn(pluginsApi, "enableMarketplacePlugin").mockResolvedValue(status({ state: "enabled", active_version: "1.2.0", enabled: true }))
  vi.spyOn(pluginsApi, "disableMarketplacePlugin").mockResolvedValue(status({ state: "installed", active_version: "1.2.0" }))
})

describe("MarketplaceSettingsPage", () => {
  it("renders catalog metadata and requires every declared permission before install", async () => {
    const wrapper = mount(MarketplaceSettingsPage, {
      props: { catalogEntries: [entry] },
      global: { plugins: [i18n] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain("Sample Assistant")
    expect(wrapper.text()).toContain("approved-publisher")
    expect(wrapper.text()).toContain("1.0 MB")
    expect(wrapper.text()).toContain("宿主兼容性")
    const install = wrapper.get("button.primary-action")
    expect(install.text()).toContain("安装")
    expect(install.attributes("disabled")).toBeDefined()

    const checkboxes = wrapper.findAll<HTMLInputElement>('input[type="checkbox"]')
    expect(checkboxes).toHaveLength(2)
    await checkboxes[0].setValue(true)
    expect(install.attributes("disabled")).toBeDefined()
    await checkboxes[1].setValue(true)
    expect(install.attributes("disabled")).toBeUndefined()
    wrapper.unmount()
  })

  it("forces a trusted source refresh when the user refreshes the marketplace", async () => {
    const wrapper = mount(MarketplaceSettingsPage, {
      props: { catalogEntries: [entry] },
      global: { plugins: [i18n] },
    })
    await flushPromises()

    await wrapper.get('button[aria-label="刷新插件状态"]').trigger("click")
    await flushPromises()
    expect(pluginsApi.reloadCatalog).toHaveBeenCalledOnce()
    wrapper.unmount()
  })

  it("shows generic installed lifecycle actions and does not expose internal status detail", async () => {
    vi.mocked(pluginsApi.listMarketplacePlugins).mockResolvedValueOnce([
      status({ state: "runtime_error", active_version: "1.2.0", enabled: true, reason: "C:/private/auth.json" }),
    ])
    const wrapper = mount(MarketplaceSettingsPage, {
      props: { catalogEntries: [entry] },
      global: { plugins: [i18n] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain("禁用")
    expect(wrapper.text()).toContain("重新启动")
    expect(wrapper.text()).not.toContain("auth.json")
    wrapper.unmount()
  })

  it("shows persisted permission grants for an enabled plugin", async () => {
    vi.mocked(pluginsApi.listMarketplacePlugins).mockResolvedValueOnce([
      status({
        state: "enabled",
        active_version: "1.1.0",
        enabled: true,
        granted_permissions: ["model-provider", "training-config"],
      }),
    ])
    const wrapper = mount(MarketplaceSettingsPage, {
      props: { catalogEntries: [entry] },
      global: { plugins: [i18n] },
    })
    await flushPromises()

    const checkboxes = wrapper.findAll<HTMLInputElement>('input[type="checkbox"]')
    expect(checkboxes).toHaveLength(2)
    expect(checkboxes.every((checkbox) => checkbox.element.checked)).toBe(true)
    expect(checkboxes.every((checkbox) => checkbox.attributes("disabled") !== undefined)).toBe(true)
    expect(wrapper.get("button.primary-action").text()).toContain("更新")
    wrapper.unmount()
  })
})
