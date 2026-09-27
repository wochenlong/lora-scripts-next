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

  it("treats native cancellation as cancellation without opening the web picker", async () => {
    pickFile.mockRejectedValue(pickerError("CANCELLED"))
    const picker = useServerPathPick()

    await expect(picker.pick()).resolves.toBeNull()

    expect(picker.open.value).toBe(false)
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
