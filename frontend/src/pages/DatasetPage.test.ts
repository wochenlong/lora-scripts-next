/* eslint-disable vue/one-component-per-file -- test harnesses */
// @vitest-environment jsdom
import { defineComponent, h, nextTick, onActivated, onDeactivated, onMounted, onUnmounted, ref } from "vue"
import { flushPromises, mount } from "@vue/test-utils"
import { afterEach, describe, expect, it, vi } from "vitest"
import DatasetPage from "./DatasetPage.vue"
import TaggerPage from "./TaggerPage.vue"
import DatasetEditorPage from "./DatasetEditorPage.vue"
import { i18n } from "../i18n"
import { datasetApi } from "../api/dataset"
import { useDatasetEditorSession } from "../composables/useDatasetEditorSession"

vi.mock("../stores/tagger", async () => {
  const { ref } = await import("vue")
  return {
    useTaggerStore: () => ({
      status: ref({
        phase: "idle",
        message: "",
        download: { percent: 0, current: 0, total: 0, filename: "" },
        tagging: { current: 0, total: 0, filename: "" },
      }),
      error: ref(""),
      submitting: ref(false),
      busy: ref(false),
      refresh: vi.fn().mockResolvedValue(undefined),
      start: vi.fn(),
      prefetch: vi.fn(),
      cancel: vi.fn(),
      reset: vi.fn(),
    }),
  }
})

vi.mock("../api/dataset", () => ({
  datasetApi: {
    scan: vi.fn(),
    tagTranslations: vi.fn().mockResolvedValue({ items: [], provider: "danbooru", locale: "zh-CN" }),
    tagTranslationConfig: vi.fn(),
    saveTagTranslationConfig: vi.fn(),
    saveCaption: vi.fn(),
    batchEdit: vi.fn(),
    history: vi.fn().mockResolvedValue({ can_undo: false, can_redo: false, changes: [] }),
    undo: vi.fn(),
    redo: vi.fn(),
  },
}))

vi.mock("../api/datasets", () => ({
  datasetFileUrl: vi.fn((name: string, path: string) => `/datasets/${name}/${path}`),
  datasetsApi: {
    list: vi.fn().mockResolvedValue({ datasets: [] }),
    deleteFiles: vi.fn(),
  },
}))

vi.mock("../composables/useServerPathPick", async () => {
  const { ref } = await import("vue")
  return {
    useServerPathPick: () => ({
      open: ref(false),
      mode: ref("folder"),
      initialPath: ref(""),
      nameFilter: ref(""),
      pick: vi.fn().mockResolvedValue(null),
      onConfirm: vi.fn(),
      onCancel: vi.fn(),
    }),
  }
})

const routerLinkStub = { props: ["to"], template: "<a><slot /></a>" }

afterEach(() => {
  vi.restoreAllMocks()
})

describe("DatasetPage tab keep-alive", () => {
  function lifecycleStub(name: string, events: string[]) {
    return defineComponent({
      name,
      setup() {
        onMounted(() => events.push("mount"))
        onActivated(() => events.push("activate"))
        onDeactivated(() => events.push("deactivate"))
        onUnmounted(() => events.push("unmount"))
        return () => h("div", name)
      },
    })
  }

  it("keeps both tab pages alive across round-trip switches", async () => {
    const editorEvents: string[] = []
    const taggerEvents: string[] = []
    const wrapper = mount(DatasetPage, {
      props: { tab: "editor" as const },
      global: {
        plugins: [i18n],
        stubs: {
          RouterLink: routerLinkStub,
          DatasetEditorPage: lifecycleStub("DatasetEditorPage", editorEvents),
          TaggerPage: lifecycleStub("TaggerPage", taggerEvents),
        },
      },
    })
    await flushPromises()

    await wrapper.setProps({ tab: "tagger" })
    await wrapper.setProps({ tab: "editor" })

    expect(editorEvents).toEqual(["mount", "activate", "deactivate", "activate"])
    expect(taggerEvents).toEqual(["mount", "activate", "deactivate"])
    expect(editorEvents).not.toContain("unmount")
    expect(taggerEvents).not.toContain("unmount")
    wrapper.unmount()
  })
})

