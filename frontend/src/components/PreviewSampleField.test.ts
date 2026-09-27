// @vitest-environment jsdom
import { ElInputNumber } from "element-plus"
import { mount } from "@vue/test-utils"
import { describe, expect, it } from "vitest"
import { i18n } from "../i18n"
import { createSample, decodeSamples, encodeSamples } from "../training/sampleContract"
import PreviewSampleField from "./PreviewSampleField.vue"
import ReferencePathsField from "./ReferencePathsField.vue"

const global = { plugins: [i18n], stubs: { PathPickerDialog: true } }

describe("PreviewSampleField", () => {
  it("applies model-specific numeric limits without adding edit controls", () => {
    const wrapper = mount(PreviewSampleField, { props: { dimensionStep: 32, minGuidance: 1 }, global })
    const inputs = wrapper.findAllComponents(ElInputNumber)
    expect(inputs[0].props()).toMatchObject({ min: 32, step: 32 })
    expect(inputs[1].props()).toMatchObject({ min: 32, step: 32 })
    expect(inputs[3].props()).toMatchObject({ min: 1, step: 0.1 })
    expect(wrapper.findComponent(ReferencePathsField).exists()).toBe(false)
  })

  it("starts with one Sample and adds an independent Sample", async () => {
    const wrapper = mount(PreviewSampleField, { global })
    expect(wrapper.findAll(".preview-sample-item")).toHaveLength(1)
    await wrapper.find(".preview-sample-add").trigger("click")
    const samples = wrapper.emitted("update:samples")![0][0] as string[]
    expect(decodeSamples(samples)).toHaveLength(2)
    await wrapper.setProps({ samples })
    await wrapper.findAll("textarea")[1].setValue("second prompt")
    const changed = decodeSamples(wrapper.emitted("update:samples")!.at(-1)![0] as string[])
    expect(changed.map(sample => sample.prompt)).toEqual(["", "second prompt"])
    await wrapper.find("header button").trigger("click")
    expect(decodeSamples(wrapper.emitted("update:samples")!.at(-1)![0] as string[])).toHaveLength(1)
  })

  it("shows references only for editing and respects disabled state", async () => {
    const wrapper = mount(PreviewSampleField, { global })
    expect(wrapper.findComponent(ReferencePathsField).exists()).toBe(false)
    await wrapper.setProps({ editing: true, disabled: true })
    expect(wrapper.findComponent(ReferencePathsField).exists()).toBe(true)
    expect(wrapper.findAll("button").every(button => button.attributes("disabled") !== undefined)).toBe(true)
  })

  it("keeps malformed saved values visible as an error without overwriting them", () => {
    const wrapper = mount(PreviewSampleField, { props: { samples: ["broken"] }, global })
    expect(wrapper.find('[role="alert"]').exists()).toBe(true)
    expect(wrapper.emitted("update:samples")).toBeUndefined()
  })

  it("preserves per-Sample numeric values", async () => {
    const samples = encodeSamples([{ ...createSample(), seed: 123 }, { ...createSample(), width: 768 }])
    const wrapper = mount(PreviewSampleField, { props: { samples }, global })
    await wrapper.findAll("textarea")[0].setValue("changed")
    const changed = decodeSamples(wrapper.emitted("update:samples")![0][0] as string[])
    expect(changed[0].seed).toBe(123)
    expect(changed[1].width).toBe(768)
  })
})

describe("ReferencePathsField", () => {
  it("supports more than three references and removes a selected row", async () => {
    const wrapper = mount(ReferencePathsField, { props: { modelValue: ["a", "b", "c", "d"] }, global })
    expect(wrapper.findAll(".reference-path")).toHaveLength(4)
    await wrapper.find(".reference-paths > button").trigger("click")
    expect(wrapper.emitted("update:modelValue")![0][0]).toEqual(["a", "b", "c", "d", ""])
    await wrapper.findAll(".reference-path")[1].findAll("button")[1].trigger("click")
    expect(wrapper.emitted("update:modelValue")![1][0]).toEqual(["a", "c", "d"])
  })
})
