// @vitest-environment jsdom
import { flushPromises, mount } from "@vue/test-utils"
import { createPinia } from "pinia"
import { ElMessage } from "element-plus"
import { defineComponent, type PropType } from "vue"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import Schema from "schemastery"
import TrainingPage from "./TrainingPage.vue"
import { i18n } from "../i18n"
import type { AdaptedSchema } from "../schema/adapter"
import { loadTrainingSchema } from "../schema/loader"
import { schemasApi } from "../api/schemas"
import { tasksApi } from "../api/tasks"
import { trainingApi } from "../api/training"

vi.mock("../schema/loader", () => ({
  loadTrainingSchema: vi.fn(),
}))

vi.mock("../api/schemas", () => ({
  schemasApi: {
    graphicCards: vi.fn(),
    files: vi.fn(),
  },
}))

vi.mock("../api/tasks", () => ({
  tasksApi: {
    list: vi.fn(),
    terminate: vi.fn(),
  },
}))

vi.mock("../api/training", () => ({
  trainingApi: {
    validateImport: vi.fn(),
    normalizeExport: vi.fn(),
    presets: vi.fn(),
    run: vi.fn(),
    saveParams: vi.fn(),
    animaFastPreflight: vi.fn(),
    musubiPreflight: vi.fn(),
    aiToolkitPreflight: vi.fn(),
  },
}))

vi.mock("vue-router", () => ({
  useRouter: () => ({ push: vi.fn() }),
  RouterLink: { props: ["to"], template: "<a><slot /></a>" },
}))

vi.mock("element-plus", async () => {
  const actual = await vi.importActual<typeof import("element-plus")>("element-plus")
  return {
    ...actual,
    ElMessage: {
      success: vi.fn(),
      error: vi.fn(),
      warning: vi.fn(),
      info: vi.fn(),
    },
    ElMessageBox: {
      confirm: vi.fn(),
    },
  }
})

const schema: AdaptedSchema = {
  name: "training",
  hash: "training",
  schema: Schema.object({}),
  sections: [{
    id: "main",
    title: "Main",
    fields: [
      { key: "mode", type: "string", options: ["basic", "advanced"], defaultValue: "basic", conditions: [] },
      { key: "sample_cfg", type: "number", defaultValue: 4, min: 1, conditions: [] },
      { key: "keep_text", type: "string", defaultValue: "schema", conditions: [] },
      { key: "tags", type: "array", defaultValue: ["schema-tag"], conditions: [] },
      { key: "optional_note", type: "string", conditions: [] },
      { key: "advanced_only", type: "string", defaultValue: "adv", conditions: [{ key: "mode", value: "advanced" }] },
    ],
  }],
}

const animaFastSchema: AdaptedSchema = {
  ...schema,
  name: "anima-lora-fast",
  sections: [{
    ...schema.sections[0],
    fields: [
      ...schema.sections[0].fields,
      { key: "training_duration_mode", type: "string", options: ["epoch", "steps"], defaultValue: "epoch", conditions: [] },
      { key: "max_train_epochs", type: "number", defaultValue: 1, min: 1, conditions: [{ key: "training_duration_mode", value: "epoch" }] },
      { key: "max_train_steps", type: "number", defaultValue: 100, min: 1, conditions: [{ key: "training_duration_mode", value: "steps" }] },
    ],
  }],
}

