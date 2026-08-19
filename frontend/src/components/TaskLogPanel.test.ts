// @vitest-environment jsdom
import { flushPromises, mount } from "@vue/test-utils"
import { beforeEach, describe, expect, it, vi } from "vitest"
import TaskLogPanel from "./TaskLogPanel.vue"
import { tasksApi } from "../api/tasks"
import { i18n } from "../i18n"

vi.mock("../api/tasks", () => ({
  tasksApi: { logTail: vi.fn() },
  trainLogStreamUrl: (taskId: string) => `/api/train/log/stream/${taskId}`,
}))

const logTail = vi.mocked(tasksApi.logTail)

function mountPanel(status: "RUNNING" | "FAILED" | "FINISHED" = "RUNNING") {
  return mount(TaskLogPanel, { props: { taskId: "task-1", status }, global: { plugins: [i18n] } })
}

describe("TaskLogPanel", () => {
  beforeEach(() => {
    logTail.mockReset()
  })

  it("starts collapsed and shows no alert for a clean log", async () => {
    logTail.mockResolvedValue({ task_id: "task-1", lines: ["step 1", "step 2"], total: 2, done: false })
    const wrapper = mountPanel()
    await flushPromises()
    expect(wrapper.find(".log-body").exists()).toBe(false)
    expect(wrapper.find(".log-alert").exists()).toBe(false)
  })

  it("shows the error alert for failed tasks and error lines", async () => {
    logTail.mockResolvedValue({ task_id: "task-1", lines: ["ok"], total: 1, done: true })
    const failed = mountPanel("FAILED")
    await flushPromises()
    expect(failed.find(".log-alert").exists()).toBe(true)

    logTail.mockResolvedValue({ task_id: "task-1", lines: ["Traceback (most recent call last):"], total: 1, done: true })
    const crashed = mountPanel("FINISHED")
    await flushPromises()
    expect(crashed.find(".log-alert").exists()).toBe(true)
  })

  it("renders tailed lines when expanded via the polling fallback", async () => {
    logTail.mockResolvedValue({ task_id: "task-1", lines: ["first", "CUDA out of memory"], total: 2, done: true })
    const wrapper = mountPanel("FINISHED")
    await flushPromises()
    await wrapper.get(".log-header").trigger("click")
    await flushPromises()
    expect(wrapper.find(".log-lines").text()).toContain("CUDA out of memory")
    expect(wrapper.find(".log-alert").exists()).toBe(true)
    expect(wrapper.get(".log-toolbar button:nth-child(2)").attributes("disabled")).toBeUndefined()
  })

  it("marks logs from other sessions as unavailable", async () => {
    logTail.mockRejectedValue(new Error("404"))
    const wrapper = mountPanel("FINISHED")
    await flushPromises()
    await wrapper.get(".log-header").trigger("click")
    await flushPromises()
    expect(wrapper.find(".log-hint").text()).toContain("当前服务会话")
    expect(wrapper.find(".log-alert").exists()).toBe(false)
  })
})
