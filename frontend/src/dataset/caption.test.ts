import { describe, expect, it } from "vitest"
import { addTagToCaption, captionEditingFormat, captionEditingTags, detectCaptionFormat, moveCaptionTag, removeTagFromCaption, splitCaptionTags } from "./caption"

describe("caption tag helpers", () => {
  it("honors explicit provenance independently of caption wording", () => {
    for (const format of ["tag", "natural", "mixed", "unknown"] as const) {
      expect(captionEditingFormat("  猫\r\n", { caption_exists: true, caption_format: format })).toBe(format)
      expect(captionEditingFormat("", { caption_exists: true, caption_format: format })).toBe(format)
      expect(captionEditingFormat("A cat sits on the window sill.", { caption_exists: true, caption_format: format })).toBe(format)
    }
  })

  it("keeps unconfirmed short prose and apparent tags unknown", () => {
    for (const caption of ["cat", "猫", "red cat", "solo, 1girl", ""]) {
      expect(captionEditingFormat(caption)).toBe("unknown")
      expect(captionEditingFormat(caption, { caption_exists: true, caption_format: "unknown" })).toBe("unknown")
      expect(captionEditingFormat(caption, { caption_exists: false, caption_format: "unknown" })).toBe("unknown")
    }
  })

  it("uses only explicit mixed training tags and protects natural drafts", () => {
    expect(captionEditingTags("猫\n\ncat, window", { caption_exists: true, caption_format: "mixed", tags: ["cat", "window"] })).toEqual(["cat", "window"])
    expect(captionEditingTags("猫\n\ncat, window", { caption_exists: true, caption_format: "mixed", tags: [] })).toEqual([])
    expect(splitCaptionTags("猫\n\ncat, window", "mixed")).toEqual([])
    expect(captionEditingTags("猫", { caption_exists: true, caption_format: "natural", tags: [] })).toEqual([])
    expect(captionEditingTags("猫", { caption_exists: true, caption_format: "unknown", tags: [] })).toEqual([])
    expect(captionEditingTags("A cat sits on the window sill.", { caption_exists: true, caption_format: "tag", tags: [] })).toEqual(["A cat sits on the window sill"])
  })

  it("preserves unconfirmed text through every tag mutation", () => {
    for (const caption of ["猫", "cat", "red cat", "solo, 1girl", "solo, 1girl\n\n她站在窗边。", "她站在窗边。\n\nsolo, 1girl", "A cat is sitting next to the window"]) {
      expect(addTagToCaption(caption, "smile")).toBe(caption)
      expect(removeTagFromCaption(caption, "solo")).toBe(caption)
      expect(moveCaptionTag(caption, 0, 1)).toBe(caption)
      expect(splitCaptionTags(caption)).toEqual([])
    }
  })

  it("preserves explicitly natural or mixed text even when empty or tag-like", () => {
    for (const format of ["natural", "mixed", "unknown"] as const) {
      const caption = "solo, 1girl"
      expect(addTagToCaption(caption, "smile", format)).toBe(caption)
      expect(removeTagFromCaption(caption, "solo", format)).toBe(caption)
      expect(moveCaptionTag(caption, 0, 1, format)).toBe(caption)
    }
    for (const format of ["natural", "mixed"] as const) {
      expect(addTagToCaption("", "solo", format)).toBe("")
    }
    // The legacy suggestion helper does not grant permission to edit tags.
    expect(detectCaptionFormat("她站在窗边。\n\nsolo, 1girl")).toBe("mixed")
  })

  it("splits confirmed captions into trimmed tags", () => {
    expect(splitCaptionTags("solo, 1girl ,,cat ears", "tag")).toEqual(["solo", "1girl", "cat ears"])
    expect(splitCaptionTags("", "tag")).toEqual([])
  })

  it("splits confirmed Chinese commas and sentence-ending periods", () => {
    expect(splitCaptionTags("solo，1girl", "tag")).toEqual(["solo", "1girl"])
    expect(splitCaptionTags("cute animal. display piece.", "tag")).toEqual(["cute animal", "display piece"])
    expect(splitCaptionTags("cute animal. display piece.")).toEqual([])
    // Periods inside a token stay part of the tag.
    expect(splitCaptionTags(".hack, 3.5", "tag")).toEqual([".hack", "3.5"])
  })

  it("appends confirmed tags and ignores duplicates or blanks", () => {
    expect(addTagToCaption("solo, 1girl", "cat ears", "tag")).toBe("solo, 1girl, cat ears")
    expect(addTagToCaption("solo, 1girl", "solo", "tag")).toBe("solo, 1girl")
    expect(addTagToCaption("solo", "   ", "tag")).toBe("solo")
    expect(addTagToCaption("", "solo")).toBe("solo")
    expect(addTagToCaption(" \r\n ", "solo")).toBe("solo")
  })

  it("removes confirmed tags without disturbing order", () => {
    expect(removeTagFromCaption("solo, 1girl, cat ears", "1girl", "tag")).toBe("solo, cat ears")
    expect(removeTagFromCaption("solo", "solo", "tag")).toBe("")
    expect(removeTagFromCaption("solo", "missing", "tag")).toBe("solo")
  })

  it("reorders confirmed tags by index for drag-and-drop", () => {
    expect(moveCaptionTag("a, b, c", 0, 2, "tag")).toBe("b, c, a")
    expect(moveCaptionTag("a, b, c", 2, 0, "tag")).toBe("c, a, b")
    expect(moveCaptionTag("a, b, c", 1, 1, "tag")).toBe("a, b, c")
    expect(moveCaptionTag("a, b", 5, 0, "tag")).toBe("a, b")
  })
})
