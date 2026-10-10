// @vitest-environment jsdom
import { flushPromises, mount } from "@vue/test-utils"
import { afterEach, expect, it, vi } from "vitest"
import { datasetsApi } from "../../api/datasets"
import { i18n } from "../../i18n"
import DatasetUploadDialog from "./DatasetUploadDialog.vue"

afterEach(() => vi.restoreAllMocks())
it("preserves the target subdirectory and dragged folder through conflicts and retry", async () => {
  const path = "nested/source/a.png"
  const check = vi.spyOn(datasetsApi, "checkUpload").mockResolvedValue({ conflicts: [path], invalid: [], ok: 0 })
  const upload = vi.spyOn(datasetsApi, "upload").mockResolvedValueOnce({ dataset: "A", succeeded: [], skipped: [], failed: [{ path, reason: "temporary" }] })
    .mockResolvedValueOnce({ dataset: "A", succeeded: [path], skipped: [], failed: [] })
  const wrapper = mount(DatasetUploadDialog, { props: { modelValue: true, datasetName: "A", targetDirectory: "nested" }, global: {
    plugins: [i18n], stubs: { ElDialog: { template: "<div><slot /><slot name='footer' /></div>" } },
  } })
  const file = new File(["image"], "a.png", { type: "image/png" })
  Object.defineProperty(file, "webkitRelativePath", { value: "source/a.png" })
  const input = wrapper.get('input[webkitdirectory]')
  Object.defineProperty(input.element, "files", { value: [file] })
  await input.trigger("change")
  await wrapper.get(".primary-action").trigger("click")
  await flushPromises()
  expect(check).toHaveBeenCalledWith("A", [path])
  await wrapper.get(".upload-conflict-actions .danger-action").trigger("click")
  await flushPromises()
  expect(upload.mock.calls[0]?.[1][0]?.path).toBe(path)
  expect(upload.mock.calls[0]?.[2]).toBe("overwrite")
  await wrapper.get(".upload-result button").trigger("click")
  await flushPromises()
  expect(upload.mock.calls[1]?.[1][0]?.path).toBe(path)
  expect(wrapper.emitted("uploaded")).toHaveLength(1)
  wrapper.unmount()
})
