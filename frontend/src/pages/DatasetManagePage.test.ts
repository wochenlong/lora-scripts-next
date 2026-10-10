// @vitest-environment jsdom
import { KeepAlive, defineComponent } from "vue"
import { flushPromises, mount } from "@vue/test-utils"
import { afterEach, expect, it, vi } from "vitest"
import DatasetManagePage from "./DatasetManagePage.vue"
import { datasetsApi } from "../api/datasets"
import { i18n } from "../i18n"
import { ElDropdown, ElDropdownMenu, ElDropdownItem, ElMessageBox } from "element-plus"

const push = vi.hoisted(() => vi.fn())
vi.mock("vue-router", () => ({ useRouter: () => ({ push }) }))
const wrappers: ReturnType<typeof mount>[] = []
afterEach(() => {
  wrappers.forEach(wrapper => wrapper.unmount())
  wrappers.length = 0
  vi.restoreAllMocks()
})

function render(realDropdown = false) {
  const wrapper = mount(defineComponent({
    components: { KeepAlive, DatasetManagePage },
    template: "<KeepAlive><DatasetManagePage /></KeepAlive>",
  }), {
    global: { plugins: [i18n], components: { ElDropdown, ElDropdownMenu, ElDropdownItem }, stubs: {
      ElDialog: true, ElInput: true, ElSwitch: true, ElSelect: true,
      ElOption: true, ElInputNumber: true, ElCheckbox: true,
      DatasetTrashDialog: true, DatasetUploadDialog: true,
      ...(realDropdown ? {} : { ElDropdown: { template: "<div><slot /></div>" }, ElDropdownMenu: true, ElDropdownItem: true }),
    } },
  })
  wrappers.push(wrapper)
  return wrapper
}

it("shows loading instead of an empty directory while awaiting the server", () => {
  vi.spyOn(datasetsApi, "list").mockReturnValue(new Promise(() => {}))
  const wrapper = render()
  expect(wrapper.get('[role="status"]').text()).toContain(i18n.global.t("datasetManage.loadingTitle"))
  expect(wrapper.text()).not.toContain(i18n.global.t("datasetManage.emptyTitle"))
})

it.each([true, false])("distinguishes empty and missing roots: exists=%s", async exists => {
  vi.spyOn(datasetsApi, "list").mockResolvedValue({ root: "/datasets", exists, datasets: [] })
  const wrapper = render()
  await flushPromises()
  const state = wrapper.get('[role="status"]')
  expect(state.text()).toContain(i18n.global.t(exists ? "datasetManage.emptyTitle" : "datasetManage.missingTitle"))
  expect(state.get("button").text()).toContain(i18n.global.t(exists ? "datasetManage.create" : "datasetManage.rootSettings"))
})

it("shows a retry action on failure and recovers to an empty directory", async () => {
  vi.spyOn(datasetsApi, "list").mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValue({ root: "/datasets", exists: true, datasets: [] })
  const wrapper = render()
  await flushPromises()
  expect(wrapper.get('[role="status"]').text()).toContain(i18n.global.t("datasetManage.loadErrorTitle"))
  await wrapper.get('[role="status"] button').trigger("click")
  await flushPromises()
  expect(wrapper.get('[role="status"]').text()).toContain(i18n.global.t("datasetManage.emptyTitle"))
})

it("filters the list and retains the training lock on folder actions", async () => {
  const overview = { state: "ready" as const, file_count: 12, captioned_count: 10, total_bytes: 1024, updated_at: "2026-10-07T10:00:00Z" }
  vi.spyOn(datasetsApi, "list").mockResolvedValue({ root: "/datasets", exists: true, datasets: [
    { name: "Portrait", path: "/datasets/Portrait", in_use: true, overview },
    { name: "Landscape", path: "/datasets/Landscape", overview },
  ] })
  vi.spyOn(datasetsApi, "overview").mockResolvedValue({ name: "test", overview })
  const wrapper = render()
  await flushPromises()
  expect(wrapper.findAll(".dataset-table tbody tr")).toHaveLength(2)
  const locked = wrapper.findAll(".dataset-row-name").find(button => button.text() === "Portrait")!
  expect(locked.attributes("disabled")).toBeDefined()
  await wrapper.get(".dataset-search input").setValue("LAND")
  expect(wrapper.findAll(".dataset-table tbody tr")).toHaveLength(1)
  expect(wrapper.get(".dataset-table tbody").text()).toContain("Landscape")
  await wrapper.get(".dataset-search input").setValue("missing")
  expect(wrapper.get(".dataset-no-results").text()).toBe(i18n.global.t("datasetManage.noResults"))
})

