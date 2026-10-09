// @vitest-environment jsdom
import { flushPromises, mount } from "@vue/test-utils"
import { createPinia } from "pinia"
import { afterEach, expect, it, vi } from "vitest"
import TasksPage from "./TasksPage.vue"
import { i18n } from "../i18n"

const { push } = vi.hoisted(() => ({ push: vi.fn() }))
vi.mock("vue-router", () => ({ useRouter: () => ({ push }) }))

afterEach(() => {
  vi.restoreAllMocks()
  sessionStorage.clear()
})

it("offers archive browsing with no queue history", async () => {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => new Response(JSON.stringify({
    status: "success", data: String(input).includes("task-archives") ? { archives: [] } : { tasks: [] },
  })))
  const wrapper = mount(TasksPage, {
    global: { plugins: [createPinia(), i18n], stubs: {
      "el-dialog": { props: ["modelValue"], template: '<div v-if="modelValue"><slot /></div>' },
      "el-icon": true, "el-input-number": true, "el-select": true, "el-option": true, RouterLink: true,
    } },
  })
  try {
    await flushPromises()
    const action = wrapper.findAll("button").find(button => button.text() === i18n.global.t("tasks.archives.loadButton"))
    expect(action).toBeDefined()
    await action!.trigger("click")
    await flushPromises()
    expect(wrapper.text()).toContain(i18n.global.t("tasks.archives.empty"))
  } finally { wrapper.unmount() }
})

it("loads a server archive into the matching training module", async () => {
  const archive = {
    id: "archive-1", name: "Saved run", train_type: "anima-lora-fast",
    engine: "anima-fast", config: { model_train_type: "anima-lora-fast", max_train_steps: 100 },
  }
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input)
    let data: unknown = {}
    if (url.includes("/task-archives/")) data = archive
    else if (url.includes("/task-archives")) data = { archives: [archive] }
    else if (url === "/api/tasks") data = { tasks: [{
      id: "task-1", status: "FINISHED", metadata: { train_type: "anima-lora-fast" },
    }] }
    return new Response(JSON.stringify({ status: "success", data }))
  })
  const wrapper = mount(TasksPage, {
    global: {
      plugins: [createPinia(), i18n],
      stubs: {
        "el-dialog": { props: ["modelValue"], template: '<div v-if="modelValue"><slot /><slot name="footer" /></div>' },
        "el-select": true, "el-option": true, "el-icon": true, "el-input-number": true, RouterLink: true,
        LossChart: true, TaskLogPanel: true,
      },
    },
  })
  try {
    await flushPromises()
    const button = (key: string) => wrapper.findAll("button").find((item) => item.text() === i18n.global.t(key))!
    await wrapper.findAll(".tasks-tabs button")[1]!.trigger("click")
    await wrapper.get(".task-row").trigger("click")
    await flushPromises()
    await button("tasks.archives.loadButton").trigger("click")
    await flushPromises()
    expect(wrapper.get(".task-archive-picker").text()).toContain("Saved run")
    await wrapper.get(".task-archive-picker select").setValue("archive-1")
    await button("tasks.archives.load").trigger("click")
    await flushPromises()
    expect(JSON.parse(sessionStorage.getItem("mikazuki-pending-import")!)).toEqual(archive.config)
    expect(push).toHaveBeenCalledWith({
      path: "/training", query: { model: "anima", engine: "anima-fast", target: "lora" },
    })
  } finally {
    wrapper.unmount()
  }
})

const numberStub = {
  props: ["modelValue"],
  emits: ["update:modelValue"],
  template: '<input type="number" :value="modelValue" @input="$emit(\'update:modelValue\', Number($event.target.value))">',
}

