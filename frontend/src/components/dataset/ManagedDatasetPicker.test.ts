// @vitest-environment jsdom
import { flushPromises, mount } from "@vue/test-utils"
import { afterEach, expect, it, vi } from "vitest"
import { i18n } from "../../i18n"
import { datasetsApi } from "../../api/datasets"
import ManagedDatasetPicker from "./ManagedDatasetPicker.vue"
import PathPickerDialog from "../PathPickerDialog.vue"
import { schemasApi } from "../../api/schemas"
import { ApiError } from "../../api/client"
import { writePathPickerPreference } from "../../utils/pathPickerPreference"

afterEach(() => { vi.restoreAllMocks(); localStorage.clear() })

it("browses nested managed folders and emits the server path without starting work", async () => {
  vi.spyOn(datasetsApi, "list").mockResolvedValue({ root: "/data", exists: true, datasets: [
    { name: "Portrait", path: "/data/Portrait", overview: null },
  ] })
  vi.spyOn(datasetsApi, "contents").mockResolvedValueOnce({
    name: "Portrait", path: "/data/Portrait", relative_path: "", in_use: false,
    entries: [{ name: "people", path: "people", kind: "directory" }],
  }).mockResolvedValueOnce({
    name: "Portrait", path: "/data/Portrait/people", relative_path: "people", in_use: false, entries: [],
  })
  const wrapper = mount(ManagedDatasetPicker, { global: { plugins: [i18n], stubs: { ElDialog: { template: "<div><slot /><slot name='footer' /></div>" }, PathPickerDialog: true } } })
  await wrapper.get("button").trigger("click")
  await flushPromises()
  await wrapper.get(".managed-picker-folder").trigger("click")
  await flushPromises()
  await wrapper.get(".managed-picker-folder").trigger("click")
  await flushPromises()
  await wrapper.get(".managed-picker-confirm").trigger("click")
  expect(wrapper.emitted("select")).toEqual([["/data/Portrait/people"]])
  wrapper.unmount()
})

it("requires confirmation for a manually entered server folder", async () => {
  vi.spyOn(datasetsApi, "list").mockResolvedValue({ root: "/data", exists: true, datasets: [] })
  const wrapper = mount(ManagedDatasetPicker, { global: { plugins: [i18n], stubs: { ElDialog: { template: "<div><slot /><slot name='footer' /></div>" }, PathPickerDialog: true } } })
  await wrapper.get("button").trigger("click")
  await flushPromises()
  await wrapper.get('[data-source="server"]').trigger("click")
  await wrapper.get(".dataset-source-path input").setValue("/data/external")
  expect(wrapper.emitted("select")).toBeUndefined()
  await wrapper.get(".managed-picker-confirm").trigger("click")
  expect(wrapper.emitted("select")).toEqual([["/data/external"]])
  wrapper.unmount()
})

it("opens the server browser from a mounted closed state and keeps selection pending", async () => {
  writePathPickerPreference("web")
  vi.spyOn(datasetsApi, "list").mockResolvedValue({ root: "/data", exists: true, datasets: [] })
  const wrapper = mount(ManagedDatasetPicker, { global: { plugins: [i18n], stubs: { ElDialog: { template: "<div><slot /><slot name='footer' /></div>" }, PathPickerDialog: true } } })
  expect(wrapper.getComponent(PathPickerDialog).props("modelValue")).toBe(false)
  await wrapper.get("button").trigger("click")
  await flushPromises()
  await wrapper.get('[data-source="server"]').trigger("click")
  await wrapper.get(".dataset-source-path button").trigger("click")
  expect(wrapper.getComponent(PathPickerDialog).props("modelValue")).toBe(true)
  wrapper.getComponent(PathPickerDialog).vm.$emit("confirm", "/data/picked")
  await flushPromises()
  expect(wrapper.emitted("select")).toBeUndefined()
  await wrapper.get(".managed-picker-confirm").trigger("click")
  expect(wrapper.emitted("select")).toEqual([["/data/picked"]])
  wrapper.unmount()
})

it("uses the native folder picker and waits for load confirmation", async () => {
  writePathPickerPreference("native")
  const native = vi.spyOn(schemasApi, "pickFile").mockResolvedValue({ path: "D:/photos" })
  vi.spyOn(datasetsApi, "list").mockResolvedValue({ root: "/data", exists: true, datasets: [] })
  const wrapper = mount(ManagedDatasetPicker, { global: { plugins: [i18n], stubs: { ElDialog: { template: "<div><slot /><slot name='footer' /></div>" }, PathPickerDialog: true } } })
  await wrapper.get("button").trigger("click")
  await flushPromises()
  await wrapper.get('[data-source="server"]').trigger("click")
  await wrapper.get(".dataset-source-path button").trigger("click")
  await flushPromises()
  expect(native).toHaveBeenCalledWith("folder")
  expect(wrapper.getComponent(PathPickerDialog).props("modelValue")).toBe(false)
  expect(wrapper.emitted("select")).toBeUndefined()
  await wrapper.get(".managed-picker-confirm").trigger("click")
  expect(wrapper.emitted("select")).toEqual([["D:/photos"]])
  wrapper.unmount()
})

it("keeps a typed path when native folder selection is cancelled", async () => {
  writePathPickerPreference("native")
  vi.spyOn(schemasApi, "pickFile").mockRejectedValue(new ApiError("cancelled", "fail", { status: "fail", data: { code: "CANCELLED" } }))
  vi.spyOn(datasetsApi, "list").mockResolvedValue({ root: "/data", exists: true, datasets: [] })
  const wrapper = mount(ManagedDatasetPicker, { props: { initialPath: "D:/existing" }, global: { plugins: [i18n], stubs: { ElDialog: { template: "<div><slot /><slot name='footer' /></div>" }, PathPickerDialog: true } } })
  await wrapper.get("button").trigger("click")
  await flushPromises()
  await wrapper.get('[data-source="server"]').trigger("click")
  await wrapper.get(".dataset-source-path button").trigger("click")
  await flushPromises()
  expect(wrapper.getComponent(PathPickerDialog).props("modelValue")).toBe(false)
  expect((wrapper.get(".dataset-source-path input").element as HTMLInputElement).value).toBe("D:/existing")
  wrapper.unmount()
})
