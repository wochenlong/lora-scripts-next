import { apiData } from "./client"

export type PathBrowserMode = "folder" | "file"

export interface PathBrowserEntry {
  name: string
  path: string
  type: "dir" | "file"
  size_bytes?: number
  mtime?: number
}

export interface PathBrowserRoot {
  id: string
  label: string
  path: string
}

export interface PathBrowserList {
  path: string
  parent: string | null
  mode: PathBrowserMode
  entries: PathBrowserEntry[]
  roots: PathBrowserRoot[]
  gui_picker: boolean
}

export interface PathBrowserCapability {
  web_picker: boolean
  gui_picker: boolean
  tkinter: boolean
}

export const pathBrowserApi = {
  capability: () => apiData<PathBrowserCapability>("/api/path_browser/capability"),
  list: (path: string, mode: PathBrowserMode, nameFilter = "") => {
    const params = new URLSearchParams()
    if (path) params.set("path", path)
    params.set("mode", mode)
    if (nameFilter) params.set("name_filter", nameFilter)
    return apiData<PathBrowserList>(`/api/path_browser/list?${params.toString()}`)
  },
  imageUrl: (path: string, thumb = true) => {
    const params = new URLSearchParams({ path })
    if (thumb) params.set("thumb", "1")
    return `/api/path_browser/image?${params.toString()}`
  },
}
