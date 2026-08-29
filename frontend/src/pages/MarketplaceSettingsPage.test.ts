// @vitest-environment jsdom
import { createPinia, setActivePinia } from "pinia"
import { flushPromises, mount } from "@vue/test-utils"
import { beforeEach, describe, expect, it, vi } from "vitest"
import MarketplaceSettingsPage from "./MarketplaceSettingsPage.vue"
import {
  pluginsApi,
  type MarketplaceEntry,
  type MarketplaceInstallOperation,
  type MarketplacePluginStatus,
} from "../api/plugins"
import { i18n } from "../i18n"
import { scheduleHostRefresh } from "../extensions/hostRefresh"

// The page reloads the host shell after a successful install/uninstall so the
// plugin panel mounts/tears down cleanly; assert the schedule call instead of
// triggering a real jsdom reload.
vi.mock("../extensions/hostRefresh", () => ({ scheduleHostRefresh: vi.fn() }))

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

function operation(
  overrides: Partial<MarketplaceInstallOperation> = {},
): MarketplaceInstallOperation {
  return {
    operationId: "op-test",
    pluginId: "sample-plugin",
    version: "1.2.0",
    state: "running",
    phase: "acquiring",
    progress: { current: 0, total: 0, percent: null },
    errorCode: null,
    errorMessage: null,
    status: null,
    startedAt: "2026-08-29T00:00:00Z",
    finishedAt: null,
    ...overrides,
  }
}

