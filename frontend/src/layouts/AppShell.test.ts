// @vitest-environment jsdom
import { flushPromises, mount } from "@vue/test-utils"
import { createPinia } from "pinia"
import { createMemoryHistory, createRouter } from "vue-router"
import { afterEach, expect, it, vi } from "vitest"
import AppShell from "./AppShell.vue"
import { i18n } from "../i18n"
import { loadEngineSettings } from "../engines/settings"
import { writeRecentTrainingSelection } from "../training/recent"
import { ref } from "vue"

vi.mock("../stores/app", () => ({ useAppStore: () => ({ version: ref(""), loadVersion: vi.fn() }) }))
vi.mock("../stores/tasks", () => ({ useTasksStore: () => ({
  showNavBadge: ref(false), navBadgeCount: ref(0), activeCount: ref(0), refresh: vi.fn(), clearAttention: vi.fn(),
}) }))
afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })

it("does not turn old browser engine selections into explicit navigation overrides", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
    status: "success", data: { schema_version: 1, revision: 1, engine_prefs: { defaultEngine: "ai-toolkit", rememberLast: true } },
  }))))
  await loadEngineSettings()
  writeRecentTrainingSelection({ model: "anima", engine: "kohya", target: "lora" })
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: "/:pathMatch(.*)*", component: { template: "<div />" } },
  ] })
  await router.push("/settings")
  const wrapper = mount(AppShell, { global: {
    plugins: [createPinia(), i18n, router],
    stubs: { GenericFloatingExtensionHost: true, "el-icon": true, "el-button": true },
  } })
  try {
    await flushPromises()
    expect(wrapper.get(".navigation a").attributes("href")).toBe("/training")
  } finally { wrapper.unmount() }
})
