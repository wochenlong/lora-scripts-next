import { describe, it, expect, vi, afterEach } from "vitest"
import { llmApi } from "../api/llm"
import { useCaptionTranslation } from "./useCaptionTranslation"

afterEach(() => vi.restoreAllMocks())

describe("natural caption translation", () => {
  it("shows Chinese directly without a request, including Latin names", async () => {
    const request = vi.spyOn(llmApi, "translateCaption")
    const state = useCaptionTranslation()
    await state.translate("一只猫坐在 Qwen 标牌前。")
    expect(state.text.value).toBe("一只猫坐在 Qwen 标牌前。")
    expect(state.alreadyChinese.value).toBe(true)
    expect(request).not.toHaveBeenCalled()
  })
  it("translates the whole sentence and ignores an obsolete result", async () => {
    let oldResolve!: (value: { translation: string; skipped: boolean; cached: boolean }) => void
    const request = vi.spyOn(llmApi, "translateCaption").mockImplementationOnce(() => new Promise(resolve => { oldResolve = resolve }))
      .mockResolvedValueOnce({ translation: "一杯咖啡。", skipped: false, cached: false })
    const state = useCaptionTranslation()
    const pending = state.translate("A cat, by a window.")
    const signal = request.mock.calls[0][2]
    await state.translate("A cup of coffee.", true)
    oldResolve({ translation: "旧猫译文", skipped: false, cached: false })
    await pending
    expect(signal?.aborted).toBe(true)
    expect(state.text.value).toBe("一杯咖啡。")
    expect(request.mock.calls[0][0]).toBe("A cat, by a window.")
    expect(request.mock.calls[1][1]).toBe(true)
  })
  it("does not treat an English sentence with a Chinese label as Chinese", async () => {
    const request = vi.spyOn(llmApi, "translateCaption").mockResolvedValue({ translation: "标着猫字的箱子旁的一只猫。", skipped: false, cached: true })
    await useCaptionTranslation().translate("A cat next to a box labelled 猫.")
    expect(request).toHaveBeenCalledOnce()
  })
})