beforeEach(() => {
  setActivePinia(createPinia())
  i18n.global.locale.value = "zh-CN"
  vi.spyOn(pluginsApi, "ensureHostAuthority").mockResolvedValue()
  vi.spyOn(pluginsApi, "listMarketplacePlugins").mockResolvedValue([status()])
  vi.spyOn(pluginsApi, "listMarketplaceCatalog").mockResolvedValue([])
  vi.spyOn(pluginsApi, "installMarketplacePlugin").mockResolvedValue(operation())
  vi.spyOn(pluginsApi, "refreshMarketplaceCatalog").mockResolvedValue(1)
  // Default: the stream resolves immediately at a terminal snapshot so tests
  // that do not exercise progress settle without real timers.
  vi.spyOn(pluginsApi, "streamInstallOperation").mockImplementation(
    async (_pluginId, _operationId, onSnapshot) => {
      onSnapshot(
        operation({
          state: "succeeded",
          phase: "done",
          progress: { current: 1, total: 1, percent: 100 },
          status: status({ state: "installed", active_version: "1.2.0" }),
        }),
      )
    },
  )
  vi.spyOn(pluginsApi, "getInstallOperation").mockResolvedValue(
    operation({
      state: "succeeded",
      phase: "done",
      status: status({ state: "installed", active_version: "1.2.0" }),
    }),
  )
  vi.spyOn(pluginsApi, "enableMarketplacePlugin").mockResolvedValue(status({ state: "enabled", active_version: "1.2.0", enabled: true }))
  vi.spyOn(pluginsApi, "disableMarketplacePlugin").mockResolvedValue(status({ state: "installed", active_version: "1.2.0" }))
  vi.spyOn(pluginsApi, "uninstallMarketplacePlugin").mockResolvedValue(status())
  vi.mocked(scheduleHostRefresh).mockClear()
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

  it("follows the install operation, shows progress, and lands on installed", async () => {
    const { ElMessageBox } = await import("element-plus")
    vi.spyOn(ElMessageBox, "confirm").mockResolvedValue(
      "confirm" as Awaited<ReturnType<typeof ElMessageBox.confirm>>,
    )
    // Hold the stream open until the assertions below release it, so the
    // progress block is observable while the operation is running.
    let releaseStream: () => void = () => {}
    const streamGate = new Promise<void>((resolve) => {
      releaseStream = resolve
    })
    const snapshots: Array<{ state: string; phase: string }> = []
    vi.mocked(pluginsApi.streamInstallOperation).mockImplementation(
      async (_pluginId, _operationId, onSnapshot) => {
        const running = operation({
          phase: "acquiring",
          progress: { current: 512 * 1024, total: 1024 * 1024, percent: 50 },
        })
        onSnapshot(running)
        snapshots.push({ state: running.state, phase: running.phase })
        await streamGate
        onSnapshot(
          operation({
            state: "succeeded",
            phase: "done",
            progress: { current: 1024 * 1024, total: 1024 * 1024, percent: 100 },
            status: status({ state: "installed", active_version: "1.2.0" }),
          }),
        )
      },
    )
    vi.mocked(pluginsApi.listMarketplacePlugins)
      .mockResolvedValueOnce([status()])
      .mockResolvedValueOnce([status({ state: "installed", active_version: "1.2.0" })])

    const wrapper = mount(MarketplaceSettingsPage, {
      props: { catalogEntries: [entry] },
      global: { plugins: [i18n] },
    })
    await flushPromises()
    await wrapper.get("button.primary-action").trigger("click")
    await flushPromises()
    // While the stream is active the progress block renders the phase label
    // and the byte counter.
    const progress = wrapper.find(".marketplace-install-progress")
    expect(progress.exists()).toBe(true)
    expect(progress.text()).toContain("正在获取安装包")
    expect(progress.text()).toContain("512.0 KB")
    expect(progress.find("button").text()).toContain("取消安装")
    releaseStream()
    await flushPromises()

    // The operation settled: progress block is gone, detail shows installed.
    expect(wrapper.find(".marketplace-install-progress").exists()).toBe(false)
    expect(wrapper.find("button.primary-action").text()).toContain("启用")
    expect(wrapper.find("i[data-state='installed']").exists()).toBe(true)
    expect(snapshots).toEqual([{ state: "running", phase: "acquiring" }])
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

  it("recovers a cold OFFLINE catalog by polling the channel once", async () => {
    // Fresh host: GET /catalog answers OFFLINE until the channel is polled.
    // load() must trigger refreshMarketplaceCatalog and re-read, so a new user
    // sees the installable listing instead of a silently empty catalog.
    vi.mocked(pluginsApi.listMarketplaceCatalog)
      .mockRejectedValueOnce(new Error("MARKETPLACE_CATALOG_OFFLINE"))
      .mockResolvedValueOnce([entry])
    const wrapper = mount(MarketplaceSettingsPage, {
      global: { plugins: [i18n] },
    })
    await flushPromises()

    expect(pluginsApi.refreshMarketplaceCatalog).toHaveBeenCalledTimes(1)
    expect(wrapper.find(".marketplace-notice").exists()).toBe(false)
    expect(wrapper.get("button.primary-action").text()).toContain("安装")
    wrapper.unmount()
  })

  it("reloads the host after a successful install so the plugin panel mounts", async () => {
    const { ElMessageBox } = await import("element-plus")
    vi.spyOn(ElMessageBox, "confirm").mockResolvedValue(
      "confirm" as Awaited<ReturnType<typeof ElMessageBox.confirm>>,
    )
    vi.mocked(pluginsApi.listMarketplacePlugins)
      .mockResolvedValueOnce([status()])
      .mockResolvedValueOnce([status({ state: "installed", active_version: "1.2.0" })])
    const wrapper = mount(MarketplaceSettingsPage, {
      props: { catalogEntries: [entry] },
      global: { plugins: [i18n] },
    })
    await flushPromises()
    await wrapper.get("button.primary-action").trigger("click")
    await flushPromises()

    // Default beforeEach stream settles at succeeded → the install schedules a
    // host reload so the floating panel mounts fresh (no stale "not ready").
    expect(scheduleHostRefresh).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it("reloads the host after a successful uninstall so no plugin UI lingers", async () => {
    const { ElMessageBox } = await import("element-plus")
    vi.spyOn(ElMessageBox, "confirm").mockResolvedValue(
      "confirm" as Awaited<ReturnType<typeof ElMessageBox.confirm>>,
    )
    vi.mocked(pluginsApi.listMarketplacePlugins).mockResolvedValueOnce([
      status({ state: "enabled", active_version: "1.2.0", enabled: true }),
    ])
    const wrapper = mount(MarketplaceSettingsPage, {
      props: { catalogEntries: [entry] },
      global: { plugins: [i18n] },
    })
    await flushPromises()

    const uninstall = wrapper.get("button.danger-action")
    expect(uninstall.text()).toContain("卸载")
    await uninstall.trigger("click")
    await flushPromises()

    expect(pluginsApi.uninstallMarketplacePlugin).toHaveBeenCalledWith("sample-plugin")
    expect(scheduleHostRefresh).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it("does not reload the host when uninstall fails", async () => {
    const { ElMessageBox } = await import("element-plus")
    vi.spyOn(ElMessageBox, "confirm").mockResolvedValue(
      "confirm" as Awaited<ReturnType<typeof ElMessageBox.confirm>>,
    )
    vi.mocked(pluginsApi.listMarketplacePlugins).mockResolvedValueOnce([
      status({ state: "enabled", active_version: "1.2.0", enabled: true }),
    ])
    vi.mocked(pluginsApi.uninstallMarketplacePlugin).mockRejectedValueOnce(new Error("busy"))
    const wrapper = mount(MarketplaceSettingsPage, {
      props: { catalogEntries: [entry] },
      global: { plugins: [i18n] },
    })
    await flushPromises()

    await wrapper.get("button.danger-action").trigger("click")
    await flushPromises()

    expect(scheduleHostRefresh).not.toHaveBeenCalled()
    expect(wrapper.find(".marketplace-error").exists()).toBe(true)
    wrapper.unmount()
  })

  it("shows busy progress while enabling and reloads the host when done", async () => {
    const { ElMessageBox } = await import("element-plus")
    vi.spyOn(ElMessageBox, "confirm").mockResolvedValue(
      "confirm" as Awaited<ReturnType<typeof ElMessageBox.confirm>>,
    )
    vi.mocked(pluginsApi.listMarketplacePlugins).mockResolvedValueOnce([
      status({ state: "installed", active_version: "1.2.0" }),
    ])
    // Enable blocks server-side until the plugin runtime boots; hold it so the
    // busy strip is observable — the user-reported "click enable, nothing
    // happens" window.
    let releaseEnable: () => void = () => {}
    const gate = new Promise<void>((resolve) => {
      releaseEnable = resolve
    })
    vi.mocked(pluginsApi.enableMarketplacePlugin).mockImplementation(async () => {
      await gate
      return status({ state: "enabled", active_version: "1.2.0", enabled: true })
    })
    const wrapper = mount(MarketplaceSettingsPage, {
      props: { catalogEntries: [entry] },
      global: { plugins: [i18n] },
    })
    await flushPromises()

    const enable = wrapper.get("button.primary-action")
    expect(enable.text()).toContain("启用")
    await enable.trigger("click")
    await flushPromises()

    const busy = wrapper.find("[data-test='busy-progress']")
    expect(busy.exists()).toBe(true)
    expect(busy.text()).toContain("正在启用插件")
    expect(busy.text()).toContain("已耗时")
    // The action bar is inert while an operation runs (no double submits).
    expect(wrapper.get("button.primary-action").attributes("disabled")).toBeDefined()

    releaseEnable()
    await flushPromises()
    expect(wrapper.find("[data-test='busy-progress']").exists()).toBe(false)
    // Enable also reloads the host: the floating panel must mount fresh.
    expect(scheduleHostRefresh).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it("surfaces an enable failure as a toast and does not reload", async () => {
    const { ElMessage, ElMessageBox } = await import("element-plus")
    const errorToast = vi.spyOn(ElMessage, "error").mockImplementation(() => ({ close: () => {} }) as never)
    vi.spyOn(ElMessageBox, "confirm").mockResolvedValue(
      "confirm" as Awaited<ReturnType<typeof ElMessageBox.confirm>>,
    )
    vi.mocked(pluginsApi.listMarketplacePlugins).mockResolvedValueOnce([
      status({ state: "installed", active_version: "1.2.0" }),
    ])
    vi.mocked(pluginsApi.enableMarketplacePlugin).mockRejectedValueOnce(
      new Error("plugin runtime failed to start"),
    )
    const wrapper = mount(MarketplaceSettingsPage, {
      props: { catalogEntries: [entry] },
      global: { plugins: [i18n] },
    })
    await flushPromises()

    await wrapper.get("button.primary-action").trigger("click")
    await flushPromises()

    expect(errorToast).toHaveBeenCalledWith("plugin runtime failed to start")
    expect(wrapper.find(".marketplace-error").text()).toContain("plugin runtime failed to start")
    expect(wrapper.find("[data-test='busy-progress']").exists()).toBe(false)
    expect(scheduleHostRefresh).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
