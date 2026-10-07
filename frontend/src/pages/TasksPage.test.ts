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
