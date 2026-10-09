/**
 * Tag separators: English comma, Chinese comma, and a sentence-ending period.
 * A period inside a token (e.g. ".hack" or "3.5") is left alone.
 */
const TAG_SEPARATOR = /\s*[,，]\s*|\.\s+|\.$/

export function splitCaptionTags(caption: string): string[] {
  return caption.split(TAG_SEPARATOR).map((tag) => tag.trim()).filter(Boolean)
}

export function addTagToCaption(caption: string, tag: string): string {
  const clean = tag.trim()
  const tags = splitCaptionTags(caption)
  if (!clean || tags.includes(clean)) return tags.join(", ")
  return [...tags, clean].join(", ")
}

export function removeTagFromCaption(caption: string, tag: string): string {
  const clean = tag.trim()
  return splitCaptionTags(caption).filter((item) => item !== clean).join(", ")
}

/** Move a tag from one index to another; used by chip drag-and-drop reorder. */
export function moveCaptionTag(caption: string, fromIndex: number, toIndex: number): string {
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
