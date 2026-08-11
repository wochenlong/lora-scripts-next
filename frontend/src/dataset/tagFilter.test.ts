import { describe, expect, it } from "vitest"
import { filterItemsByTags, searchTagList, sortTagList, type TagCount } from "./tagFilter"
import { estimateTokenLength } from "./tokenLength"

const items = [
  { name: "a", tags: ["bplay", "1girl"] },
  { name: "b", tags: ["bplay", "cat ears"] },
  { name: "c", tags: ["1girl"] },
  { name: "d", tags: [] },
]

describe("filterItemsByTags", () => {
  it("passes items through when nothing is selected", () => {
    expect(filterItemsByTags(items, new Set(), "and")).toBe(items)
  })

  it("filters with AND logic requiring every selected tag", () => {
    const selected = new Set(["bplay", "1girl"])
    expect(filterItemsByTags(items, selected, "and").map((item) => item.name)).toEqual(["a"])
  })

  it("filters with OR logic requiring any selected tag", () => {
    const selected = new Set(["bplay", "cat ears"])
    expect(filterItemsByTags(items, selected, "or").map((item) => item.name)).toEqual(["a", "b"])
  })

  it("filters with NONE logic excluding every selected tag", () => {
    expect(filterItemsByTags(items, new Set(["bplay"]), "none").map((item) => item.name)).toEqual(["c", "d"])
    expect(filterItemsByTags(items, new Set(["bplay", "1girl"]), "none").map((item) => item.name)).toEqual(["d"])
  })
})

const tagList: TagCount[] = [
  { tag: "1girl", count: 312 },
  { tag: "bplay", count: 128 },
  { tag: "cat ears", count: 128 },
  { tag: "masterpiece", count: 96 },
]

describe("sortTagList", () => {
  it("sorts alphabetically case-insensitively in both directions", () => {
    expect(sortTagList(tagList, "alphabetical", "asc").map((entry) => entry.tag)).toEqual(["1girl", "bplay", "cat ears", "masterpiece"])
    expect(sortTagList(tagList, "alphabetical", "desc").map((entry) => entry.tag)).toEqual(["masterpiece", "cat ears", "bplay", "1girl"])
  })

  it("sorts by frequency with alphabetical tie-break", () => {
    expect(sortTagList(tagList, "frequency", "desc").map((entry) => entry.tag)).toEqual(["1girl", "bplay", "cat ears", "masterpiece"])
    expect(sortTagList(tagList, "frequency", "asc").map((entry) => entry.tag)).toEqual(["masterpiece", "bplay", "cat ears", "1girl"])
  })

  it("sorts by character length", () => {
    expect(sortTagList(tagList, "length", "asc").map((entry) => entry.tag)).toEqual(["1girl", "bplay", "cat ears", "masterpiece"])
  })

  it("sorts by estimated token length", () => {
    expect(sortTagList(tagList, "tokenLength", "desc").map((entry) => entry.tag)).toEqual(["cat ears", "1girl", "bplay", "masterpiece"])
  })

  it("does not mutate the input array", () => {
    const snapshot = [...tagList]
    sortTagList(tagList, "frequency", "asc")
    expect(tagList).toEqual(snapshot)
  })
})

describe("searchTagList", () => {
  it("returns the list untouched for blank search", () => {
    expect(searchTagList(tagList, "  ")).toBe(tagList)
  })

  it("matches case-insensitive substrings by default", () => {
    expect(searchTagList(tagList, "GIRL").map((entry) => entry.tag)).toEqual(["1girl"])
  })

  it("supports prefix and suffix modes", () => {
    expect(searchTagList(tagList, "b", "prefix").map((entry) => entry.tag)).toEqual(["bplay"])
    expect(searchTagList(tagList, "girl", "prefix")).toEqual([])
    expect(searchTagList(tagList, "girl", "suffix").map((entry) => entry.tag)).toEqual(["1girl"])
    expect(searchTagList(tagList, "ears", "suffix").map((entry) => entry.tag)).toEqual(["cat ears"])
  })
})

describe("estimateTokenLength", () => {
  it("counts words split by spaces and underscores", () => {
    expect(estimateTokenLength("1girl")).toBe(1)
    expect(estimateTokenLength("cat ears")).toBe(2)
    expect(estimateTokenLength("cat_ears")).toBe(2)
  })

  it("adds tokens for overly long words", () => {
    expect(estimateTokenLength("supercalifragilistic")).toBe(2)
  })

  it("returns zero for blank input", () => {
    expect(estimateTokenLength("")).toBe(0)
    expect(estimateTokenLength("  _ ")).toBe(0)
  })
})
