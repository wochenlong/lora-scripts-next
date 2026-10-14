import type { CaptionFormat, DatasetItem } from "../api/dataset"

export function captionEditingFormat(_caption: string, source?: Pick<DatasetItem, "caption_exists" | "caption_format">): CaptionFormat {
  if (source?.caption_exists && source.caption_format) return source.caption_format
  // Short prose can be indistinguishable from tags. Only explicit provenance
  // unlocks tag editing; text without provenance must remain raw text.
  return "unknown"
}

export function captionEditingTags(caption: string, source: Pick<DatasetItem, "caption_exists" | "caption_format" | "tags">): string[] {
  const format = captionEditingFormat(caption, source)
  if (format === "tag") return splitCaptionTags(caption, "tag")
  return format === "mixed" ? [...source.tags] : []
}

export function detectCaptionFormat(caption: string): CaptionFormat {
  const text = caption.trim()
  if (!text) return "unknown"
  const blocks = text.split(/\n\s*\n/).map((block) => block.trim()).filter(Boolean)
  const looksLikeTags = (value: string) => value.split(/[,，；;\n]/).map((tag) => tag.trim()).filter(Boolean).every((tag) => tag.length <= 120 && tag.split(/\s+/).length <= 4 && !/[。！？!?]/.test(tag) && !/(?:[A-Za-z]\.(?:\s|$))/.test(tag) && (tag.match(/[\u3400-\u9fff]/g)?.length ?? 0) <= 12)
  if (blocks.length > 1 && blocks.some(looksLikeTags)) return "mixed"
  return looksLikeTags(text) ? "tag" : "natural"
}

// Separators apply only to a known Tag source; prose must retain punctuation.
const TAG_SEPARATOR = /\s*[,，]\s*|\.\s+|\.$/

export function splitCaptionTags(caption: string, format: CaptionFormat = "unknown"): string[] {
  if (format !== "tag") return []
  return caption.split(TAG_SEPARATOR).map((tag) => tag.trim()).filter(Boolean)
}

export function addTagToCaption(caption: string, tag: string, format: CaptionFormat = "unknown"): string {
  if (format !== "tag" && (caption.trim() || format !== "unknown")) return caption
  const clean = tag.trim()
  const tags = splitCaptionTags(caption, "tag")
  if (!clean || tags.includes(clean)) return tags.join(", ")
  return [...tags, clean].join(", ")
}

export function removeTagFromCaption(caption: string, tag: string, format: CaptionFormat = "unknown"): string {
  if (format !== "tag") return caption
  const clean = tag.trim()
  return splitCaptionTags(caption, "tag").filter((item) => item !== clean).join(", ")
}

/** Move a tag from one index to another; used by chip drag-and-drop reorder. */
export function moveCaptionTag(caption: string, fromIndex: number, toIndex: number, format: CaptionFormat = "unknown"): string {
  if (format !== "tag") return caption
  const tags = splitCaptionTags(caption, "tag")
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
