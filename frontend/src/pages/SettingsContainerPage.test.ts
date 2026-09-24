// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest"
import { mount } from "@vue/test-utils"
import { createPinia } from "pinia"
import { i18n, UI_CONFIGS_KEY } from "../i18n"

vi.mock("element-plus", async (importOriginal) => {
  const original = await importOriginal<typeof import("element-plus")>()
  return { ...original, ElMessage: { success: vi.fn() } }
})
vi.mock("./AboutPage.vue", () => ({ default: { template: "<div />" } }))
vi.mock("./ChangelogPage.vue", () => ({ default: { template: "<div />" } }))
vi.mock("./EnginesSettingsPage.vue", () => ({ default: { template: "<div />" } }))
vi.mock("./MarketplaceSettingsPage.vue", () => ({ default: { template: "<div />" } }))
vi.mock("./UpdateSettingsPage.vue", () => ({ default: { template: "<div />" } }))

import SettingsContainerPage from "./SettingsContainerPage.vue"

function mountPage() {
  return mount(SettingsContainerPage, {
    props: { tab: "ui" },
    global: {
      plugins: [i18n, createPinia()],
      stubs: {
        RouterLink: { template: "<a><slot /></a>" },
        AboutPage: true,
        ChangelogPage: true,
        EnginesSettingsPage: true,
        MarketplaceSettingsPage: true,
        UpdateSettingsPage: true,
      },
    },
  })
}

describe("SettingsContainerPage path picker preference", () => {
  beforeEach(() => localStorage.clear())

  it("shows the stored picker preference", () => {
    localStorage.setItem(UI_CONFIGS_KEY, JSON.stringify({ path_picker: "web" }))

    const wrapper = mountPage()

    expect(wrapper.get('[data-testid="path-picker-web"]').classes()).toContain("active")
    expect(wrapper.get('[data-testid="path-picker-web"]').text()).toBe("Linux")
    expect(wrapper.get('[data-testid="path-picker-native"]').text()).toBe("Windows")
    expect(wrapper.get('[data-testid="path-picker-auto"]').text()).toContain("推荐")
    expect(wrapper.get('[data-testid="path-picker-auto"]').classes()).not.toContain("active")
  })

  it("saves the selected picker preference with existing UI settings", async () => {
    localStorage.setItem(UI_CONFIGS_KEY, JSON.stringify({ language: "zh-CN" }))
    const wrapper = mountPage()

    await wrapper.get('[data-testid="path-picker-native"]').trigger("click")
    await wrapper.get('[data-testid="settings-save"]').trigger("click")

    expect(JSON.parse(localStorage.getItem(UI_CONFIGS_KEY) || "{}")).toMatchObject({
      language: "zh-CN",
      path_picker: "native",
    })
  })

  it("resets the picker preference to auto", async () => {
    localStorage.setItem(UI_CONFIGS_KEY, JSON.stringify({ path_picker: "web" }))
    const wrapper = mountPage()

    await wrapper.get('[data-testid="settings-reset"]').trigger("click")

    expect(wrapper.get('[data-testid="path-picker-auto"]').classes()).toContain("active")
    expect(JSON.parse(localStorage.getItem(UI_CONFIGS_KEY) || "{}").path_picker).toBe("auto")
  })
})
