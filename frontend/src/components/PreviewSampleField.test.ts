// @vitest-environment jsdom
import { ElInputNumber } from "element-plus"
import { mount } from "@vue/test-utils"
import { describe, expect, it, vi } from "vitest"
import { i18n } from "../i18n"
import { schemasApi } from "../api/schemas"
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

  it("shows an editing instruction example only in edit mode", async () => {
    const wrapper = mount(PreviewSampleField, { global })
    expect(wrapper.get("textarea").attributes("placeholder")).toBe("")
    await wrapper.setProps({ editing: true })
    expect(wrapper.get("textarea").attributes("placeholder")).toBe("例如：将图片转换为 XX 风格")
  })

  it("renders edit references as AI Toolkit-style control image cards", async () => {
    const wrapper = mount(PreviewSampleField, { props: { editing: true }, global })
    expect(wrapper.find(".control-images").exists()).toBe(true)
    expect(wrapper.find(".control-image-add").exists()).toBe(true)
    await wrapper.find(".control-image-add").trigger("click")
    expect(decodeSamples(wrapper.emitted("update:samples")!.at(-1)![0] as string[])[0].controlImages).toEqual([""])
  })

  it("uploads an image dropped on the add card and stores the server path", async () => {
    vi.spyOn(schemasApi, "uploadPreviewImage").mockResolvedValue({ path: ".runtime/training-preview/dropped.png" })
    const wrapper = mount(PreviewSampleField, { props: { editing: true }, global })
    const file = new File(["image"], "dropped.png", { type: "image/png" })

    await wrapper.find(".control-image-add").trigger("drop", {
      dataTransfer: { files: [file] },
    })
    await vi.waitFor(() => expect(wrapper.emitted("update:samples")).toBeTruthy())

    expect(schemasApi.uploadPreviewImage).toHaveBeenCalledWith(file)
    const samples = decodeSamples(wrapper.emitted("update:samples")!.at(-1)![0] as string[])
    expect(samples[0].controlImages).toEqual([".runtime/training-preview/dropped.png"])
  })

  it("uses a browser file input when an edit reference card is clicked", async () => {
    vi.spyOn(schemasApi, "uploadPreviewImage").mockResolvedValue({ path: ".runtime/training-preview/picked.png" })
    const samples = encodeSamples([{ ...createSample(), controlImages: [""] }])
    const wrapper = mount(PreviewSampleField, { props: { editing: true, samples }, global })
    const input = wrapper.get('input[type="file"]')
    const file = new File(["image"], "picked.png", { type: "image/png" })
    Object.defineProperty(input.element, "files", { configurable: true, value: [file] })

    await wrapper.get(".control-image-card").trigger("click")
    await input.trigger("change")
    await vi.waitFor(() => expect(schemasApi.uploadPreviewImage).toHaveBeenCalledWith(file))

    const emitted = decodeSamples(wrapper.emitted("update:samples")!.at(-1)![0] as string[])
    expect(emitted[0].controlImages).toEqual([".runtime/training-preview/picked.png"])
  })

  it("renders uploaded server paths through the protected preview endpoint", () => {
    const samples = encodeSamples([{ ...createSample(), controlImages: [".runtime/training-preview/example image.png"] }])
    const wrapper = mount(PreviewSampleField, { props: { editing: true, samples }, global })
    expect(wrapper.get(".control-image-card img").attributes("src")).toBe(
      "/api/training/preview-image?path=.runtime%2Ftraining-preview%2Fexample%20image.png",
    )
    expect(wrapper.get(".control-image-card").classes()).toContain("filled")
    expect(wrapper.find(".control-image-card.filled strong").exists()).toBe(false)
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
