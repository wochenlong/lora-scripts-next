// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest"
import { ApiError } from "../api/client"

const { pickFile, readPathPickerPreference } = vi.hoisted(() => ({
  pickFile: vi.fn(),
  readPathPickerPreference: vi.fn(),
}))

vi.mock("../api/schemas", () => ({
  schemasApi: { pickFile },
}))

vi.mock("../utils/pathPickerPreference", () => ({
  readPathPickerPreference,
}))

import { shouldTryNativePicker, useServerPathPick } from "./useServerPathPick"

function pickerError(code: string) {
  return new ApiError("picker failed", "fail", {
    status: "fail",
    data: { code, web_picker: true },
  })
}

describe("useServerPathPick", () => {
  beforeEach(() => {
    vi.unstubAllGlobals()
    pickFile.mockReset()
    readPathPickerPreference.mockReset()
    readPathPickerPreference.mockReturnValue("auto")
  })

  it("opens the web picker directly when web is preferred", async () => {
    readPathPickerPreference.mockReturnValue("web")
    const picker = useServerPathPick()

    const result = picker.pick({ mode: "file", initialPath: "D:/models", nameFilter: "*.safetensors" })

    expect(pickFile).not.toHaveBeenCalled()
    expect(picker.open.value).toBe(true)
    expect(picker.mode.value).toBe("file")
    expect(picker.initialPath.value).toBe("D:/models")
    expect(picker.nameFilter.value).toBe("*.safetensors")

    picker.onConfirm("D:/models/base.safetensors")
    await expect(result).resolves.toBe("D:/models/base.safetensors")
  })

  it("uses the web picker automatically for remote browser hosts", () => {
    expect(shouldTryNativePicker("auto", "trainer.example.com")).toBe(false)
    expect(shouldTryNativePicker("auto", "127.0.0.1")).toBe(true)
    expect(shouldTryNativePicker("auto", "localhost")).toBe(true)
    expect(shouldTryNativePicker("native", "trainer.example.com")).toBe(true)
  })

  it.each(["auto", "native"])("uses the native picker first for %s", async (preference) => {
    readPathPickerPreference.mockReturnValue(preference)
    pickFile.mockResolvedValue({ path: "D:/models/base.safetensors" })
    const picker = useServerPathPick()

    await expect(picker.pick({ mode: "file" })).resolves.toBe("D:/models/base.safetensors")

    expect(pickFile).toHaveBeenCalledWith("model-file")
    expect(picker.open.value).toBe(false)
  })

  it("requests image files explicitly from the native picker", async () => {
    pickFile.mockResolvedValue({ path: "D:/images/preview.png" })
    const picker = useServerPathPick()

    await expect(picker.pick({ mode: "file", fileType: "image" })).resolves.toBe("D:/images/preview.png")

    expect(pickFile).toHaveBeenCalledWith("image")
    expect(picker.open.value).toBe(false)
  })

  it.each(["web", "remote"])("uses image filters for %s web selection", async (selection) => {
    if (selection === "web") {
      readPathPickerPreference.mockReturnValue("web")
    } else {
      vi.stubGlobal("location", { hostname: "trainer.example.com" })
    }
    const picker = useServerPathPick()

    const result = picker.pick({ mode: "file", fileType: "image", initialPath: "D:/images" })

    expect(pickFile).not.toHaveBeenCalled()
    expect(picker.mode.value).toBe("file")
    expect(picker.initialPath.value).toBe("D:/images")
    expect(picker.nameFilter.value).toBe("*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.gif;*.tif;*.tiff")
    picker.onConfirm("D:/images/preview.webp")
    await expect(result).resolves.toBe("D:/images/preview.webp")
  })

  it("treats native cancellation as cancellation without opening the web picker", async () => {
    pickFile.mockRejectedValue(pickerError("CANCELLED"))
    const picker = useServerPathPick()

    await expect(picker.pick()).resolves.toBeNull()

    expect(pickFile).toHaveBeenCalledWith("folder")
    expect(picker.open.value).toBe(false)
  })

  it("returns null when native image selection is cancelled", async () => {
    pickFile.mockRejectedValue(pickerError("CANCELLED"))
    const picker = useServerPathPick()

    await expect(picker.pick({ mode: "file", fileType: "image" })).resolves.toBeNull()

    expect(pickFile).toHaveBeenCalledWith("image")
    expect(picker.open.value).toBe(false)
  })

  it.each([undefined, "*.png"])("preserves image options in web fallback with filter %s", async (nameFilter) => {
    pickFile.mockRejectedValue(pickerError("GUI_PICKER_UNAVAILABLE"))
    const picker = useServerPathPick()

    const result = picker.pick({ mode: "file", fileType: "image", initialPath: "D:/images/preview.jpg", nameFilter })
    await vi.waitFor(() => expect(picker.open.value).toBe(true))

    expect(pickFile).toHaveBeenCalledWith("image")
    expect(picker.mode.value).toBe("file")
    expect(picker.initialPath.value).toBe("D:/images/preview.jpg")
    expect(picker.nameFilter.value).toBe(nameFilter ?? "*.png;*.jpg;*.jpeg;*.webp;*.bmp;*.gif;*.tif;*.tiff")
    picker.onCancel()
    await expect(result).resolves.toBeNull()
  })

  it.each([
    pickerError("GUI_PICKER_UNAVAILABLE"),
    new ApiError("network failed", "network"),
  ])("falls back to the web picker when native selection fails", async (error) => {
    pickFile.mockRejectedValue(error)
    const picker = useServerPathPick()

    const result = picker.pick({ mode: "folder", initialPath: "D:/datasets" })
    await vi.waitFor(() => expect(picker.open.value).toBe(true))

    expect(picker.initialPath.value).toBe("D:/datasets")
    picker.onCancel()
    await expect(result).resolves.toBeNull()
  })
})
