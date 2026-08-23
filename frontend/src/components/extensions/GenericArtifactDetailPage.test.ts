// @vitest-environment jsdom
import { flushPromises, mount } from "@vue/test-utils"
import { defineComponent } from "vue"
import { createMemoryHistory, createRouter } from "vue-router"
import { afterEach, describe, expect, it, vi } from "vitest"
import GenericArtifactDetailPage from "./GenericArtifactDetailPage.vue"
import { pluginsApi } from "../../api/plugins"
import { i18n } from "../../i18n"

vi.mock("../../api/plugins", async (importOriginal) => {
  const original = await importOriginal<typeof import("../../api/plugins")>()
  return { ...original, pluginsApi: { ...original.pluginsApi, getArtifact: vi.fn() } }
})

const getArtifact = vi.mocked(pluginsApi.getArtifact)

async function mountPage() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: "/plugins/:pluginId/artifacts/:artifactId", component: GenericArtifactDetailPage }],
  })
  await router.push("/plugins/sample-plugin/artifacts/artifact-1")
  await router.isReady()
  const wrapper = mount(defineComponent({ template: "<RouterView />" }), { global: { plugins: [router, i18n] } })
  await flushPromises()
  return wrapper
}

afterEach(() => {
  getArtifact.mockReset()
})

describe("GenericArtifactDetailPage", () => {
  it("loads a logical artifact and exposes only a host-owned download URL", async () => {
    getArtifact.mockResolvedValue({
      pluginId: "sample-plugin",
      artifactId: "artifact-1",
      title: "Training config",
      kind: "training-config",
      status: "available",
      summary: "Validated configuration",
      downloadUrl: "/api/plugin-host/artifacts/sample-plugin/artifact-1/download",
    })
    const wrapper = await mountPage()
    expect(getArtifact).toHaveBeenCalledWith("sample-plugin", "artifact-1")
    expect(wrapper.text()).toContain("Training config")
    expect(wrapper.get("a").attributes("href")).toBe("/api/plugin-host/artifacts/sample-plugin/artifact-1/download")
    wrapper.unmount()
  })

  it("does not render an external download URL", async () => {
    getArtifact.mockResolvedValue({
      pluginId: "sample-plugin",
      artifactId: "artifact-1",
      title: "Report",
      kind: "report",
      status: "renderer_unavailable",
      downloadUrl: "https://untrusted.example/report",
    })
    const wrapper = await mountPage()
    expect(wrapper.find("a").exists()).toBe(false)
    wrapper.unmount()
  })

  it("renders a stable error without exposing backend exception details", async () => {
    getArtifact.mockRejectedValue(new Error("C:/Users/name/auth.json contained sk-sensitive"))
    const wrapper = await mountPage()
    expect(wrapper.text()).toContain("制品暂不可用")
    expect(wrapper.text()).not.toContain("auth.json")
    expect(wrapper.text()).not.toContain("sk-sensitive")
    wrapper.unmount()
  })
})
