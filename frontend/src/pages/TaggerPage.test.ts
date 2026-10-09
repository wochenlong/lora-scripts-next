// @vitest-environment jsdom
import { mount } from "@vue/test-utils"
import { createPinia } from "pinia"
import { expect, it, vi } from "vitest"
import { i18n } from "../i18n"
import TaggerPage from "./TaggerPage.vue"

vi.mock("vue-router", () => ({ useRoute: () => ({ query: {} }) }))

it("keeps future controls disabled and uses a searchable grouped model selector", async () => {
  const wrapper = mount(TaggerPage, { global: {
    plugins: [createPinia(), i18n], stubs: { ManagedDatasetPicker: true },
  } })
  expect(wrapper.get('[data-testid="caption-pending"]').attributes("disabled")).toBeDefined()
  expect(wrapper.get('[data-testid="preview-pending"]').attributes("disabled")).toBeDefined()
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
