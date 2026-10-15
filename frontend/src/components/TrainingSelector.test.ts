// @vitest-environment jsdom
import { flushPromises, mount } from "@vue/test-utils"
import { afterEach, expect, it, vi } from "vitest"
import { i18n } from "../i18n"
import { enginesApi } from "../api/engines"
import type { TrainingEngine, TrainingModel, TrainingTarget } from "../training/modules"
import TrainingSelector from "./TrainingSelector.vue"

afterEach(() => { vi.restoreAllMocks() })

function mountSelector(props: { model?: TrainingModel; engine?: TrainingEngine; target?: TrainingTarget } = {}) {
  return mount(TrainingSelector, {
    props: {
      model: props.model ?? "anima",
      engine: props.engine ?? "kohya",
      target: props.target ?? "lora",
    },
    global: {
      plugins: [i18n],
      stubs: {
        ElSelect: {
          props: ["modelValue"],
          emits: ["update:modelValue", "change"],
          template: `<select :data-testid="$attrs['data-testid']" :value="modelValue" @change="$emit('update:modelValue', $event.target.value); $emit('change', $event.target.value)"><slot /></select>`,
        },
        ElOption: {
          props: ["value", "label"],
          template: `<option :value="value"><slot>{{ label }}</slot></option>`,
        },
      },
    },
  })
}

it("keeps one model hint visible and hides use-case tips until asked", async () => {
  vi.spyOn(enginesApi, "list").mockResolvedValue([
    { id: "kohya", state: "ready", featureEnabled: true },
    { id: "anima-fast", state: "ready", featureEnabled: true },
  ] as never)
  const wrapper = mountSelector({ engine: "anima-fast" })
  await flushPromises()

  expect(wrapper.get('[data-testid="model-use-hint"]').text()).toContain("二次元")
  expect(wrapper.get('[data-testid="model-guide-toggle"]').text()).toBe("不会选？")
  expect(wrapper.findAll('[data-testid="model-guide-panel"]')).toHaveLength(0)
  expect(wrapper.get('[data-testid="engine-hint"]').text()).toMatch(/隐藏 2 项/)
  expect(wrapper.findAll('[data-testid="engine-select"]')).toHaveLength(1)

  await wrapper.get('[data-testid="model-guide-toggle"]').trigger("click")
  const panel = wrapper.get('[data-testid="model-guide-panel"]')
  expect(panel.text()).toContain("通用写实")
  await panel.findAll("button")[1].trigger("click")
  expect(wrapper.emitted("update:model")?.at(-1)).toEqual(["krea2"])
  expect(wrapper.findAll('[data-testid="model-guide-panel"]')).toHaveLength(0)
  wrapper.unmount()
})

it("explains when unsupported engines are hidden for the model", async () => {
  vi.spyOn(enginesApi, "list").mockResolvedValue([
    { id: "kohya", state: "ready", featureEnabled: true },
    { id: "anima-fast", state: "not_installed", featureEnabled: true },
  ] as never)
  const wrapper = mountSelector({ engine: "kohya" })
  await flushPromises()

  expect(wrapper.get('[data-testid="engine-hint"]').text()).toMatch(/不支持当前模型.*隐藏 2 项/)
  wrapper.unmount()
})

it("lists only supported engines with green/red dots, and sinks unsupported outside", async () => {
  vi.spyOn(enginesApi, "list").mockResolvedValue([
    { id: "kohya", state: "ready", featureEnabled: true },
    { id: "anima-fast", state: "not_installed", featureEnabled: true },
    { id: "ai-toolkit", state: "installing", featureEnabled: true },
    { id: "musubi", state: "ready", featureEnabled: true },
    { id: "diffsynth", state: "ready", featureEnabled: true },
  ] as never)
  const wrapper = mountSelector()
  await flushPromises()

  const options = wrapper.findAll('[data-testid="engine-select"] option')
  const values = options.map((option) => option.attributes("value"))
  expect(values).toEqual(["kohya", "anima-fast", "ai-toolkit"])
  expect(values).not.toContain("musubi")
  expect(values).not.toContain("diffsynth")

  const dots = wrapper.findAll(".engine-option .engine-dot")
  expect(dots[0].attributes("data-status")).toBe("ready")
  expect(dots[1].attributes("data-status")).toBe("needs-install")

  const legend = wrapper.get('[data-testid="engine-legend"]')
  expect(legend.text()).toContain("已安装")
  expect(legend.text()).toContain("未下载")
  expect(wrapper.findAll('[data-testid="engine-unsupported"]')).toHaveLength(0)
  wrapper.unmount()
})

it("ignores engine status failures instead of breaking the selector (#443)", async () => {
  vi.spyOn(enginesApi, "list").mockRejectedValue(new Error("offline"))
  const wrapper = mountSelector()
  await flushPromises()

  const values = wrapper.findAll('[data-testid="engine-select"] option').map((option) => option.attributes("value"))
  expect(values).toContain("kohya")
  expect(values).toContain("anima-fast")
  wrapper.unmount()
})

it("emits engine-picked when the user changes the engine dropdown", async () => {
  vi.spyOn(enginesApi, "list").mockResolvedValue([
    { id: "kohya", state: "ready", featureEnabled: true },
    { id: "anima-fast", state: "ready", featureEnabled: true },
  ] as never)
  const wrapper = mountSelector({ engine: "anima-fast" })
  await flushPromises()

  await wrapper.get('[data-testid="engine-select"]').setValue("kohya")
  expect(wrapper.emitted("enginePicked")?.length).toBe(1)
  expect(wrapper.emitted("update:engine")?.at(-1)).toEqual(["kohya"])
  wrapper.unmount()
})
