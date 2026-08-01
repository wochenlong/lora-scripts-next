export function splitCaptionTags(caption: string): string[] {
  return caption.split(",").map((tag) => tag.trim()).filter(Boolean)
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
