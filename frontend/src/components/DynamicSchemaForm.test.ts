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
  it("renders active visible fields and propagates updates", async () => {
    const wrapper = mount(DynamicSchemaForm, {
      props: { schema, modelValue: { mode: "basic" }, errors: {} },
      global: { plugins: [i18n], stubs: { SchemaField: { props: ["field"], template: "<button @click=\"$emit('update:modelValue', 12)\">{{ field.key }}</button>" } } },
    })

    expect(wrapper.text()).toContain("mode")
    expect(wrapper.text()).not.toContain("steps")
    expect(wrapper.text()).not.toContain("secret")
    await wrapper.get("button").trigger("click")
    expect(wrapper.emitted("update:modelValue")?.[0]).toEqual([{ mode: 12 }])
  })

  it("disables and clears torch_compile when torch attention is selected", async () => {
    const guardedSchema: AdaptedSchema = {
      ...schema,
      sections: [{
        ...schema.sections[0],
        fields: [
          { key: "attn_mode", type: "string", options: ["torch", "flash"], conditions: [] },
          { key: "torch_compile", type: "boolean", conditions: [] },
        ],
      }],
    }
    const wrapper = mount(DynamicSchemaForm, {
      props: {
        schema: guardedSchema,
        modelValue: { attn_mode: "flash", torch_compile: true },
        errors: {},
      },
      global: {
        plugins: [i18n],
        stubs: {
          SchemaField: {
            props: ["field", "modelValue"],
            template: "<button :data-key=\"field.key\" :data-disabled=\"field.disabled\" @click=\"$emit('update:modelValue', field.key === 'attn_mode' ? 'torch' : false)\">{{ field.key }}</button>",
          },
        },
      },
    })

    await wrapper.get('[data-key="attn_mode"]').trigger("click")

    expect(wrapper.emitted("update:modelValue")?.at(-1)).toEqual([
      { attn_mode: "torch", torch_compile: false },
    ])
    await wrapper.setProps({ modelValue: { attn_mode: "torch", torch_compile: false } })
    expect(wrapper.get('[data-key="torch_compile"]').attributes("data-disabled")).toBe("true")
  })
})
