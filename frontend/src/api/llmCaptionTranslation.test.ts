import { beforeEach, describe, expect, it, vi } from "vitest"
import { apiData } from "./client"
import { llmApi } from "./llm"
import { useCaptionTranslation } from "../composables/useCaptionTranslation"

vi.mock("./client", () => ({ apiData: vi.fn() }))

const result = { translation: "一只猫。", skipped: false, cached: false }

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(apiData).mockResolvedValue(result)
})

describe("caption translation shared fallback request contract", () => {
  it.each([
    { policy: undefined, payload: { text: "A cat." } },
    { policy: false, payload: { text: "A cat.", allow_local_fallback: false } },
    { policy: true, payload: { text: "A cat.", allow_local_fallback: true } },
  ])("preserves the optional policy $policy and abort signal", async ({ policy, payload }) => {
    const controller = new AbortController()
    await expect(llmApi.translateCaption("A cat.", policy, controller.signal)).resolves.toEqual(result)
    const [path, options] = vi.mocked(apiData).mock.calls[0]
    expect(path).toBe("/api/llm/caption-translation")
    expect(options?.method).toBe("POST")
    expect(JSON.parse(options?.body as string)).toEqual(payload)
    expect(options?.signal).toBe(controller.signal)
  })

  it("lets the editor composable inherit shared policy through the actual API client", async () => {
    const translation = useCaptionTranslation()
    await translation.translate("A cat.")
    expect(apiData).toHaveBeenCalledOnce()
    const options = vi.mocked(apiData).mock.calls[0][1]
    expect(JSON.parse(options?.body as string)).toEqual({ text: "A cat." })
    expect(options?.signal).toBeInstanceOf(AbortSignal)
    expect(translation.text.value).toBe(result.translation)
    expect(translation.error.value).toBe("")
  })
})
