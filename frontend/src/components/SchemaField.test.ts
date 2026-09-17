// @vitest-environment jsdom
import { mount } from "@vue/test-utils"
import { defineComponent } from "vue"
import { describe, expect, it } from "vitest"
import { i18n } from "../i18n"
import type { FormField } from "../schema/adapter"
import SchemaField from "./SchemaField.vue"

const InputNumberProbe = defineComponent({
  name: "ElInputNumber",
  props: {
    modelValue: { type: Number, default: undefined },
    disabled: Boolean,
    min: { type: Number, default: undefined },
    max: { type: Number, default: undefined },
    step: { type: Number, default: undefined },
    stepStrictly: Boolean,
    precision: { type: Number, default: undefined },
    controlsPosition: { type: String, default: undefined },
  },
  template: "<input />",
})

function mountNumberField(field: FormField) {
  return mount(SchemaField, {
    props: { field, modelValue: 0 },
    global: {
      plugins: [i18n],
      components: { ElInputNumber: InputNumberProbe },
      stubs: {
        ElButton: true,
        ElDialog: true,
        ElInput: true,
        ElOption: true,
        ElSelect: true,
        ElSwitch: true,
        ElTooltip: { template: "<div><slot /></div>" },
        PathPickerDialog: true,
      },
    },
  })
}

describe("SchemaField", () => {
  it("enables strict integer input only for explicitly marked number fields", () => {
    const integer = mountNumberField({
      key: "validation_split_num",
      type: "number",
      step: 1,
      extra: { integer: true },
      conditions: [],
    })
    const regular = mountNumberField({
      key: "learning_rate",
      type: "number",
      step: 1,
      conditions: [],
    })

    expect(integer.getComponent(InputNumberProbe).props()).toMatchObject({
      stepStrictly: true,
      precision: 0,
    })
    expect(regular.getComponent(InputNumberProbe).props("stepStrictly")).toBe(false)
    expect(regular.getComponent(InputNumberProbe).props("precision")).toBeUndefined()
  })
})
