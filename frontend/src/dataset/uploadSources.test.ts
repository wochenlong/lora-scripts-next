// @vitest-environment jsdom
import { describe, expect, it } from "vitest"
import { collectUploadItems, commonTopFolder, isAcceptedUploadName, itemsFromFileList, partitionAccepted } from "./uploadSources"

function fileEntry(name: string, content = "x"): FileSystemEntry {
  const file = new File([content], name)
  return {
    isFile: true,
    isDirectory: false,
    name,
    file: (resolve: (file: File) => void) => resolve(file),
  } as unknown as FileSystemEntry
}

/** Directory reader yields one entry per readEntries call, like the browser's batching. */
function dirEntry(name: string, children: FileSystemEntry[]): FileSystemEntry {
  let index = 0
  return {
    isFile: false,
    isDirectory: true,
    name,
    createReader: () => ({
      readEntries: (resolve: (entries: FileSystemEntry[]) => void) => {
        const next = children.slice(index, index + 1)
        index += next.length
        resolve(next)
      },
    }),
  } as unknown as FileSystemEntry
}

function dropWith(entries: (FileSystemEntry | null)[], files: File[] = []): DataTransfer {
  return {
    items: entries.map((entry) => ({ webkitGetAsEntry: () => entry })),
    files,
  } as unknown as DataTransfer
}

describe("isAcceptedUploadName", () => {
  it("accepts supported image and caption extensions case-insensitively", () => {
    expect(isAcceptedUploadName("a.PNG")).toBe(true)
    expect(isAcceptedUploadName("nested/dir/b.jpeg")).toBe(true)
    expect(isAcceptedUploadName("caption.txt")).toBe(true)
  })

  it("rejects other extensions", () => {
    expect(isAcceptedUploadName("model.safetensors")).toBe(false)
    expect(isAcceptedUploadName("archive.zip")).toBe(false)
  })
})

describe("itemsFromFileList", () => {
  it("keeps bare file names by default", () => {
    const items = itemsFromFileList([new File(["x"], "a.png")])
    expect(items.map((item) => item.path)).toEqual(["a.png"])
  })

  it("uses webkitRelativePath when folder picking", () => {
    const file = new File(["x"], "a.png")
    Object.defineProperty(file, "webkitRelativePath", { value: "set/1/a.png" })
    expect(itemsFromFileList([file], true).map((item) => item.path)).toEqual(["set/1/a.png"])
  })
})

describe("collectUploadItems", () => {
  it("walks nested folders and keeps the hierarchy", async () => {
    const tree = dirEntry("mydata", [
      fileEntry("1.png"),
      dirEntry("sub", [fileEntry("2.txt")]),
    ])
    const items = await collectUploadItems(dropWith([tree]))
    expect(items.map((item) => item.path).sort()).toEqual(["mydata/1.png", "mydata/sub/2.txt"])
  })

  it("falls back to dataTransfer.files when no entries are exposed", async () => {
    const items = await collectUploadItems(dropWith([null], [new File(["x"], "loose.png")]))
    expect(items.map((item) => item.path)).toEqual(["loose.png"])
  })
})

describe("partitionAccepted", () => {
  it("splits accepted files from ignored ones", () => {
    const items = [
      { file: new File(["x"], "a.png"), path: "a.png" },
      { file: new File(["x"], "b.zip"), path: "b.zip" },
    ]
    const { accepted, ignored } = partitionAccepted(items)
    expect(accepted.map((item) => item.path)).toEqual(["a.png"])
    expect(ignored).toBe(1)
  })
})

describe("commonTopFolder", () => {
  it("returns the single dropped folder name", () => {
    expect(commonTopFolder([
      { file: new File(["x"], "1.png"), path: "set/1.png" },
      { file: new File(["x"], "2.png"), path: "set/sub/2.png" },
    ])).toBe("set")
  })

  it("returns null for loose files or mixed roots", () => {
    expect(commonTopFolder([{ file: new File(["x"], "1.png"), path: "1.png" }])).toBeNull()
    expect(commonTopFolder([
      { file: new File(["x"], "1.png"), path: "a/1.png" },
      { file: new File(["x"], "2.png"), path: "b/2.png" },
    ])).toBeNull()
  })
})
