// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest"
import { lastSelectionFor, readEnginePrefs, rememberSelection, writeEnginePrefs } from "./prefs"

const KEY = "nt.training.enginePrefs"

afterEach(() => {
  localStorage.removeItem(KEY)
})

describe("engine prefs", () => {
  it("defaults rememberLast to true", () => {
    expect(readEnginePrefs().rememberLast).toBe(true)
  })

  it("ignores legacy browser values until explicitly imported", () => {
    localStorage.setItem(KEY, '{"defaultEngine":"ai-toolkit","rememberLast":false}')
    expect(readEnginePrefs().defaultEngine).toBe("kohya")
    expect(readEnginePrefs().rememberLast).toBe(true)
    localStorage.setItem(KEY, '{"defaultEngine":"missing"}')
    expect(readEnginePrefs().defaultEngine).toBe("kohya")
  })

  it("rejects remembering without hydrated settings", async () => {
    await expect(rememberSelection("anima", "anima-fast", "lora")).rejects.toThrow()
    expect(lastSelectionFor("anima")).toBeUndefined()
  })

  it("does not treat an unavailable server save as persisted", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")))
    await expect(writeEnginePrefs({ rememberLast: false })).rejects.toThrow()
    expect(readEnginePrefs().rememberLast).toBe(true)
    expect(localStorage.getItem(KEY)).toBeNull()
    vi.unstubAllGlobals()
  })
})