describe("DatasetEditorPage route session", () => {
  it("restores the selected dataset and an unsaved caption after remount", async () => {
    const session = useDatasetEditorSession()
    session.lastPath.value = "D:/datasets/sample"
    session.lastRoot.value = ""
    session.selected.value = ""
    session.drafts.value = {}
    session.resetInMemoryDataset()
    vi.mocked(datasetApi.scan).mockResolvedValue({
      root: "D:/datasets/sample",
      total: 1,
      items: [{
        name: "sample.png",
        relative_path: "sample.png",
        category: "",
        caption: "blue_eyes",
        caption_exists: true,
        tags: ["blue_eyes"],
        image_url: "/image",
        thumb_url: "/thumb",
      }],
      tags: [{ tag: "blue_eyes", count: 1 }],
      categories: [],
    })

    const harness = defineComponent({
      components: { Page: DatasetEditorPage },
      template: "<KeepAlive><Page /></KeepAlive>",
    })
    const wrapper = mount(harness, {
      global: {
        plugins: [i18n],
        stubs: { PathPickerDialog: true, TagFilterPanel: true, "el-dialog": true },
      },
    })
    await flushPromises()

    // Default state stays a pure gallery; the editor opens once an image is picked.
    expect(wrapper.find(".caption-panel .primary-action").exists()).toBe(false)
    await wrapper.get(".image-grid button").trigger("click")
    await nextTick()
    expect((wrapper.find("textarea").element as HTMLTextAreaElement).value).toBe("blue_eyes")
    wrapper.unmount()

    // Simulate a browser refresh: the in-memory scan result is gone, but the
    // persisted dataset root and selected image remain available for restore.
    session.resetInMemoryDataset()
    session.selected.value = "sample.png"
    const refreshed = mount(harness, {
      global: {
        plugins: [i18n],
        stubs: { PathPickerDialog: true, TagFilterPanel: true, "el-dialog": true },
      },
    })
    await flushPromises()
    expect((refreshed.find("textarea").element as HTMLTextAreaElement).value).toBe("blue_eyes")

    const editor = refreshed.find("textarea")
    expect(editor.exists()).toBe(true)
    await editor.setValue("blue_eyes, long_hair")
    await nextTick()

    refreshed.unmount()

    const restored = mount(harness, {
      global: {
        plugins: [i18n],
        stubs: { PathPickerDialog: true, TagFilterPanel: true, "el-dialog": true },
      },
    })
    await flushPromises()

    expect((restored.find("textarea").element as HTMLTextAreaElement).value).toBe("blue_eyes, long_hair")
    expect(session.lastRoot.value).toBe("D:/datasets/sample")
    expect(session.getDraft("D:/datasets/sample", "sample.png")).toBe("blue_eyes, long_hair")
    restored.unmount()
  })
})

describe("TaggerPage polling under keep-alive", () => {
  const harness = (page: object) =>
    defineComponent({
      components: { Page: page },
      setup() {
        const show = ref(true)
        return { show }
      },
      template: "<KeepAlive><Page v-if=\"show\" /></KeepAlive>",
    })

  it("stops polling when hidden and resumes with exactly one interval", async () => {
    const live = new Set<number>()
    vi.spyOn(window, "setInterval").mockImplementation(((handler: TimerHandler, timeout?: number) => {
      const id = live.size + 1
      live.add(id)
      expect(timeout).toBe(1200)
      void handler
      return id
    }) as typeof window.setInterval)
    vi.spyOn(window, "clearInterval").mockImplementation(((id?: number) => {
      if (id !== undefined) live.delete(id)
    }) as typeof window.clearInterval)

    const wrapper = mount(harness(TaggerPage), {
      global: { plugins: [i18n], stubs: { PathPickerDialog: true } },
    })
    await flushPromises()
    expect(live.size).toBe(1)

    wrapper.vm.show = false
    await nextTick()
    expect(live.size).toBe(0)

    wrapper.vm.show = true
    await nextTick()
    await flushPromises()
    expect(live.size).toBe(1)

    wrapper.unmount()
    expect(live.size).toBe(0)
  })
})

describe("DatasetEditorPage keydown wiring under keep-alive", () => {
  it("removes the global keydown listener while hidden", async () => {
    const added = new Set<EventListener>()
    vi.spyOn(window, "addEventListener").mockImplementation(((type: string, listener: EventListenerOrEventListenerObject) => {
      if (type === "keydown") added.add(listener as EventListener)
    }) as typeof window.addEventListener)
    vi.spyOn(window, "removeEventListener").mockImplementation(((type: string, listener: EventListenerOrEventListenerObject) => {
      if (type === "keydown") added.delete(listener as EventListener)
    }) as typeof window.removeEventListener)

    const harness = defineComponent({
      components: { DatasetEditorPage },
      setup() {
        const show = ref(true)
        return { show }
      },
      template: "<KeepAlive><DatasetEditorPage v-if=\"show\" /></KeepAlive>",
    })
    const wrapper = mount(harness, {
      global: {
        plugins: [i18n],
        stubs: { PathPickerDialog: true, TagFilterPanel: true, "el-dialog": true },
      },
    })
    await flushPromises()
    expect(added.size).toBe(1)

    wrapper.vm.show = false
    await nextTick()
    expect(added.size).toBe(0)

    wrapper.vm.show = true
    await nextTick()
    await flushPromises()
    expect(added.size).toBe(1)

    wrapper.unmount()
    expect(added.size).toBe(0)
  })
})
