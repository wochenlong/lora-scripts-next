import { describe, expect, it } from "vitest"
import cases from "../../../tests/fixtures/caption_language_cases.json"
import { isChineseCaption } from "./captionLanguage"

describe("caption language shared frontend/backend cases", () => {
  it.each(cases)("$id", ({ text, chinese }) => {
    expect(isChineseCaption(text)).toBe(chinese)
  })
})
