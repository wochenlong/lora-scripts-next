// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { useTagTranslations } from "./useTagTranslations"
import { datasetApi, type TagTranslationResponse } from "../api/dataset"

vi.mock("../api/dataset", () => ({
  datasetApi: { tagTranslations: vi.fn() },
}))

function llmResponse(translation: string, tag = "custom_tag"): TagTranslationResponse {
  return { items: [{ tag, translation, source: "llm", status: "hit" }], provider: "llm", locale: "zh-CN" }
}

function deferredResponse() {
  let resolve!: (value: TagTranslationResponse) => void
  let reject!: (reason: Error) => void
  const promise = new Promise<TagTranslationResponse>((accept, fail) => { resolve = accept; reject = fail })
  return { promise, resolve, reject }
}

describe("useTagTranslations", () => {
  beforeEach(() => {
    vi.mocked(datasetApi.tagTranslations).mockReset()
    useTagTranslations().clearCache()
    useTagTranslations().configureCache(true, "")
  })

  afterEach(() => { vi.restoreAllMocks() })

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
        items: [{ tag: "new_review_tag", translation: "新的审查标签", source: "danbooru", status: "hit" }],
        provider: "danbooru",
        locale: "zh-CN",
      })
    const state = useTagTranslations()

    await state.resolve(["blue_eyes"], "danbooru")
    await state.resolve(["blue_eyes", "new_review_tag"], "danbooru")

    expect(datasetApi.tagTranslations).toHaveBeenNthCalledWith(2, ["new_review_tag"], "danbooru", "zh-CN")
    expect(state.translationFor("new_review_tag", "danbooru")).toBe("新的审查标签")
  })

  it("clears external results without dropping dictionary meanings", async () => {
    vi.mocked(datasetApi.tagTranslations)
      .mockResolvedValueOnce({
        items: [{ tag: "blue_eyes", translation: "蓝瞳", source: "danbooru", status: "hit" }],
        provider: "danbooru",
        locale: "zh-CN",
      })
      .mockResolvedValueOnce({
        items: [{ tag: "custom_tag", translation: "自定义标签", source: "llm", status: "hit" }],
        provider: "llm",
        locale: "zh-CN",
      })
    const state = useTagTranslations()

    await state.resolve(["blue_eyes"], "danbooru")
    await state.resolve(["custom_tag"], "llm")
    state.clearExternalCache()

    expect(state.translationFor("blue_eyes", "danbooru")).toBe("蓝瞳")
    expect(state.translationFor("custom_tag", "llm")).toBe("")
  })

  it("reuses and persists an external result only within the same shared revision", async () => {
    const state = useTagTranslations()
    state.configureCache(true, "profile-a")
    const persist = vi.spyOn(Storage.prototype, "setItem")
    vi.mocked(datasetApi.tagTranslations).mockResolvedValue(llmResponse("模型 A 译文"))

    await state.resolve(["custom_tag"], "llm")
    await state.resolve(["custom_tag"], "llm")

    expect(datasetApi.tagTranslations).toHaveBeenCalledTimes(1)
    expect(state.translationFor("custom_tag", "llm")).toBe("模型 A 译文")
    expect(persist).toHaveBeenCalledTimes(1)
    const persisted = JSON.parse(localStorage.getItem("dataset-tag-translation-cache-v2") || "{}")
    expect(persisted["zh-CN\u0000llm\u0000profile-a\u0000custom_tag"].translation).toBe("模型 A 译文")
  })

  it("displays uncached responses without reading or adding browser cache entries", async () => {
    const state = useTagTranslations()
    state.configureCache(true, "profile-a")
    vi.mocked(datasetApi.tagTranslations).mockResolvedValueOnce(llmResponse("旧缓存译文"))
    await state.resolve(["custom_tag"], "llm")
    state.configureCache(false, "profile-a")
    const storedAfterDisable = localStorage.getItem("dataset-tag-translation-cache-v2")
    const read = vi.spyOn(Storage.prototype, "getItem")
    const persist = vi.spyOn(Storage.prototype, "setItem")
    vi.mocked(datasetApi.tagTranslations)
      .mockResolvedValueOnce(llmResponse("本次译文"))
      .mockResolvedValueOnce(llmResponse("第二次译文"))

    await state.resolve(["custom_tag"], "llm")
    expect(state.translationFor("custom_tag", "llm")).toBe("本次译文")
    await state.resolve(["custom_tag"], "llm")
    expect(state.translationFor("custom_tag", "llm")).toBe("第二次译文")

    expect(datasetApi.tagTranslations).toHaveBeenCalledTimes(3)
    expect(read).not.toHaveBeenCalled()
    expect(persist).not.toHaveBeenCalled()
    read.mockRestore()
    expect(localStorage.getItem("dataset-tag-translation-cache-v2")).toBe(storedAfterDisable)
  })

  it("discards a transient response when caching is enabled again", async () => {
    const state = useTagTranslations()
    state.configureCache(false, "profile-a")
    vi.mocked(datasetApi.tagTranslations)
      .mockResolvedValueOnce(llmResponse("不缓存的译文"))
      .mockResolvedValueOnce(llmResponse("重新请求的译文"))
    await state.resolve(["custom_tag"], "llm")
    state.configureCache(true, "profile-a")
    expect(state.translationFor("custom_tag", "llm")).toBe("")

    await state.resolve(["custom_tag"], "llm")
    expect(datasetApi.tagTranslations).toHaveBeenCalledTimes(2)
    expect(state.translationFor("custom_tag", "llm")).toBe("重新请求的译文")
  })

  it("invalidates external results when a shared revision changes, while retaining dictionary meanings", async () => {
    const state = useTagTranslations()
    state.configureCache(true, "profile-a")
    vi.mocked(datasetApi.tagTranslations)
      .mockResolvedValueOnce({ items: [{ tag: "blue_eyes", translation: "蓝瞳", source: "danbooru", status: "hit" }], provider: "danbooru", locale: "zh-CN" })
      .mockResolvedValueOnce(llmResponse("模型 A 译文"))
      .mockResolvedValueOnce(llmResponse("模型 B 译文"))
    await state.resolve(["blue_eyes"], "danbooru")
    await state.resolve(["custom_tag"], "llm")
    state.configureCache(true, "profile-b")

    expect(state.translationFor("custom_tag", "llm")).toBe("")
    expect(state.translationFor("blue_eyes", "danbooru")).toBe("蓝瞳")
    await state.resolve(["blue_eyes"], "danbooru")
    await state.resolve(["custom_tag"], "llm")

    expect(datasetApi.tagTranslations).toHaveBeenCalledTimes(3)
    expect(state.translationFor("custom_tag", "llm")).toBe("模型 B 译文")
    expect(localStorage.getItem("dataset-tag-translation-cache-v2")).not.toContain("模型 A 译文")
  })

  it("keeps dictionary caching active when shared external caching is disabled", async () => {
    const state = useTagTranslations()
    state.configureCache(false, "profile-a")
    vi.mocked(datasetApi.tagTranslations).mockResolvedValue({
      items: [{ tag: "blue_eyes", translation: "蓝瞳", source: "danbooru", status: "hit" }], provider: "danbooru", locale: "zh-CN",
    })

    await state.resolve(["blue_eyes"], "danbooru")
    state.configureCache(false, "profile-b")
    await state.resolve(["blue_eyes"], "danbooru")

    expect(datasetApi.tagTranslations).toHaveBeenCalledTimes(1)
    expect(state.translationFor("blue_eyes", "danbooru")).toBe("蓝瞳")
  })

  it("does not invalidate an external result for an unchanged cache policy", async () => {
    const state = useTagTranslations()
    state.configureCache(true, "profile-a")
    vi.mocked(datasetApi.tagTranslations).mockResolvedValue(llmResponse("有效译文"))
    await state.resolve(["custom_tag"], "llm")
    state.configureCache(true, "profile-a")
    await state.resolve(["custom_tag"], "llm")
    expect(datasetApi.tagTranslations).toHaveBeenCalledTimes(1)
  })

  it("rejects a late old-revision response without touching the new result or persistence", async () => {
    const state = useTagTranslations()
    state.configureCache(true, "profile-a")
    const stale = deferredResponse()
    vi.mocked(datasetApi.tagTranslations)
      .mockReturnValueOnce(stale.promise)
      .mockResolvedValueOnce(llmResponse("模型 B 译文"))
    const oldRequest = state.resolve(["custom_tag"], "llm")
    state.configureCache(true, "profile-b")
    await state.resolve(["custom_tag"], "llm")
    const persisted = localStorage.getItem("dataset-tag-translation-cache-v2")

    stale.resolve(llmResponse("迟到的模型 A 译文"))
    await oldRequest

    expect(state.translationFor("custom_tag", "llm")).toBe("模型 B 译文")
    expect(state.loading.value).toBe(false)
    expect(state.progress.value).toEqual({ completed: 1, total: 1 })
    expect(localStorage.getItem("dataset-tag-translation-cache-v2")).toBe(persisted)
    expect(Object.values(state.translations.value).some(item => item.translation === "迟到的模型 A 译文")).toBe(false)
  })

  it("rejects a response started before external caching was disabled", async () => {
    const state = useTagTranslations()
    state.configureCache(true, "profile-a")
    const stale = deferredResponse()
    vi.mocked(datasetApi.tagTranslations)
      .mockReturnValueOnce(stale.promise)
      .mockResolvedValueOnce(llmResponse("关闭后本次译文"))
    const oldRequest = state.resolve(["custom_tag"], "llm")
    state.configureCache(false, "profile-a")
    const persist = vi.spyOn(Storage.prototype, "setItem")
    await state.resolve(["custom_tag"], "llm")

    stale.resolve(llmResponse("关闭前迟到的译文"))
    await oldRequest

    expect(state.translationFor("custom_tag", "llm")).toBe("关闭后本次译文")
    expect(persist).not.toHaveBeenCalled()
  })

  it("does not reuse an external translation for a dictionary-only request", async () => {
    const state = useTagTranslations()
    vi.mocked(datasetApi.tagTranslations)
      .mockResolvedValueOnce(llmResponse("远程译文"))
      .mockResolvedValueOnce({ items: [{ tag: "custom_tag", translation: null, source: null, status: "missing" }], provider: "llm", locale: "zh-CN" })
    await state.resolve(["custom_tag"], "llm")

    await state.resolve(["custom_tag"], "llm", "zh-CN", true)

    expect(datasetApi.tagTranslations).toHaveBeenCalledTimes(2)
    expect(datasetApi.tagTranslations).toHaveBeenLastCalledWith(["custom_tag"], "llm", "zh-CN", { localOnly: true })
    expect(state.translationFor("custom_tag", "llm")).toBe("")
    expect(state.unresolved.value).toBe(1)
  })

  it("a cache-only request supersedes an earlier pending response", async () => {
    const state = useTagTranslations()
    vi.mocked(datasetApi.tagTranslations).mockResolvedValueOnce(llmResponse("已有译文"))
    await state.resolve(["custom_tag"], "llm")
    const stale = deferredResponse()
    vi.mocked(datasetApi.tagTranslations).mockReturnValueOnce(stale.promise)
    const oldRequest = state.resolve(["pending_tag"], "llm")
    await state.resolve(["custom_tag"], "llm")

    stale.resolve(llmResponse("被取代的译文", "pending_tag"))
    await oldRequest

    expect(state.translationFor("custom_tag", "llm")).toBe("已有译文")
    expect(state.translationFor("pending_tag", "llm")).toBe("")
    expect(state.progress.value).toEqual({ completed: 1, total: 1 })
    expect(state.loading.value).toBe(false)
  })

  it("an empty request supersedes an earlier pending error", async () => {
    const state = useTagTranslations()
    const stale = deferredResponse()
    vi.mocked(datasetApi.tagTranslations).mockReturnValueOnce(stale.promise)
    const oldRequest = state.resolve(["pending_tag"], "llm")
    await state.resolve([], "danbooru")
    stale.reject(new Error("superseded failure"))
    await oldRequest

    expect(state.error.value).toBe("")
    expect(state.progress.value).toEqual({ completed: 0, total: 0 })
    expect(state.loading.value).toBe(false)
  })

  it("clearing the cache blocks an in-flight response from repopulating it", async () => {
    const state = useTagTranslations()
    const stale = deferredResponse()
    vi.mocked(datasetApi.tagTranslations).mockReturnValueOnce(stale.promise)
    const request = state.resolve(["custom_tag"], "llm")
    state.clearCache()
    stale.resolve(llmResponse("清空后迟到的译文"))
    await request

    expect(state.translationFor("custom_tag", "llm")).toBe("")
    expect(localStorage.getItem("dataset-tag-translation-cache-v2")).toBeNull()
    expect(state.loading.value).toBe(false)
  })
})
