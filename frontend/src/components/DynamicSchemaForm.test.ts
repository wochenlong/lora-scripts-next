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
  sections: [{
    id: "main",
    title: "基础参数",
    fields: [
      { key: "mode", type: "string", options: ["basic", "advanced"], conditions: [] },
      { key: "steps", type: "number", conditions: [{ key: "mode", value: "advanced" }] },
      { key: "secret", type: "string", hidden: true, conditions: [] },
    ],
  }],
}

describe("DynamicSchemaForm", () => {
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

  it("disables Anima Fast torch compile and clears it when torch attention is selected", async () => {
    const animaSchema: AdaptedSchema = {
      ...schema,
      name: "anima-lora-fast",
      sections: [{
        ...schema.sections[0],
        fields: [
          { key: "attn_mode", type: "string", options: ["", "torch", "flash"], conditions: [] },
          { key: "torch_compile", type: "boolean", conditions: [] },
        ],
      }],
    }
    const wrapper = mount(DynamicSchemaForm, {
      props: {
        schema: animaSchema,
        modelValue: { attn_mode: "torch", torch_compile: true },
        errors: {},
        effectiveDefaults: { attn_mode: "", torch_compile: false },
      },
      global: {
        plugins: [i18n],
        stubs: {
          SchemaField: {
            props: ["field"],
            template: "<button class='field' :data-key='field.key' :data-disabled='field.disabled' @click='$emit(\"update:modelValue\", field.key === \"attn_mode\" ? \"torch\" : false)' />",
          },
        },
      },
    })

    expect(wrapper.get("[data-key='torch_compile']").attributes("data-disabled")).toBe("true")
    await wrapper.get("[data-key='attn_mode']").trigger("click")
    expect(wrapper.emitted("update:modelValue")?.[0]).toEqual([{ attn_mode: "torch", torch_compile: false }])
  })
})
