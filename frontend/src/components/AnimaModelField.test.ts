// @vitest-environment jsdom
import { mount } from "@vue/test-utils"
import { beforeEach, expect, it } from "vitest"
import AnimaModelField from "./AnimaModelField.vue"
import { i18n } from "../i18n"

const base = "./sd-models/anima/anima-base-v1.0.safetensors"
const large = "./sd-models/anima/split_files/diffusion_models/Anima-2.9B-preview-v1.safetensors"
function setup(path = base) {
  return mount(AnimaModelField, {
    props: {
      modelValue: path,
      field: { key: "pretrained_model_name_or_path", type: "string" as const, conditions: [] },
    },
    global: { plugins: [i18n], stubs: { SchemaField: {
      props: ["modelValue", "defaultValue"],
      template: `<div><slot name="before-control" /><input class="path" :value="modelValue" @input="$emit('update:modelValue', $event.target.value)" /><button class="reset" @click="$emit('reset')">reset</button><span>{{ defaultValue }}</span></div>`,
    } } },
  })
}
beforeEach(() => localStorage.clear())
it("switches defaults and remembers custom paths independently", async () => {
  const wrapper = setup()
  await wrapper.get(".path").setValue("D:/custom/base.safetensors")
  await wrapper.setProps({ modelValue: "D:/custom/base.safetensors" })
  await wrapper.get('[data-spec="2.9b"]').setValue(true)
  expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([large])
  await wrapper.setProps({ modelValue: large })
  await wrapper.get('[data-spec="2b"]').setValue(true)
  expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual(["D:/custom/base.safetensors"])
})
it("keeps imported unknown paths unchanged and asks for a specification", () => {
  const wrapper = setup("D:/models/custom.safetensors")
  expect(wrapper.emitted("update:modelValue")).toBeUndefined()
  expect(wrapper.text()).toContain("请确认模型规格")
})
it("recognizes known 2.9B paths and resets to its own default", async () => {
  const wrapper = setup("D:/models/Anima-2.9B-preview-v1.safetensors")
  expect((wrapper.get('[data-spec="2.9b"]').element as HTMLInputElement).checked).toBe(true)
  await wrapper.get(".reset").trigger("click")
  expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([large])
})
it("preserves an unknown imported path when confirming its specification", async () => {
  const wrapper = setup("D:/models/custom.safetensors")
  await wrapper.get('[data-spec="2.9b"]').setValue(true)
  expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual(["D:/models/custom.safetensors"])
})
it("does not overwrite remembered custom paths when mounting a default configuration", async () => {
  localStorage.setItem("anima-model-paths", JSON.stringify({ "2b": "D:/custom/base.safetensors" }))
  const wrapper = setup()
  await wrapper.get('[data-spec="2.9b"]').setValue(true)
  await wrapper.setProps({ modelValue: large })
  await wrapper.get('[data-spec="2b"]').setValue(true)
  expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual(["D:/custom/base.safetensors"])
})
it("recognizes a confirmed custom model after importing another configuration", async () => {
  const custom = "D:/models/custom.safetensors"
  const wrapper = setup(custom)
  await wrapper.get('[data-spec="2.9b"]').setValue(true)
  await wrapper.setProps({ modelValue: base })
  await wrapper.setProps({ modelValue: custom })
  expect((wrapper.get('[data-spec="2.9b"]').element as HTMLInputElement).checked).toBe(true)
  await wrapper.get(".reset").trigger("click")
  expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([large])
})
