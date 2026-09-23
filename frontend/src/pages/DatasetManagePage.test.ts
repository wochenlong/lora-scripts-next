// @vitest-environment jsdom
import { defineComponent } from "vue"
import { flushPromises, mount } from "@vue/test-utils"
import { describe, expect, it, vi } from "vitest"
import DatasetManagePage from "./DatasetManagePage.vue"
import { i18n } from "../i18n"
import { datasetsApi, type DatasetEntry } from "../api/datasets"

vi.mock("vue-router", () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock("../api/datasets", async () => {
  const actual = await vi.importActual<typeof import("../api/datasets")>("../api/datasets")
  return {
    ...actual,
    datasetsApi: {
      list: vi.fn(),
      overview: vi.fn(),
      updateRoot: vi.fn(),
      create: vi.fn(),
      deleteDataset: vi.fn(),
    },
  }
})

function entry(overview: Partial<DatasetEntry["overview"] & object> = {}): DatasetEntry {
  return {
    name: "ds",
    path: "/data/ds",
    overview: {
      state: "ready",
      type: "image",
      type_confidence: "detected",
      targets: null,
      refs: [],
      file_count: 10,
      captioned_count: 8,
      paired_count: null,
      unpaired_count: null,
      orphan_ref_count: null,
      total_bytes: 1024,
      updated_at: null,
      computed_at: new Date().toISOString(),
      error: null,
      ...overview,
    } as DatasetEntry["overview"],
    in_use: [],
  }
}

const harness = defineComponent({
  components: { Page: DatasetManagePage },
  template: "<KeepAlive><Page /></KeepAlive>",
})

async function mountPage(datasets: DatasetEntry[]) {
  vi.mocked(datasetsApi.list).mockResolvedValue({ root: "/data", exists: true, datasets })
  const wrapper = mount(harness, {
    global: {
      plugins: [i18n],
      stubs: { ElDialog: true, ElInput: true, ElSwitch: true, DatasetUploadDialog: true, DatasetTrashDialog: true },
    },
  })
  await flushPromises()
  return wrapper
}

describe("DatasetManagePage type badge", () => {
  it("shows image badge without pairing stats for plain datasets", async () => {
    const wrapper = await mountPage([entry()])
    expect(wrapper.find(".dataset-type-badge-image").exists()).toBe(true)
    expect(wrapper.text()).not.toContain("配对完整")
    wrapper.unmount()
  })

  it("shows edit badge, targets label and pairing stats for edit datasets", async () => {
    const wrapper = await mountPage([
      entry({ type: "image_edit", targets: "targets", refs: ["ref"], file_count: 5, captioned_count: 4, paired_count: 4 }),
    ])
    expect(wrapper.find(".dataset-type-badge-edit").exists()).toBe(true)
    const text = wrapper.text()
    expect(text).toContain("目标图")
    expect(text).toContain("配对完整")
    wrapper.unmount()
  })

  it("warns when targets lack references or refs are orphaned", async () => {
    const wrapper = await mountPage([
      entry({ type: "image_edit", targets: "targets", refs: ["ref"], unpaired_count: 2, orphan_ref_count: 1 }),
    ])
    const warning = wrapper.find(".dataset-card-warning")
    expect(warning.exists()).toBe(true)
    expect(warning.text()).toContain("2")
    expect(warning.text()).toContain("1")
    wrapper.unmount()
  })

  it("marks candidate detection as uncertain", async () => {
    const wrapper = await mountPage([entry({ type_confidence: "candidate" })])
    expect(wrapper.find(".dataset-type-badge-uncertain").exists()).toBe(true)
    wrapper.unmount()
  })
})

describe("DatasetManagePage in-use lock", () => {
  it("shows in-use badge and disables upload and delete", async () => {
    const busy = { ...entry(), in_use: [{ task_id: "t-1", job_label: "Training" }] }
    const wrapper = await mountPage([busy])
    expect(wrapper.find(".dataset-inuse-badge").exists()).toBe(true)
    const buttons = wrapper.findAll(".dataset-card-actions button, .dataset-card-delete")
    const disabled = buttons.filter((button) => button.attributes("disabled") !== undefined)
    expect(disabled.length).toBeGreaterThanOrEqual(2)
    const download = wrapper.find(".dataset-card-actions a")
    expect(download.attributes("disabled")).toBeUndefined()
    wrapper.unmount()
  })

  it("keeps mutations enabled when no task references the dataset", async () => {
    const wrapper = await mountPage([entry()])
    expect(wrapper.find(".dataset-inuse-badge").exists()).toBe(false)
    const deleteButton = wrapper.find(".dataset-card-delete")
    expect(deleteButton.attributes("disabled")).toBeUndefined()
    wrapper.unmount()
  })
})
