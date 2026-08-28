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
    ...overrides,
  }
}

beforeEach(() => {
  setActivePinia(createPinia())
  i18n.global.locale.value = "zh-CN"
  vi.spyOn(pluginsApi, "ensureHostAuthority").mockResolvedValue()
  vi.spyOn(pluginsApi, "listMarketplacePlugins").mockResolvedValue([status()])
  vi.spyOn(pluginsApi, "listMarketplaceCatalog").mockResolvedValue([])
  vi.spyOn(pluginsApi, "installMarketplacePlugin").mockResolvedValue(status({ state: "installed", active_version: "1.2.0" }))
  vi.spyOn(pluginsApi, "enableMarketplacePlugin").mockResolvedValue(status({ state: "enabled", active_version: "1.2.0", enabled: true }))
  vi.spyOn(pluginsApi, "disableMarketplacePlugin").mockResolvedValue(status({ state: "installed", active_version: "1.2.0" }))
})

describe("MarketplaceSettingsPage", () => {
  it("renders catalog metadata and installs with declared permissions auto-approved", async () => {
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
    // The permission-approval bar is gone: install is enabled immediately
    // and no permission checkboxes are rendered.
    expect(install.attributes("disabled")).toBeUndefined()
    expect(wrapper.findAll('input[type="checkbox"]')).toHaveLength(0)
    wrapper.unmount()
  })

  it("renders the live catalog and allows zero-permission plugins to install immediately", async () => {
    const zeroPermissionEntry: MarketplaceEntry = {
      ...entry,
      id: "next-trainer-pi-agent",
      name: "Next Trainer Agent (pi-web)",
      permissions_summary: [],
    }
    vi.mocked(pluginsApi.listMarketplaceCatalog).mockResolvedValueOnce([zeroPermissionEntry])
    vi.mocked(pluginsApi.listMarketplacePlugins).mockResolvedValueOnce([
      status({ id: "next-trainer-pi-agent" }),
    ])
    const wrapper = mount(MarketplaceSettingsPage, {
      global: { plugins: [i18n] },
    })
    await flushPromises()

    expect(wrapper.text()).toContain("Next Trainer Agent (pi-web)")
    // No catalog notice: the live catalog answered.
    expect(wrapper.find(".marketplace-notice").exists()).toBe(false)
    const install = wrapper.get("button.primary-action")
    expect(install.text()).toContain("安装")
    expect(install.attributes("disabled")).toBeUndefined()
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
})
