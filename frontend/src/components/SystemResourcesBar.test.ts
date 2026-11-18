// @vitest-environment jsdom
import { flushPromises, mount } from "@vue/test-utils"
import { afterEach, expect, it, vi } from "vitest"
import { i18n } from "../i18n"
import { systemApi } from "../api/system"
import SystemResourcesBar from "./SystemResourcesBar.vue"

afterEach(() => { vi.restoreAllMocks() })

it("renders gpu and ram summaries from the system resources API", async () => {
  vi.spyOn(systemApi, "resources").mockResolvedValue({
    gpu: { name: "RTX", vram_used_mb: 4096, vram_total_mb: 24576, gpu_load: 20 },
    ram: { used_mb: 16384, total_mb: 65536, percent: 25 },
  })
  const wrapper = mount(SystemResourcesBar, { global: { plugins: [i18n] } })
  await flushPromises()

  const bar = wrapper.get('[data-testid="system-resources-bar"]')
  expect(bar.text()).toContain("显存 4.0 / 24 GB")
  expect(bar.text()).toContain("内存 16 / 64 GB")
  wrapper.unmount()
})

it("stays hidden when neither gpu nor ram is available", async () => {
  vi.spyOn(systemApi, "resources").mockResolvedValue({ gpu: null, ram: null })
  const wrapper = mount(SystemResourcesBar, { global: { plugins: [i18n] } })
  await flushPromises()
  expect(wrapper.find('[data-testid="system-resources-bar"]').exists()).toBe(false)
  wrapper.unmount()
})

it("marks nearly-full meters as high pressure", async () => {
  vi.spyOn(systemApi, "resources").mockResolvedValue({
    gpu: { name: "RTX", vram_used_mb: 23000, vram_total_mb: 24576, gpu_load: 90 },
    ram: { used_mb: 8000, total_mb: 65536, percent: 12 },
  })
  const wrapper = mount(SystemResourcesBar, { global: { plugins: [i18n] } })
  await flushPromises()
  const meters = wrapper.findAll(".system-resource")
  expect(meters[0].attributes("data-level")).toBe("high")
  expect(meters[1].attributes("data-level")).toBe("ok")
  wrapper.unmount()
})
