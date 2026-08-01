// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from "vitest"
import { THEME_KEY, getTheme, setTheme } from "./theme"

describe("theme helpers", () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.classList.remove("dark")
  })

  it("defaults to light", () => {
    expect(getTheme()).toBe("light")
  })

  it("reads the stored theme", () => {
    localStorage.setItem(THEME_KEY, "dark")
    expect(getTheme()).toBe("dark")
  })

  it("prefers the applied document class over storage", () => {
    localStorage.setItem(THEME_KEY, "light")
    document.documentElement.classList.add("dark")
    expect(getTheme()).toBe("dark")
  })

  it("applies and persists theme changes", () => {
    setTheme("dark")
    expect(document.documentElement.classList.contains("dark")).toBe(true)
    expect(localStorage.getItem(THEME_KEY)).toBe("dark")
    setTheme("light")
    expect(document.documentElement.classList.contains("dark")).toBe(false)
    expect(localStorage.getItem(THEME_KEY)).toBe("light")
  })
})
