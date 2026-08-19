import { ref } from "vue"
import type { PathBrowserMode } from "../api/pathBrowser"

/** Shared state for opening the in-browser server path picker (#244). */
export function useServerPathPick() {
  const open = ref(false)
  const mode = ref<PathBrowserMode>("folder")
  const initialPath = ref("")
  const nameFilter = ref("")
  let resolvePick: ((path: string | null) => void) | null = null

  function pick(options?: {
    mode?: PathBrowserMode
    initialPath?: string
    nameFilter?: string
  }): Promise<string | null> {
    mode.value = options?.mode || "folder"
    initialPath.value = options?.initialPath || ""
    nameFilter.value = options?.nameFilter || ""
    open.value = true
    return new Promise((resolve) => {
      resolvePick = resolve
    })
  }

  function onConfirm(path: string) {
    resolvePick?.(path)
    resolvePick = null
    open.value = false
  }

  function onCancel() {
    if (resolvePick) {
      resolvePick(null)
      resolvePick = null
    }
  }

  return {
    open,
    mode,
    initialPath,
    nameFilter,
    pick,
    onConfirm,
    onCancel,
  }
}
