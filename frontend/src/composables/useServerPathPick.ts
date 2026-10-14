import { ref } from "vue"
import { ApiError } from "../api/client"
import type { PathBrowserMode } from "../api/pathBrowser"
import { schemasApi, type FilePickerType } from "../api/schemas"
import {
  readPathPickerPreference,
  type PathPickerPreference,
} from "../utils/pathPickerPreference"

interface ServerPathPickOptions {
  mode?: PathBrowserMode
  initialPath?: string
  nameFilter?: string
  /** 文件模式默认选择模型权重；图片调用须显式指定。 */
  fileType?: FilePickerType
}

const IMAGE_NAME_FILTER = "*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.gif;*.tif;*.tiff"

export function shouldTryNativePicker(
  preference: PathPickerPreference,
  hostname = globalThis.location?.hostname ?? "localhost",
): boolean {
  if (preference === "native") return true
  if (preference === "web") return false
  return hostname === "localhost"
    || hostname === "127.0.0.1"
    || hostname === "::1"
    || hostname === "[::1]"
}

/** Shared state for opening the in-browser server path picker (#244). */
export function useServerPathPick() {
  const open = ref(false)
  const mode = ref<PathBrowserMode>("folder")
  const initialPath = ref("")
  const nameFilter = ref("")
  let resolvePick: ((path: string | null) => void) | null = null

  function openWebPicker(options?: ServerPathPickOptions): Promise<string | null> {
    mode.value = options?.mode || "folder"
    initialPath.value = options?.initialPath || ""
    nameFilter.value = options?.nameFilter
      || (options?.mode === "file" && options.fileType === "image" ? IMAGE_NAME_FILTER : "")
    open.value = true
    return new Promise((resolve) => {
      resolvePick = resolve
    })
  }

  async function pick(options?: ServerPathPickOptions): Promise<string | null> {
    if (!shouldTryNativePicker(readPathPickerPreference())) {
      return openWebPicker(options)
    }

    try {
      const pickerType = options?.mode === "file" ? options.fileType ?? "model-file" : "folder"
      const result = await schemasApi.pickFile(pickerType)
      return result.path
    } catch (error) {
      const data = error instanceof ApiError ? error.response?.data : null
      const code = data && typeof data === "object" && "code" in data ? data.code : null
      if (code === "CANCELLED") return null
      return openWebPicker(options)
    }
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
    open.value = false
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
