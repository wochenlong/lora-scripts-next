import type { UploadFileItem } from "../api/datasets"

/** Extensions accepted by the dataset upload endpoint. */
export const UPLOAD_ACCEPT = ".png,.jpg,.jpeg,.webp,.bmp,.txt"

const ACCEPTED_SUFFIXES = UPLOAD_ACCEPT.split(",")

export function isAcceptedUploadName(name: string): boolean {
  const lower = name.toLowerCase()
  return ACCEPTED_SUFFIXES.some((suffix) => lower.endsWith(suffix))
}

export function itemsFromFileList(files: Iterable<File>, relativePath = false): UploadFileItem[] {
  return Array.from(files).map((file) => ({
    file,
    path: relativePath ? (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name : file.name,
  }))
}

async function readEntry(entry: FileSystemEntry, prefix: string, out: UploadFileItem[]): Promise<void> {
  if (entry.isFile) {
    const file = await new Promise<File>((resolve, reject) => (entry as FileSystemFileEntry).file(resolve, reject))
    out.push({ file, path: prefix + file.name })
    return
  }
  if (entry.isDirectory) {
    const reader = (entry as FileSystemDirectoryEntry).createReader()
    // readEntries yields at most 100 entries per call, so read until it returns empty.
    for (;;) {
      const entries = await new Promise<FileSystemEntry[]>((resolve, reject) => reader.readEntries(resolve, reject))
      if (!entries.length) return
      for (const child of entries) await readEntry(child, `${prefix}${entry.name}/`, out)
    }
  }
}

/**
 * Collect dropped files and folders, keeping the directory hierarchy.
 * Folders need `webkitGetAsEntry`; `dataTransfer.files` only lists loose files.
 */
export async function collectUploadItems(dataTransfer: DataTransfer | null): Promise<UploadFileItem[]> {
  const items = dataTransfer?.items
  if (items) {
    const entries: FileSystemEntry[] = []
    for (const item of Array.from(items)) {
      const entry = item.webkitGetAsEntry?.()
      if (entry) entries.push(entry)
    }
    if (entries.length) {
      const collected: UploadFileItem[] = []
      for (const entry of entries) await readEntry(entry, "", collected)
      return collected
    }
  }
  return itemsFromFileList(dataTransfer?.files ?? [])
}

export function partitionAccepted(items: UploadFileItem[]): { accepted: UploadFileItem[]; ignored: number } {
  const accepted = items.filter((item) => isAcceptedUploadName(item.path))
  return { accepted, ignored: items.length - accepted.length }
}

/** Name of the single dropped top-level folder, or null when files were dropped loose. */
export function commonTopFolder(items: UploadFileItem[]): string | null {
  const segments = items.map((item) => item.path.split("/"))
  const first = segments[0]
  if (!first || first.length < 2 || !first[0]) return null
  return segments.every((parts) => parts.length > 1 && parts[0] === first[0]) ? first[0] : null
}
