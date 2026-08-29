// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { HOST_REFRESH_DELAY_MS, scheduleHostRefresh } from "./hostRefresh"

describe("scheduleHostRefresh", () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it("reloads once after the toast-visible delay", () => {
    const reload = vi.fn()
    scheduleHostRefresh(reload)
    // The success toast must be visible first — no immediate reload.
    expect(reload).not.toHaveBeenCalled()
    vi.advanceTimersByTime(HOST_REFRESH_DELAY_MS - 1)
    expect(reload).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    expect(reload).toHaveBeenCalledTimes(1)
  })
})
