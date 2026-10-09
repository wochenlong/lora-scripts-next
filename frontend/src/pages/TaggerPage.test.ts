// @vitest-environment jsdom
import { mount } from "@vue/test-utils"
import { createPinia } from "pinia"
import { beforeEach, expect, it, vi } from "vitest"
import { i18n } from "../i18n"
import TaggerPage from "./TaggerPage.vue"

vi.mock("vue-router", () => ({ useRoute: () => ({ query: {} }) }))

beforeEach(() => localStorage.clear())

it("keeps unavailable modes quietly disabled and uses a searchable grouped model selector", async () => {
  const wrapper = mount(TaggerPage, { global: {
    plugins: [createPinia(), i18n], stubs: { ManagedDatasetPicker: true },
  } })
  expect(wrapper.text()).not.toContain("待接入")
  expect(wrapper.find('[data-testid="preview-pending"]').exists()).toBe(false)
  expect(wrapper.find('[data-testid="retry-failed"]').exists()).toBe(false)
  expect(wrapper.find('input[placeholder*="huggingface"]').exists()).toBe(false)
  expect(wrapper.find("aside.tagger-status").exists()).toBe(false)
  const select = wrapper.findComponent({ name: "ElSelect" })
  expect(select.props("filterable")).toBe(true)
  expect(wrapper.findAllComponents({ name: "ElOptionGroup" })).toHaveLength(2)
  await select.vm.$emit("update:modelValue", "wd-eva02-large-tagger-v3")
  expect(select.props("modelValue")).toBe("wd-eva02-large-tagger-v3")
  expect(wrapper.get(".tagger-future").attributes("open")).toBeUndefined()
  expect(wrapper.get("#tagger-parameters").isVisible()).toBe(false)
  await wrapper.get('[data-testid="parameter-toggle"]').trigger("click")
  expect(wrapper.get("#tagger-parameters").isVisible()).toBe(true)
  await wrapper.get('#tagger-parameters input[type="number"]').setValue("0.5")
  await wrapper.get('[data-testid="parameter-close"]').trigger("click")
  await wrapper.get('[data-testid="parameter-toggle"]').trigger("click")
  expect((wrapper.get('#tagger-parameters input[type="number"]').element as HTMLInputElement).value).toBe("0.5")
  wrapper.unmount()
})

it("provides load, save-as-template and reset actions for natural-language prompts", async () => {
  const wrapper = mount(TaggerPage, { global: {
    plugins: [createPinia(), i18n], stubs: { ManagedDatasetPicker: true },
  } })
  await wrapper.get('[data-testid="parameter-toggle"]').trigger("click")
  await wrapper.get('[data-testid="tab-advanced"]').trigger("click")
  expect(wrapper.get('[data-testid="caption-load"]').text()).toContain("加载")
  expect(wrapper.get('[data-testid="caption-save-template"]').text()).toContain("保存为模板")
  expect(wrapper.get('[data-testid="caption-reset"]').text()).toContain("重置")
  wrapper.unmount()
})

it("updates and deletes the selected custom prompt template", async () => {
  localStorage.setItem("nt.tagger.captionTemplates", JSON.stringify({ "custom-existing": "Original prompt" }))
  const wrapper = mount(TaggerPage, { global: {
    plugins: [createPinia(), i18n], stubs: { ManagedDatasetPicker: true },
  } })
  await wrapper.get('[data-testid="parameter-toggle"]').trigger("click")
  await wrapper.get('[data-testid="tab-advanced"]').trigger("click")
  const select = wrapper.get('[data-testid="caption-template-select"]')
  await select.setValue("custom-existing")
  await wrapper.get('[data-testid="caption-load"]').trigger("click")
  const prompt = wrapper.get('[data-testid="caption-prompt"]')
  expect((prompt.element as HTMLTextAreaElement).value).toBe("Original prompt")

  await prompt.setValue("Edited prompt")
  await wrapper.get('[data-testid="caption-update-template"]').trigger("click")
  expect(JSON.parse(localStorage.getItem("nt.tagger.captionTemplates") || "{}")["custom-existing"]).toBe("Edited prompt")

  await wrapper.get('[data-testid="caption-delete-template"]').trigger("click")
  expect(JSON.parse(localStorage.getItem("nt.tagger.captionTemplates") || "{}")["custom-existing"]).toBeUndefined()
  expect((select.element as HTMLSelectElement).value).toBe("default")
  wrapper.unmount()
})
