// @vitest-environment jsdom
import { mount } from "@vue/test-utils"
import { describe, expect, it } from "vitest"
import SchemaField from "./SchemaField.vue"
import { i18n } from "../i18n"

const field = {
  key: "control_data_dirs",
  type: "array" as const,
  role: "paired-directories",
  extra: { type: "folder", internal: "train-dir" },
  description: "图像编辑参考图目录（按文件名与训练图配对）",
  conditions: [],
}

const previewField = {
  key: "sample_control_images",
  type: "array" as const,
  role: "preview-control-images",
  extra: { type: "file", internal: "train-dir" },
  description: "图像编辑预览参考图",
  conditions: [],
}

const resolutionField = {
  key: "resolution",
  type: "array" as const,
  role: "resolution-selector",
  description: "训练分辨率档位",
  conditions: [],
}

const modelPathField = {
  key: "dit",
  type: "string" as const,
  role: "model-path",
  extra: { type: "model-file" },
  description: "Klein DiT 模型路径",
  conditions: [],
}

function mountField(value?: string[]) {
  return mount(SchemaField, {
    props: { field, modelValue: value, defaultValue: value },
    global: {
      plugins: [i18n],
      stubs: {
        ElInput: {
          props: ["modelValue", "placeholder"],
          emits: ["update:modelValue"],
          template: `<input class="stub-input" :value="modelValue" :placeholder="placeholder" @input="$emit('update:modelValue', $event.target.value)" />`,
        },
        ElButton: { template: "<button><slot /></button>" },
        ElTooltip: { template: "<span><slot /></span>" },
        ElDialog: { template: "<div><slot /></div>" },
        PathPickerDialog: { template: "<div />" },
      },
    },
  })
}

function mountPreviewField(value?: string[]) {
  return mount(SchemaField, {
    props: { field: previewField, modelValue: value, defaultValue: value },
    global: {
      plugins: [i18n],
      stubs: {
        ElInput: {
          props: ["modelValue", "placeholder"],
          emits: ["update:modelValue"],
          template: `<input class="stub-input" :value="modelValue" :placeholder="placeholder" @input="$emit('update:modelValue', $event.target.value)" />`,
        },
        ElButton: { template: "<button><slot /></button>" },
        ElTooltip: { template: "<span><slot /></span>" },
        ElDialog: { template: "<div><slot /></div>" },
        PathPickerDialog: { template: "<div />" },
      },
    },
  })
}

function mountResolutionField(value: string | Array<string | number> = [512, 768, 1024]) {
  return mount(SchemaField, {
    props: { field: resolutionField, modelValue: value, defaultValue: value },
    global: {
      plugins: [i18n],
      stubs: {
        ElSelect: {
          props: ["modelValue"],
          emits: ["update:modelValue"],
          template: `<select class="resolution-select" multiple :data-value="JSON.stringify(modelValue)" @change="$emit('update:modelValue', Array.from($event.target.selectedOptions).map((option) => option.value))"><slot /></select>`,
        },
        ElOption: {
          props: ["value", "label"],
          template: `<option :value="value">{{ label }}</option>`,
        },
        ElTooltip: { template: "<span><slot /></span>" },
        ElDialog: { template: "<div><slot /></div>" },
        PathPickerDialog: { template: "<div />" },
      },
    },
  })
}

function mountModelPathField(source: string) {
  return mount(SchemaField, {
    props: { field: modelPathField, modelValue: "./models/klein", defaultValue: "./models/klein", context: { model_source: source } },
    global: {
      plugins: [i18n],
      stubs: {
        ElInput: { template: `<input class="stub-input" />` },
        ElButton: { template: "<button><slot /></button>" },
        ElTooltip: { template: "<span><slot /></span>" },
        ElDialog: { template: "<div><slot /></div>" },
        PathPickerDialog: { template: "<div />" },
      },
    },
  })
}

describe("SchemaField", () => {
  it("shows two empty reference directory inputs when no paths are configured", () => {
    const wrapper = mountField()

    expect(wrapper.findAll(".paired-directory-row")).toHaveLength(2)
    expect(wrapper.findAll(".paired-directory-row .filepicker-control")).toHaveLength(2)
    expect(wrapper.findAll(".paired-directory-label").map((label) => label.text())).toEqual(["control_data_dirs 1", "control_data_dirs 2"])
    expect(wrapper.findAll(".stub-input").map((input) => input.attributes("placeholder"))).toEqual(["control_data_dirs 1", "control_data_dirs 2"])
    expect(wrapper.findAll(".paired-directory-row .common-paths")).toHaveLength(0)
  })

  it("adds and removes paired reference directories", async () => {
    const wrapper = mountField(["./controls"])

    expect(wrapper.findAll(".paired-directory-row")).toHaveLength(1)
    await wrapper.get('[data-action="add-directory"]').trigger("click")
    await wrapper.setProps({ modelValue: ["./controls", ""] })
    expect(wrapper.findAll(".paired-directory-row")).toHaveLength(2)
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([["./controls", ""]])

    await wrapper.get('[data-action="remove-directory"]').trigger("click")
    await wrapper.setProps({ modelValue: ["./controls"] })
    expect(wrapper.findAll(".paired-directory-row")).toHaveLength(1)
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([["./controls"]])
  })

  it("explains filename pairing for reference directories", () => {
    expect(mountField().text()).toContain("按文件名与训练图配对")
  })

  it("shows preview reference image slots with thumbnails and paths", () => {
    const wrapper = mountPreviewField(["./controls/one.png", "./controls/two.png"])

    expect(wrapper.findAll(".preview-control-image-row")).toHaveLength(3)
    expect(wrapper.findAll(".preview-control-image-thumb")).toHaveLength(2)
    expect(wrapper.findAll(".preview-control-image-path input")).toHaveLength(3)
    expect(wrapper.text()).toContain("sample_control_images 1")
    expect(wrapper.text()).toContain("sample_control_images 2")
    expect(wrapper.findAll('[data-action="clear-preview-image"]')).toHaveLength(2)
  })

  it("clears only the selected preview reference image", async () => {
    const wrapper = mountPreviewField(["./controls/one.png", "./controls/two.png"])

    await wrapper.findAll('[data-action="clear-preview-image"]')[0].trigger("click")

    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([["", "./controls/two.png", ""]])
  })

  it("renders toolkit resolution presets and emits numeric values", async () => {
    const wrapper = mountResolutionField()

    expect(wrapper.findAll("option").map((option) => option.text())).toEqual([
      "256", "512", "768", "1024", "1280", "1328", "1536", "2048",
    ])
    await wrapper.find("select").trigger("change")
    expect(wrapper.emitted("update:modelValue")).toBeDefined()
  })

  it("shows a legacy width-height string as toolkit resolution values", () => {
    const wrapper = mountResolutionField("1024,1024")

    expect(wrapper.get(".resolution-select").attributes("data-value")).toBe("[1024]")
  })

  it("uses a folder picker for local model directories", () => {
    const wrapper = mountModelPathField("local-directory")

    expect(wrapper.find(".model-path-control").exists()).toBe(true)
    expect(wrapper.find(".filepicker-control").exists()).toBe(true)
  })

  it("keeps repository IDs as plain text without a misleading file picker", () => {
    const wrapper = mountModelPathField("hf-repo")

    expect(wrapper.find(".model-path-control").exists()).toBe(true)
    expect(wrapper.find(".filepicker-control").exists()).toBe(false)
  })
})
