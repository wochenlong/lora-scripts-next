import { describe, expect, it } from "vitest"
import { addTagToCaption, removeTagFromCaption, splitCaptionTags } from "./caption"

describe("caption tag helpers", () => {
  it("splits captions into trimmed tags", () => {
    expect(splitCaptionTags("solo, 1girl ,,cat ears")).toEqual(["solo", "1girl", "cat ears"])
    expect(splitCaptionTags("")).toEqual([])
  })

  it("appends new tags and ignores duplicates or blanks", () => {
    expect(addTagToCaption("solo, 1girl", "cat ears")).toBe("solo, 1girl, cat ears")
    expect(addTagToCaption("solo, 1girl", "solo")).toBe("solo, 1girl")
    expect(addTagToCaption("solo", "   ")).toBe("solo")
    expect(addTagToCaption("", "solo")).toBe("solo")
  })

  it("removes tags without disturbing order", () => {
    expect(removeTagFromCaption("solo, 1girl, cat ears", "1girl")).toBe("solo, cat ears")
    expect(removeTagFromCaption("solo", "solo")).toBe("")
    expect(removeTagFromCaption("solo", "missing")).toBe("solo")
  })
})
