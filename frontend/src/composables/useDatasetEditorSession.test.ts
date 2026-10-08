// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest"
import { useDatasetEditorSession } from "./useDatasetEditorSession"

describe("useDatasetEditorSession", () => {
  beforeEach(() => {
    const state = useDatasetEditorSession()
    state.lastPath.value = ""
    state.lastRoot.value = ""
    state.selected.value = ""
    state.drafts.value = {}
    state.showTranslations.value = false
    state.translationProvider.value = "danbooru"
    state.category.value = ""
    state.query.value = ""
    state.page.value = 1
    state.rightPanelMode.value = "caption"
    state.resetInMemoryDataset()
    localStorage.clear()
  })

  it("keeps the last dataset and draft isolated by dataset root", () => {
    const state = useDatasetEditorSession()

    state.rememberDataset("D:/datasets/one", "D:/datasets/one")
    state.rememberSelection("first.png")
    state.setDraft("D:/datasets/one", "first.png", "blue_eyes, long_hair")
    state.setDraft("D:/datasets/two", "first.png", "red_eyes")

    expect(state.lastPath.value).toBe("D:/datasets/one")
    expect(state.selected.value).toBe("first.png")
    expect(state.getDraft("D:/datasets/one", "first.png")).toBe("blue_eyes, long_hair")
    expect(state.getDraft("D:/datasets/two", "first.png")).toBe("red_eyes")

    const persisted = JSON.parse(localStorage.getItem("dataset-editor-session-v1") || "{}")
    expect(persisted.lastRoot).toBe("D:/datasets/one")
    expect(persisted.drafts["D:/datasets/one\u0000first.png"]).toBe("blue_eyes, long_hair")
  })

  it("removes only the saved draft for an explicitly saved image", () => {
    const state = useDatasetEditorSession()
    state.setDraft("D:/datasets/one", "first.png", "blue_eyes")
    state.setDraft("D:/datasets/one", "second.png", "long_hair")

    state.clearDraft("D:/datasets/one", "first.png")

    expect(state.getDraft("D:/datasets/one", "first.png")).toBeUndefined()
    expect(state.getDraft("D:/datasets/one", "second.png")).toBe("long_hair")
  })
})

