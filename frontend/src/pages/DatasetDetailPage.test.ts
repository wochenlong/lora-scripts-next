// @vitest-environment jsdom
import { flushPromises, mount } from "@vue/test-utils"
import { afterEach, expect, it, vi } from "vitest"
import { i18n } from "../i18n"
import { datasetsApi } from "../api/datasets"
import DatasetDetailPage from "./DatasetDetailPage.vue"
const push = vi.hoisted(() => vi.fn())
vi.mock("vue-router", () => ({ useRouter: () => ({ push }) }))
afterEach(() => vi.restoreAllMocks())

it("keeps previews private until requested and sends the selected directory to tools", async () => {
  vi.spyOn(datasetsApi, "contents").mockResolvedValue({
    name: "Portrait", path: "/data/Portrait/nested", relative_path: "nested", in_use: false,
    entries: [{ name: "a.png", path: "nested/a.png", kind: "image" }],
  })
  const wrapper = mount(DatasetDetailPage, { props: { name: "Portrait", directory: "nested" }, global: {
    plugins: [i18n], stubs: { DatasetUploadDialog: true, ElDialog: true, ElInput: true },
  } })
  await flushPromises()
  expect(wrapper.find("img").exists()).toBe(false)
  expect(wrapper.get('[data-action="download"]').attributes("href")).toContain("Portrait")
  expect(wrapper.find('[data-action="copy"]').exists()).toBe(true)
  await wrapper.get('[data-action="previews"]').trigger("click")
  expect(wrapper.get("img").attributes("src")).toContain("nested%2Fa.png")
  await wrapper.get('[data-action="editor"]').trigger("click")
  expect(push).toHaveBeenLastCalledWith({ path: "/dataset/editor", query: { path: "/data/Portrait/nested" } })
  wrapper.unmount()
})

it("does not navigate away from a new page when preprocessing finishes after unmount", async () => {
  push.mockClear()
  vi.spyOn(datasetsApi, "contents").mockResolvedValue({ name: "A", path: "/A", relative_path: "", in_use: false, entries: [] })
  let finish!: (value: { name: string; path: string; copied: number; flattened: number; deduped: number }) => void
  vi.spyOn(datasetsApi, "copy").mockReturnValue(new Promise(resolve => { finish = resolve }))
  const wrapper = mount(DatasetDetailPage, { props: { name: "A" }, global: {
    plugins: [i18n], stubs: { DatasetUploadDialog: true, ElInput: true, ElDialog: { template: "<div><slot /><slot name='footer' /></div>" } },
  } })
  await flushPromises()
  await wrapper.findAll("button").find(button => button.text() === i18n.global.t("datasetManage.preprocess"))!.trigger("click")
  await wrapper.findAll("button").find(button => button.text() === i18n.global.t("datasetManage.preprocessConfirm"))!.trigger("click")
  wrapper.unmount()
  finish({ name: "A-white", path: "/A-white", copied: 1, flattened: 1, deduped: 0 })
  await flushPromises()
  expect(push).not.toHaveBeenCalled()
})
