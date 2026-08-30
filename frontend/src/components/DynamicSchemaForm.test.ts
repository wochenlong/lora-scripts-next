// @vitest-environment jsdom
import { mount } from "@vue/test-utils"
import { describe, expect, it } from "vitest"
import DynamicSchemaForm from "./DynamicSchemaForm.vue"
import { i18n } from "../i18n"
import type { AdaptedSchema } from "../schema/adapter"
import Schema from "schemastery"

const schema: AdaptedSchema = {
  name: "test",
  hash: "test",
  schema: Schema.object({}),
  capabilities: ["lora", "text-to-image", "image-edit"],
  sections: [{
    id: "main",
    title: "数据集设置",
    fields: [
      { key: "task", type: "string", role: "task-selector", options: ["text-to-image", "image-edit"], description: "训练任务", conditions: [] },
      { key: "mode", type: "string", options: ["basic", "advanced"], conditions: [] },
      { key: "steps", type: "number", conditions: [{ key: "mode", value: "advanced" }] },
      { key: "secret", type: "string", hidden: true, conditions: [] },
    ],
  }],
}

describe("DynamicSchemaForm", () => {
  it("renders a task selector only for dual-capability schemas", async () => {
    const wrapper = mount(DynamicSchemaForm, {
      props: { schema, modelValue: { task: "text-to-image", mode: "basic" }, errors: {}, effectiveDefaults: { task: "text-to-image", mode: "basic" } },
      global: { plugins: [i18n], stubs: { SchemaField: { props: ["field"], template: "<div>{{ field.key }}</div>" } } },
    })

    expect(wrapper.get(".task-selector").text()).toContain("文生图")
    expect(wrapper.get(".task-selector").text()).toContain("图像编辑")
    expect(wrapper.get(".task-selector").text().match(/训练任务/g)).toHaveLength(1)
    const formChildren = Array.from(wrapper.get(".schema-form").element.children).map((child) => child.getAttribute("class")?.split(/\s+/) || [])
    expect(formChildren.findIndex((classes) => classes.includes("task-selector"))).toBeLessThan(formChildren.findIndex((classes) => classes.includes("schema-section")))
    await wrapper.get('[data-task="image-edit"]').trigger("click")
    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([{ task: "image-edit", mode: "basic" }])
  })

  it("keeps the image-edit dataset path first while placing the task selector before fields", () => {
    const imageEditSchema: AdaptedSchema = {
      ...schema,
      sections: [{
        id: "dataset",
        title: "数据集设置",
        fields: [
          { key: "task", type: "string", role: "task-selector", options: ["text-to-image", "image-edit"], conditions: [] },
          { key: "train_data_dir", type: "string", conditions: [] },
          { key: "resolution", type: "string", conditions: [] },
        ],
      }],
    }
    const wrapper = mount(DynamicSchemaForm, {
      props: { schema: imageEditSchema, modelValue: { task: "image-edit" }, errors: {}, effectiveDefaults: {} },
      global: { plugins: [i18n], stubs: { SchemaField: { props: ["field"], template: "<div class='field'>{{ field.key }}</div>" } } },
    })

    expect(wrapper.findAll(".field").map((field) => field.text())).toEqual(["train_data_dir", "resolution"])
    expect(wrapper.find(".task-selector").exists()).toBe(true)
    const formChildren = Array.from(wrapper.get(".schema-form").element.children).map((child) => child.getAttribute("class")?.split(/\s+/) || [])
    expect(formChildren.findIndex((classes) => classes.includes("task-selector"))).toBeLessThan(formChildren.findIndex((classes) => classes.includes("schema-section")))
  })

  it("does not render a task selector for a single-capability schema", () => {
    const singleCapabilitySchema = { ...schema, capabilities: ["lora", "text-to-image"] }
    const wrapper = mount(DynamicSchemaForm, {
      props: { schema: singleCapabilitySchema, modelValue: { task: "text-to-image", mode: "basic" }, errors: {}, effectiveDefaults: { task: "text-to-image", mode: "basic" } },
      global: { plugins: [i18n], stubs: { SchemaField: { props: ["field"], template: "<div>{{ field.key }}</div>" } } },
    })

    expect(wrapper.find(".task-selector").exists()).toBe(false)
  })

  it("renders active visible fields, passes effective defaults, and propagates updates", async () => {
    const wrapper = mount(DynamicSchemaForm, {
      props: { schema, modelValue: { mode: "basic" }, errors: {}, effectiveDefaults: { mode: "basic", steps: 8 } },
      global: { plugins: [i18n], stubs: { SchemaField: { props: ["field", "defaultValue"], template: "<div><button class=\"update\" @click=\"$emit('update:modelValue', 12)\">{{ field.key }}={{ JSON.stringify(defaultValue) }}</button><button class=\"reset\" @click=\"$emit('reset')\">reset {{ field.key }}</button></div>" } } },
    })

    expect(wrapper.text()).toContain("mode")
    expect(wrapper.text()).toContain("\"basic\"")
    expect(wrapper.text()).not.toContain("steps")
    expect(wrapper.text()).not.toContain("secret")
    await wrapper.get(".update").trigger("click")
    expect(wrapper.emitted("update:modelValue")?.[0]).toEqual([{ mode: 12 }])
    await wrapper.get(".reset").trigger("click")
    expect(wrapper.emitted("reset-field")?.[0]).toEqual(["mode"])
  })

  it("renders the preview sample as one combined prompt and control-image block", () => {
    const previewSchema: AdaptedSchema = {
      ...schema,
      sections: [{
        id: "preview",
        title: "训练预览图设置",
        fields: [
          { key: "enable_preview", type: "boolean", conditions: [] },
          { key: "positive_prompts", type: "string", role: "preview-sample", conditions: [] },
          { key: "sample_control_images", type: "array", hidden: true, conditions: [] },
          { key: "preview_samples", type: "array", hidden: true, conditions: [] },
        ],
      }],
    }
    const wrapper = mount(DynamicSchemaForm, {
      props: {
        schema: previewSchema,
        modelValue: { enable_preview: true, positive_prompts: "edit this", sample_control_images: ["one.png"] },
        errors: {},
        effectiveDefaults: {},
      },
      global: {
        plugins: [i18n],
        stubs: {
          SchemaField: { props: ["field"], template: "<div class='field'>{{ field.key }}</div>" },
          PreviewSampleField: {
            props: ["samples", "legacyPrompt", "legacyControlImages"],
            template: "<div class='preview-sample-stub'>{{ legacyPrompt }} {{ legacyControlImages[0] }}</div>",
          },
        },
      },
    })

    expect(wrapper.findAll(".preview-sample-stub")).toHaveLength(1)
    expect(wrapper.text()).toContain("edit this one.png")
    expect(wrapper.text()).not.toContain("sample_control_images")
  })
})
