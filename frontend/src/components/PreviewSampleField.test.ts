// @vitest-environment jsdom
import { mount } from "@vue/test-utils"
import { describe, expect, it } from "vitest"
import PreviewSampleField from "./PreviewSampleField.vue"
import { i18n } from "../i18n"

describe("PreviewSampleField", () => {
  it("starts with one sample and adds another only when requested", async () => {
    const wrapper = mount(PreviewSampleField, {
      props: {
        samples: [],
      },
      global: {
        plugins: [i18n],
        stubs: {
          ElInput: { template: "<textarea />" },
          ElInputNumber: { template: "<input type='number' />" },
          ElSelect: { template: "<select><slot /></select>" },
          ElOption: { template: "<option><slot /></option>" },
          ElButton: { template: "<button><slot /></button>" },
          ElIcon: { template: "<span><slot /></span>" },
          PathPickerDialog: { template: "<div />" },
        },
      },
    })

    expect(wrapper.findAll(".preview-sample-item")).toHaveLength(1)

    await wrapper.get(".preview-sample-add").trigger("click")

    const emitted = wrapper.emitted("update:samples")
    expect(emitted).toHaveLength(1)
    expect(emitted?.[0]?.[0]).toHaveLength(2)
  })

  it("renders multiple AI Toolkit samples with independent prompts", () => {
    const wrapper = mount(PreviewSampleField, {
      props: {
        samples: [
          JSON.stringify({ prompt: "first edit", controlImages: ["one.png"] }),
          JSON.stringify({ prompt: "second edit", controlImages: ["two.png"] }),
        ],
      },
      global: {
        plugins: [i18n],
        stubs: {
          ElInput: { template: "<textarea />" },
          ElInputNumber: { template: "<input type='number' />" },
          ElSelect: { template: "<select><slot /></select>" },
          ElOption: { template: "<option><slot /></option>" },
          ElButton: { template: "<button><slot /></button>" },
          ElIcon: { template: "<span><slot /></span>" },
          PathPickerDialog: { template: "<div />" },
        },
      },
    })

    expect(wrapper.findAll(".preview-sample-item")).toHaveLength(2)
    expect(wrapper.findAll(".preview-sample-prompt")).toHaveLength(4)
    expect(wrapper.findAll(".preview-sample-image-slot")).toHaveLength(6)
    expect(wrapper.findAll(".preview-sample-add")).toHaveLength(1)
    expect(wrapper.findAll("textarea")).toHaveLength(10)
  })

  it("renders independent generation settings for every sample", () => {
    const wrapper = mount(PreviewSampleField, {
      props: {
        samples: [
          JSON.stringify({
            prompt: "first edit",
            controlImages: [],
            width: 768,
            height: 1024,
            seed: 11,
            guidance_scale: 3,
            sample_steps: 18,
            network_multiplier: 0.8,
            sampler: "flowmatch",
          }),
        ],
      },
      global: {
        plugins: [i18n],
        stubs: {
          ElInput: { template: "<textarea />" },
          ElInputNumber: { template: "<input type='number' />" },
          ElSelect: { template: "<select><slot /></select>" },
          ElOption: { template: "<option><slot /></option>" },
          PathPickerDialog: { template: "<div />" },
        },
      },
    })

    expect(wrapper.findAll(".preview-sample-setting")).toHaveLength(7)
    expect(wrapper.text()).toContain("width")
    expect(wrapper.text()).toContain("height")
    expect(wrapper.text()).toContain("seed")
    expect(wrapper.text()).toContain("guidance_scale")
    expect(wrapper.text()).toContain("sample_steps")
    expect(wrapper.text()).toContain("network_multiplier")
    expect(wrapper.text()).toContain("sampler")
  })
})
