import { estimateTokenLength } from "./tokenLength"

export type TagFilterLogic = "and" | "or" | "none"
export type TagSortBy = "alphabetical" | "frequency" | "length" | "tokenLength"
export type SortOrder = "asc" | "desc"
export type TagSearchMode = "substring" | "prefix" | "suffix"

export interface TagCount {
  tag: string
  count: number
}

export interface TagFilterState {
  selectedTags: ReadonlySet<string>
  logic: TagFilterLogic
  search: string
  searchMode: TagSearchMode
  sortBy: TagSortBy
  order: SortOrder
}

export function filterItemsByTags<T extends { tags: string[] }>(items: T[], selectedTags: ReadonlySet<string>, logic: TagFilterLogic): T[] {
  if (!selectedTags.size) return items
  if (logic === "none") return items.filter((item) => !item.tags.some((tag) => selectedTags.has(tag)))
  return items.filter((item) => {
    const owned = new Set(item.tags)
    return logic === "and" ? [...selectedTags].every((tag) => owned.has(tag)) : [...selectedTags].some((tag) => owned.has(tag))
  })
}

function compareAlphabetical(a: string, b: string): number {
  return a.toLowerCase().localeCompare(b.toLowerCase())
}

export function sortTagList(tags: TagCount[], sortBy: TagSortBy, order: SortOrder): TagCount[] {
  const direction = order === "asc" ? 1 : -1
  const metric = (entry: TagCount): number => {
    if (sortBy === "frequency") return entry.count
    if (sortBy === "length") return entry.tag.length
    if (sortBy === "tokenLength") return estimateTokenLength(entry.tag)
    return 0
  }
  return [...tags].sort((a, b) => {
    if (sortBy === "alphabetical") return compareAlphabetical(a.tag, b.tag) * direction
    return (metric(a) - metric(b)) * direction || compareAlphabetical(a.tag, b.tag)
  })
}

export function searchTagList(tags: TagCount[], search: string, mode: TagSearchMode = "substring"): TagCount[] {
  const needle = search.trim().toLowerCase()
  if (!needle) return tags
  return tags.filter(({ tag }) => {
    const candidate = tag.toLowerCase()
    if (mode === "prefix") return candidate.startsWith(needle)
    if (mode === "suffix") return candidate.endsWith(needle)
    return candidate.includes(needle)
  })
}
