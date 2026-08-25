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
})
