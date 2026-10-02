import { beforeEach, describe, expect, it, vi } from "vitest"
import { useTagTranslations } from "./useTagTranslations"
import { datasetApi } from "../api/dataset"

vi.mock("../api/dataset", () => ({
  datasetApi: { tagTranslations: vi.fn() },
}))

describe("useTagTranslations", () => {
  beforeEach(() => {
    vi.mocked(datasetApi.tagTranslations).mockReset()
    useTagTranslations().clearCache()
  })

  it("resolves missing tags and reuses the in-memory result", async () => {
    vi.mocked(datasetApi.tagTranslations).mockResolvedValue({
      items: [{ tag: "blue_eyes", translation: "蓝瞳", source: "danbooru", status: "hit" }],
      provider: "danbooru",
      locale: "zh-CN",
    })
    const state = useTagTranslations()

    await state.resolve(["blue_eyes", "blue_eyes"], "danbooru")
    await state.resolve(["blue_eyes"], "danbooru")

    expect(state.translationFor("blue_eyes")).toBe("蓝瞳")
    expect(state.progress.value).toEqual({ completed: 1, total: 1 })
    expect(datasetApi.tagTranslations).toHaveBeenCalledTimes(1)
    expect(datasetApi.tagTranslations).toHaveBeenCalledWith(["blue_eyes"], "danbooru", "zh-CN")
  })

  it("clears the result and error state", async () => {
    vi.mocked(datasetApi.tagTranslations).mockResolvedValue({
      items: [{ tag: "unknown", translation: "未知", source: "mymemory", status: "hit" }],
      provider: "mymemory",
      locale: "zh-CN",
    })
    const state = useTagTranslations()
    await state.resolve(["unknown"], "danbooru")
    expect(state.translationFor("unknown")).toBe("未知")
    state.clearCache()
    expect(state.translationFor("unknown")).toBe("")
    expect(state.error.value).toBe("")
  })

  it("only requests a newly added tag when the dataset grows", async () => {
    vi.mocked(datasetApi.tagTranslations)
      .mockResolvedValueOnce({
        items: [{ tag: "blue_eyes", translation: "蓝瞳", source: "danbooru", status: "hit" }],
        provider: "danbooru",
        locale: "zh-CN",
      })
      .mockResolvedValueOnce({
        items: [{ tag: "new_review_tag", translation: "新的审查标签", source: "llm", status: "hit" }],
        provider: "danbooru",
        locale: "zh-CN",
      })
    const state = useTagTranslations()

    await state.resolve(["blue_eyes"], "danbooru")
    await state.resolve(["blue_eyes", "new_review_tag"], "danbooru")

    expect(datasetApi.tagTranslations).toHaveBeenNthCalledWith(2, ["new_review_tag"], "danbooru", "zh-CN")
    expect(state.translationFor("new_review_tag", "danbooru")).toBe("新的审查标签")
  })
})