const DynamicSchemaFormStub = defineComponent({
  props: {
    modelValue: { type: Object as PropType<Record<string, unknown>>, required: true },
    errors: { type: Object as PropType<Record<string, string>>, required: true },
    effectiveDefaults: { type: Object as PropType<Record<string, unknown>>, required: true },
  },
  emits: ["update:modelValue", "reset-field"],
  setup(props, { emit }) {
    const patch = (value: Record<string, unknown>) => emit("update:modelValue", { ...props.modelValue, ...value })
    const mutateTags = () => {
      const next = { ...props.modelValue }
      if (Array.isArray(next.tags)) next.tags.push("polluted")
      emit("update:modelValue", next)
    }
    return { patch, mutateTags }
  },
  template: `
    <div class="dynamic-schema-form-stub">
      <button class="apply-draft" @click="patch({ mode: 'advanced', sample_cfg: 9, keep_text: 'keep', tags: ['changed'], advanced_only: 'branch-custom', optional_note: 'filled' })">apply</button>
      <button class="invalid-sample" @click="patch({ sample_cfg: 0 })">invalid</button>
      <button class="set-optional" @click="patch({ optional_note: 'filled' })">optional</button>
      <button class="set-mode-advanced" @click="patch({ mode: 'advanced' })">mode advanced</button>
      <button class="set-tags" @click="patch({ tags: ['changed'] })">set tags</button>
      <button class="set-advanced-only" @click="patch({ advanced_only: 'branch-custom' })">set advanced</button>
      <button class="set-duration-steps" @click="patch({ training_duration_mode: 'steps' })">steps</button>
      <button class="mutate-tags" @click="mutateTags">mutate tags</button>
      <button class="reset-sample" @click="$emit('reset-field', 'sample_cfg')">reset sample</button>
      <button class="reset-optional" @click="$emit('reset-field', 'optional_note')">reset optional</button>
      <button class="reset-mode" @click="$emit('reset-field', 'mode')">reset mode</button>
      <button class="reset-tags" @click="$emit('reset-field', 'tags')">reset tags</button>
      <pre class="model">{{ JSON.stringify(modelValue) }}</pre>
      <pre class="errors">{{ JSON.stringify(errors) }}</pre>
      <pre class="defaults">{{ JSON.stringify(effectiveDefaults) }}</pre>
    </div>
  `,
})

