import { describe, expect, it } from "vitest"
import { addTagToCaption, captionEditingFormat, captionEditingTags, detectCaptionFormat, moveCaptionTag, removeTagFromCaption, splitCaptionTags } from "./caption"

describe("caption tag helpers", () => {
  it("honors generated natural and uncertain provenance even for short text", () => {
    for (const format of ["natural", "mixed", "unknown"] as const) {
      expect(captionEditingFormat("  猫\r\n", { caption_exists: true, caption_format: format })).toBe(format)
      expect(captionEditingFormat("", { caption_exists: true, caption_format: format })).toBe(format)
    }
    expect(captionEditingFormat("cat", { caption_exists: false, caption_format: "unknown" })).toBe("tag")
    expect(captionEditingFormat("A cat sits on the window sill.", { caption_exists: true, caption_format: "tag" })).toBe("natural")
  })
  it("uses actual mixed training tags and never projects short natural drafts into filters", () => {
    expect(captionEditingTags("猫\n\ncat, window", { caption_exists: true, caption_format: "mixed", tags: ["cat", "window"] })).toEqual(["cat", "window"])
    expect(captionEditingTags("猫", { caption_exists: true, caption_format: "natural", tags: [] })).toEqual([])
    expect(captionEditingTags("猫", { caption_exists: true, caption_format: "unknown", tags: [] })).toEqual([])
  })
  it("preserves mixed and natural text through every tag mutation", () => {
    for (const caption of ["solo, 1girl\n\n她站在窗边。", "她站在窗边。\n\nsolo, 1girl", "A cat is sitting next to the window"]) {
      expect(addTagToCaption(caption, "smile")).toBe(caption)
      expect(removeTagFromCaption(caption, "solo")).toBe(caption)
      expect(moveCaptionTag(caption, 0, 1)).toBe(caption)
    }
    expect(detectCaptionFormat("她站在窗边。\n\nsolo, 1girl")).toBe("mixed")
    expect(splitCaptionTags("她站在窗边。\n\nsolo, 1girl")).toEqual(["solo", "1girl"])
  })
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

  it("reorders tags by index for drag-and-drop", () => {
    expect(moveCaptionTag("a, b, c", 0, 2)).toBe("b, c, a")
    expect(moveCaptionTag("a, b, c", 2, 0)).toBe("c, a, b")
    expect(moveCaptionTag("a, b, c", 1, 1)).toBe("a, b, c")
    expect(moveCaptionTag("a, b", 5, 0)).toBe("a, b")
  })
})
