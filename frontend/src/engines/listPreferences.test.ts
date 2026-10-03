// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest"
import {
  normalizeOrder, moveEngine, readEngineOrder, saveEngineOrder, matchesEngineFilter,
} from "./listPreferences"

const ids = ["kohya", "anima-fast", "musubi", "ai-toolkit"]
afterEach(() => { localStorage.clear(); vi.restoreAllMocks() })

it("normalizes stale, duplicate and non-string IDs and appends new engines", () => {
  expect(normalizeOrder(["musubi", "old", "musubi", 3], ids)).toEqual(["musubi", "kohya", "anima-fast", "ai-toolkit"])
  for (const invalid of [null, {}, "kohya", 42]) expect(normalizeOrder(invalid, ids)).toEqual(ids)
})
it("inserts before or after a target without disturbing other entries", () => {
  expect(moveEngine(ids, "ai-toolkit", "anima-fast")).toEqual(["kohya", "ai-toolkit", "anima-fast", "musubi"])
  expect(moveEngine(ids, "kohya", "musubi", true)).toEqual(["anima-fast", "musubi", "kohya", "ai-toolkit"])
  expect(moveEngine(ids, "kohya", "kohya")).toEqual(ids)
  expect(moveEngine(ids, "missing", "kohya")).toEqual(ids)
  expect(moveEngine(ids, "kohya", "missing")).toEqual(ids)
})
it("keeps hidden engines in relative order during a filtered move", () => {
  expect(moveEngine(ids, "ai-toolkit", "kohya")).toEqual(["ai-toolkit", "kohya", "anima-fast", "musubi"])
})
it("persists order without changing training preferences", () => {
  localStorage.setItem("nt.training.enginePrefs", '{"rememberLast":false}')
  expect(saveEngineOrder([...ids].reverse())).toBe(true)
  expect(readEngineOrder(ids)).toEqual([...ids].reverse())
  expect(localStorage.getItem("nt.training.enginePrefs")).toBe('{"rememberLast":false}')
})
it("recovers from malformed or inaccessible storage", () => {
  localStorage.setItem("nt.settings.engineOrder", "{")
  expect(readEngineOrder(ids)).toEqual(ids)
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked") })
  expect(readEngineOrder(ids)).toEqual(ids)
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("quota") })
  expect(saveEngineOrder(ids)).toBe(false)
})
it("combines localized search and precise status filters", () => {
  expect(matchesEngineFilter("Anima Fast 图像", "ready", " ANIMA ", "installed")).toBe(true)
  expect(matchesEngineFilter("Anima Fast 图像", "installed_unverified", "图像", "installed")).toBe(true)
  expect(matchesEngineFilter("Anima", "not_installed", "", "not_installed")).toBe(true)
  expect(matchesEngineFilter("Anima", "ready", "flux", "all")).toBe(false)
  for (const state of ["unknown", "broken", "disabled", "installing", "auditing", "coming_soon"] as const) {
    expect(matchesEngineFilter("Anima", state, "", "all")).toBe(true)
    expect(matchesEngineFilter("Anima", state, "", "installed")).toBe(false)
    expect(matchesEngineFilter("Anima", state, "", "not_installed")).toBe(false)
  }
})
