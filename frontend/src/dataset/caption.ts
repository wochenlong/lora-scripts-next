import type { CaptionFormat } from "../api/dataset"

export function detectCaptionFormat(caption: string): CaptionFormat {
  const text = caption.trim()
  if (!text) return "unknown"
  const blocks = text.split(/\n\s*\n/).map((block) => block.trim()).filter(Boolean)
  const looksLikeTags = (value: string) => value.split(/[,，；;\n]/).map((tag) => tag.trim()).filter(Boolean).every((tag) => tag.length <= 120 && tag.split(/\s+/).length <= 4 && !/[。！？.!?]/.test(tag) && (tag.match(/[\u3400-\u9fff]/g)?.length ?? 0) <= 12)
  if (blocks.length > 1 && blocks.some(looksLikeTags)) return "mixed"
  return looksLikeTags(text) ? "tag" : "natural"
}

export function splitCaptionTags(caption: string, format: CaptionFormat = detectCaptionFormat(caption)): string[] {
  if (format === "natural" || format === "unknown") return []
  const source = format === "mixed"
    ? caption.split(/\n\s*\n/).find((block) => detectCaptionFormat(block) === "tag") ?? ""
    : caption
  return source.split(",").map((tag) => tag.trim()).filter(Boolean)
}

export function addTagToCaption(caption: string, tag: string): string {
  if (caption.trim() && detectCaptionFormat(caption) !== "tag") return caption
  const clean = tag.trim()
  const tags = splitCaptionTags(caption)
  if (!clean || tags.includes(clean)) return tags.join(", ")
  return [...tags, clean].join(", ")
}

export function removeTagFromCaption(caption: string, tag: string): string {
  if (caption.trim() && detectCaptionFormat(caption) !== "tag") return caption
  const clean = tag.trim()
  return splitCaptionTags(caption).filter((item) => item !== clean).join(", ")
}

/** Move a tag from one index to another; used by chip drag-and-drop reorder. */
export function moveCaptionTag(caption: string, fromIndex: number, toIndex: number): string {
  if (caption.trim() && detectCaptionFormat(caption) !== "tag") return caption
  const tags = splitCaptionTags(caption)
  if (
    fromIndex < 0 || toIndex < 0
    || fromIndex >= tags.length || toIndex >= tags.length
    || fromIndex === toIndex
  ) {
    return tags.join(", ")
  }
  const [item] = tags.splice(fromIndex, 1)
  tags.splice(toIndex, 0, item)
  return tags.join(", ")
}
