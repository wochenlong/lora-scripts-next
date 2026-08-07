// @vitest-environment jsdom
import { flushPromises, mount } from "@vue/test-utils"
import { beforeEach, describe, expect, it, vi } from "vitest"
import ModelAssetsTools from "./ModelAssetsTools.vue"
import { assetsApi, type AssetItem } from "../api/assets"
import { i18n } from "../i18n"

vi.mock("../api/assets", () => ({
  assetsApi: { check: vi.fn(), download: vi.fn() },
}))

const check = vi.mocked(assetsApi.check)
const download = vi.mocked(assetsApi.download)

function asset(partial: Partial<AssetItem>): AssetItem {
  return { key: "dit", label: "DiT", path: "/x/dit.safetensors", exists: false, optional: false, sources: { huggingface: true, modelscope: true }, ...partial }
}

function mountTools() {
  return mount(ModelAssetsTools, {
    props: { schemaName: "krea2-lora", model: { model_train_type: "krea2-lora", dit: "./sd-models/krea2/krea2.safetensors" } },
    global: { plugins: [i18n], stubs: { ElDialog: { props: ["modelValue"], template: '<div v-if="modelValue"><slot /></div>' } } },
  })
}

describe("ModelAssetsTools", () => {
  beforeEach(() => {
    check.mockReset()
    download.mockReset()
  })

  it("renders nothing when the train type has no manifest", async () => {
    check.mockResolvedValue({ train_type: "sd15-lora", items: [] })
    const wrapper = mountTools()
    await flushPromises()
    expect(wrapper.find(".model-assets-tools").exists()).toBe(false)
  })

  it("shows missing count after checking", async () => {
    check.mockResolvedValue({ train_type: "krea2-lora", items: [asset({}), asset({ key: "vae", exists: true })] })
    const wrapper = mountTools()
    await flushPromises()
    expect(wrapper.text()).toContain("1 项缺失")
  })

  it("starts a download task with the chosen source", async () => {
    check.mockResolvedValue({ train_type: "krea2-lora", items: [asset({})] })
    download.mockResolvedValue({ task_id: "t-1", log_stream: "/api/train/log/stream/t-1" })
    const wrapper = mountTools()
    await flushPromises()
    await wrapper.findAll(".model-assets-tools button")[1].trigger("click")
    await flushPromises()
    const buttons = wrapper.findAll(".assets-actions button")
    await buttons[0].trigger("click")
    await flushPromises()
    expect(download).toHaveBeenCalledWith("krea2-lora", expect.anything(), [{ key: "dit", path: "/x/dit.safetensors" }], "modelscope")
  })
})