function mountTasks(fetchImpl: (url: string, init?: RequestInit) => unknown) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) =>
    new Response(JSON.stringify({ status: "success", data: fetchImpl(String(input), init) })))
  return mount(TasksPage, {
    global: {
      plugins: [createPinia(), i18n],
      stubs: {
        "el-dialog": { props: ["modelValue"], template: '<div v-if="modelValue"><slot /><slot name="footer" /></div>' },
        "el-select": true, "el-option": true, "el-icon": true, RouterLink: true,
        LossChart: true, TaskLogPanel: true,
        "el-input-number": numberStub,
      },
    },
  })
}

it("shows the global auto-retry budget and saves a new one", async () => {
  const posted: { url: string; body: string }[] = []
  const wrapper = mountTasks((url, init) => {
    if (url === "/api/tasks/auto_retry") {
      if (init?.method === "POST") {
        posted.push({ url, body: String(init.body) })
        return { auto_retry_max: 3 }
      }
      return { auto_retry_max: 2 }
    }
    return { tasks: [{ id: "task-1", status: "QUEUED", metadata: { train_type: "sd-lora" }, queue_position: 1 }] }
  })
  try {
    await flushPromises()
    const chip = wrapper.findAll("button").find(b => b.text().includes(i18n.global.t("tasks.autoRetry.armed", { n: 2 })))
    expect(chip).toBeDefined()
    await chip!.trigger("click")
    await flushPromises()
    expect(wrapper.text()).toContain(i18n.global.t("tasks.autoRetry.hint"))
    const numberInput = wrapper.find('input[type="number"]')
    await numberInput.setValue(3)
    const confirm = wrapper.findAll("button").find(b => b.text() === i18n.global.t("tasks.autoRetry.confirm"))
    await confirm!.trigger("click")
    await flushPromises()
    expect(posted).toHaveLength(1)
    expect(JSON.parse(posted[0].body)).toEqual({ count: 3 })
    expect(wrapper.findAll("button").some(b => b.text().includes(i18n.global.t("tasks.autoRetry.armed", { n: 3 })))).toBe(true)
  } finally { wrapper.unmount() }
})

it("batch dialog filters dropped files to .toml and renders partial failures", async () => {
  const enqueued: string[] = []
  const wrapper = mountTasks((url, init) => {
    if (url === "/api/tasks/batch-enqueue") {
      enqueued.push(url)
      return {
        results: [
          { file: "good.toml", ok: true, queued: true, output_name_renamed: { from: "a", to: "a-08230105-0" } },
          { file: "bad.toml", ok: false, error: "无法识别训练类型" },
        ],
        ok_count: 1, fail_count: 1, queue_dir: "/tmp/q",
      }
    }
    if (url === "/api/tasks/auto_retry") return { auto_retry_max: 0 }
    return { tasks: [{ id: "task-1", status: "QUEUED", metadata: { train_type: "sd-lora" }, queue_position: 1 }] }
  })
  try {
    await flushPromises()
    const entry = wrapper.findAll("button").find(b => b.text() === i18n.global.t("tasks.batchEnqueue.button"))
    expect(entry).toBeDefined()
    await entry!.trigger("click")
    await flushPromises()
    const dropzone = wrapper.find(".upload-dropzone")
    expect(dropzone.exists()).toBe(true)
    const toml = new File(["model_train_type = 'sd-lora'"], "good.toml")
    const exe = new File(["MZ"], "evil.exe")
    await dropzone.trigger("drop", { dataTransfer: { files: [toml, exe] } })
    await flushPromises()
    expect(wrapper.text()).toContain(i18n.global.t("tasks.batchEnqueue.selected", { n: 1 }))
    const confirm = wrapper.findAll("button").find(b => b.text() === i18n.global.t("tasks.batchEnqueue.confirm"))
    await confirm!.trigger("click")
    await flushPromises()
    expect(enqueued).toHaveLength(1)
    expect(wrapper.text()).toContain("good.toml")
    expect(wrapper.text()).toContain(i18n.global.t("tasks.batchEnqueue.renamed", { from: "a", to: "a-08230105-0" }))
    expect(wrapper.text()).toContain("bad.toml")
    expect(wrapper.text()).toContain("无法识别训练类型")
  } finally { wrapper.unmount() }
})