function mountPage(schemaName = "test-schema") {
  return mount(TrainingPage, {
    props: {
      title: "Training",
      area: "Area",
      schemaName,
      fieldDefaults: { sample_cfg: 5, tags: ["module-tag"] },
    },
    global: {
      plugins: [i18n, createPinia()],
      directives: { loading: {} },
      stubs: {
        DynamicSchemaForm: DynamicSchemaFormStub,
        ModelAssetsTools: { template: "<div />" },
        SectionToc: { template: "<div />" },
        RouterLink: { props: ["to"], template: "<a><slot /></a>" },
        "el-dialog": { template: "<div><slot /></div>" },
      },
    },
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  sessionStorage.clear()
  vi.spyOn(window, "setInterval").mockReturnValue(1 as unknown as ReturnType<typeof window.setInterval>)
  vi.spyOn(window, "clearInterval").mockImplementation(() => undefined)
  vi.mocked(loadTrainingSchema).mockResolvedValue(schema)
  vi.mocked(schemasApi.graphicCards).mockResolvedValue([])
  vi.mocked(tasksApi.list).mockResolvedValue([])
  vi.mocked(trainingApi.validateImport).mockResolvedValue({ result: "ok" })
  vi.mocked(trainingApi.saveParams).mockResolvedValue({ ok: true, page_train_type: "test-schema" })
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe("TrainingPage single-field reset", () => {
  it("migrates legacy Qwen component-mode autosaves", async () => {
    const qwenSchema: AdaptedSchema = {
      ...schema,
      name: "qwen-image-21-lora",
      sections: [{
        ...schema.sections[0],
        fields: [
          ...schema.sections[0].fields,
          { key: "model_input_mode", type: "string", options: ["model_repository", "comfyui_files"], defaultValue: "model_repository", conditions: [] },
          { key: "dit_path", type: "string", conditions: [{ key: "model_input_mode", value: "comfyui_files" }] },
        ],
      }],
    }
    vi.mocked(loadTrainingSchema).mockResolvedValue(qwenSchema)
    localStorage.setItem("configs-qwen-image-21-lora-autosave", JSON.stringify({
      model_input_mode: "components",
      dit_path: "D:/models/dit.safetensors",
    }))

    const wrapper = mountPage("qwen-image-21-lora")
    await flushPromises()

    expect(wrapper.get(".model").text()).toContain('"model_input_mode":"comfyui_files"')
    expect(wrapper.get(".preview-panel pre").text()).toContain('dit_path = "D:/models/dit.safetensors"')
    wrapper.unmount()
  })

  it("restores module override defaults and clears stale field errors without changing other values", async () => {
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get(".apply-draft").trigger("click")
    await wrapper.get(".invalid-sample").trigger("click")
    await wrapper.get(".schema-validate").trigger("click")
    expect(wrapper.get(".errors").text()).toContain("sample_cfg")
    expect(vi.mocked(ElMessage.error)).toHaveBeenCalled()

    await wrapper.get(".reset-sample").trigger("click")
    await flushPromises()

    expect(wrapper.get(".model").text()).toContain('"sample_cfg":5')
    expect(wrapper.get(".model").text()).toContain('"keep_text":"keep"')
    expect(wrapper.get(".model").text()).toContain('"advanced_only":"branch-custom"')
    expect(wrapper.get(".model").text()).toContain('"optional_note":"filled"')
    expect(wrapper.get(".errors").text()).not.toContain("sample_cfg")
    expect(wrapper.get(".preview-panel pre").text()).toContain("sample_cfg = 5")
    wrapper.unmount()
  })

  it("resets arrays with cloned defaults, drops undefined fields, and updates conditional output", async () => {
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get(".set-optional").trigger("click")
    await wrapper.get(".set-mode-advanced").trigger("click")
    await wrapper.get(".set-advanced-only").trigger("click")
    await wrapper.get(".set-tags").trigger("click")
    await flushPromises()
    expect(wrapper.get(".preview-panel pre").text()).toContain('optional_note = "filled"')
    expect(wrapper.get(".preview-panel pre").text()).toContain('advanced_only = "branch-custom"')

    await wrapper.get(".reset-optional").trigger("click")
    await wrapper.get(".reset-tags").trigger("click")
    await flushPromises()
    expect(wrapper.get(".preview-panel pre").text()).not.toContain("optional_note =")
    expect(wrapper.get(".preview-panel pre").text()).toContain('tags = [ "module-tag" ]')

    await wrapper.get(".mutate-tags").trigger("click")
    await flushPromises()
    expect(wrapper.get(".defaults").text()).toContain('"tags":["module-tag"]')
    expect(wrapper.get(".defaults").text()).not.toContain("polluted")

    await wrapper.get(".reset-mode").trigger("click")
    await flushPromises()
    expect(wrapper.get(".preview-panel pre").text()).not.toContain("advanced_only =")
    expect(wrapper.get(".preview-panel pre").text()).toContain('mode = "basic"')
    wrapper.unmount()
  })

  it("normalizes unsafe carry-over when autosave JSON is malformed", async () => {
    const torchCompileSchema: AdaptedSchema = {
      ...schema,
      name: "anima-lora-fast",
      sections: [{
        ...schema.sections[0],
        fields: [
          ...schema.sections[0].fields,
          { key: "attn_mode", type: "string", defaultValue: "", conditions: [] },
          { key: "torch_compile", type: "boolean", defaultValue: false, conditions: [] },
        ],
      }],
    }
    vi.mocked(loadTrainingSchema).mockResolvedValue(torchCompileSchema)
    sessionStorage.setItem("mikazuki-carry-over", JSON.stringify({ attn_mode: "torch", torch_compile: true }))
    localStorage.setItem("configs-anima-lora-fast-autosave", "{malformed")

    const wrapper = mountPage("anima-lora-fast")
    await flushPromises()

    expect(wrapper.get(".model").text()).toContain('"torch_compile":false')
    wrapper.unmount()
  })
})

describe("TrainingPage Anima Fast imports", () => {
  it("restores the default step count when the user switches from Epoch to Steps", async () => {
    vi.mocked(loadTrainingSchema).mockResolvedValue(animaFastSchema)

    const wrapper = mountPage("anima-lora-fast")
    await flushPromises()
    expect(wrapper.get(".model").text()).not.toContain("max_train_steps")

    await wrapper.get(".set-duration-steps").trigger("click")

    expect(wrapper.get(".model").text()).toContain('"training_duration_mode":"steps"')
    expect(wrapper.get(".model").text()).toContain('"max_train_steps":100')
    expect(wrapper.get(".preview-panel pre").text()).toContain("max_train_steps = 100")
    wrapper.unmount()
  })

  it("keeps a step-only import step-only in the preview", async () => {
    vi.mocked(loadTrainingSchema).mockResolvedValue(animaFastSchema)
    vi.mocked(trainingApi.validateImport).mockResolvedValue({
      result: "ok",
      config: { max_train_steps: 100 },
    })
    sessionStorage.setItem("mikazuki-pending-import", JSON.stringify({ max_train_steps: 100 }))

    const wrapper = mountPage("anima-lora-fast")
    await flushPromises()

    expect(wrapper.get(".model").text()).toContain('"training_duration_mode":"steps"')
    expect(wrapper.get(".preview-panel pre").text()).toContain("max_train_steps = 100")
    expect(wrapper.get(".preview-panel pre").text()).not.toContain("max_train_epochs")
    wrapper.unmount()
  })

  it("uses Epoch for a dual-field import and preserves the backend notice", async () => {
    vi.mocked(loadTrainingSchema).mockResolvedValue(animaFastSchema)
    vi.mocked(trainingApi.validateImport).mockResolvedValue({
      result: "ok",
      config: { max_train_epochs: 3, max_train_steps: 100 },
      notice: "Backend import notice",
    })
    sessionStorage.setItem("mikazuki-pending-import", JSON.stringify({ max_train_epochs: 3, max_train_steps: 100 }))

    const wrapper = mountPage("anima-lora-fast")
    await flushPromises()

    expect(wrapper.get(".model").text()).toContain('"training_duration_mode":"epoch"')
    expect(wrapper.get(".preview-panel pre").text()).toContain("max_train_epochs = 3")
    expect(wrapper.get(".preview-panel pre").text()).not.toContain("max_train_steps")
    expect(vi.mocked(ElMessage.info)).toHaveBeenCalledWith(i18n.global.t("training.importMsg.animaFastDurationConflict"))
    expect(vi.mocked(ElMessage.info)).toHaveBeenCalledWith("Backend import notice")
    wrapper.unmount()
  })

  it("does not report a conflict when an imported duration field is blank", async () => {
    vi.mocked(loadTrainingSchema).mockResolvedValue(animaFastSchema)
    vi.mocked(trainingApi.validateImport).mockResolvedValue({
      result: "ok",
      config: { max_train_epochs: "", max_train_steps: 100 },
    })
    sessionStorage.setItem("mikazuki-pending-import", JSON.stringify({ max_train_epochs: "", max_train_steps: 100 }))

    const wrapper = mountPage("anima-lora-fast")
    await flushPromises()

    expect(wrapper.get(".model").text()).toContain('"training_duration_mode":"steps"')
    expect(vi.mocked(ElMessage.info)).not.toHaveBeenCalledWith(i18n.global.t("training.importMsg.animaFastDurationConflict"))
    wrapper.unmount()
  })

  it("does not show the Epoch conflict notice when an explicit Steps import contains both fields", async () => {
    vi.mocked(loadTrainingSchema).mockResolvedValue(animaFastSchema)
    vi.mocked(trainingApi.validateImport).mockResolvedValue({
      result: "ok",
      config: { training_duration_mode: "steps", max_train_epochs: 3, max_train_steps: 100 },
    })
    sessionStorage.setItem("mikazuki-pending-import", JSON.stringify({
      training_duration_mode: "steps",
      max_train_epochs: 3,
      max_train_steps: 100,
    }))

    const wrapper = mountPage("anima-lora-fast")
    await flushPromises()

    expect(wrapper.get(".model").text()).toContain('"training_duration_mode":"steps"')
    expect(wrapper.get(".model").text()).not.toContain("max_train_epochs")
    expect(vi.mocked(ElMessage.info)).not.toHaveBeenCalledWith(i18n.global.t("training.importMsg.animaFastDurationConflict"))
    wrapper.unmount()
  })
})