it("sorts by creation, modification and image count descending", async () => {
  const base = { state: "ready" as const, captioned_count: 0, total_bytes: 0, updated_at: null }
  const entries = [
    { name: "A", path: "/A", created_at: "2026-10-01", updated_at: "2026-10-03", overview: { ...base, file_count: 2 } },
    { name: "B", path: "/B", created_at: "2026-10-03", updated_at: "2026-10-01", overview: { ...base, file_count: 1 } },
    { name: "C", path: "/C", created_at: null, updated_at: "2026-10-02", overview: { ...base, file_count: 5 } },
  ]
  vi.spyOn(datasetsApi, "list").mockResolvedValue({ root: "/datasets", exists: true, datasets: entries })
  vi.spyOn(datasetsApi, "overview").mockImplementation(async name => ({ name, overview: entries.find(item => item.name === name)!.overview }))
  const wrapper = render()
  await flushPromises()
  const names = () => wrapper.findAll(".dataset-row-name").map(item => item.text())
  expect(names()).toEqual(["A", "C", "B"])
  await wrapper.get(".dataset-list-toolbar select").setValue("created")
  expect(names()).toEqual(["B", "A", "C"])
  await wrapper.get(".dataset-list-toolbar select").setValue("images")
  expect(names()).toEqual(["C", "A", "B"])
})

it("opens the dataset detail, not the caption editor, when its name is clicked", async () => {
  const overview = { state: "ready" as const, file_count: 1, captioned_count: 1, total_bytes: 10, updated_at: null }
  vi.spyOn(datasetsApi, "list").mockResolvedValue({ root: "/datasets", exists: true, datasets: [
    { name: "Portrait", path: "/datasets/Portrait", overview },
  ] })
  vi.spyOn(datasetsApi, "overview").mockResolvedValue({ name: "Portrait", overview })
  const wrapper = render()
  await flushPromises()
  await wrapper.get(".dataset-row-name").trigger("click")
  expect(push).toHaveBeenLastCalledWith({ path: "/dataset/manage", query: { dataset: "Portrait" } })
})

it("renders the actual dropdown and dispatches rename", async () => {
  const overview = { state: "ready" as const, file_count: 0, captioned_count: 0, total_bytes: 0, updated_at: null }
  vi.spyOn(datasetsApi, "list").mockResolvedValue({ root: "/datasets", exists: true, datasets: [{ name: "A", path: "/datasets/A", overview }] })
  vi.spyOn(datasetsApi, "overview").mockResolvedValue({ name: "A", overview })
  vi.spyOn(ElMessageBox, "prompt").mockResolvedValue({ value: "B", action: "confirm" } as never)
  const rename = vi.spyOn(datasetsApi, "rename").mockResolvedValue({ name: "B", path: "/datasets/B" })
  const wrapper = render(true)
  await flushPromises()
  expect(wrapper.findComponent(ElDropdown).exists()).toBe(true)
  expect(wrapper.findAllComponents({ name: "ElDropdownItem" }).map(item => item.props("command"))).toEqual(["manage", "rename", "delete"])
  wrapper.findComponent(ElDropdown).vm.$emit("command", "manage")
  expect(push).toHaveBeenLastCalledWith({ path: "/dataset/manage", query: { dataset: "A" } })
  wrapper.findComponent(ElDropdown).vm.$emit("command", "rename")
  await flushPromises()
  expect(rename).toHaveBeenCalledWith("A", "B")
})
