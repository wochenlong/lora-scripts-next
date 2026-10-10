// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest"
import type { UserPreset } from "../api/userPresets"
import {
  LEGACY_CAPTION_TEMPLATES_KEY,
  TAGGER_CAPTION_TRAIN_TYPE,
  createCaptionPresetService,
} from "./captionPresets"

function preset(overrides: Partial<UserPreset> = {}): UserPreset {
  return {
    id: "preset-1",
    name: "Portrait",
    train_type: TAGGER_CAPTION_TRAIN_TYPE,
    description: null,
    config: { prompt: "Describe the portrait.", language: "en" },
    ...overrides,
  }
}

function client(records: UserPreset[] = []) {
  return {
    list: vi.fn().mockResolvedValue(records),
    create: vi.fn().mockImplementation(async payload => preset({ id: `created-${payload.name}`, ...payload })),
    update: vi.fn().mockImplementation(async (id, payload) => preset({ id, ...payload })),
    remove: vi.fn().mockResolvedValue({ removed: true }),
  }
}

beforeEach(() => localStorage.clear())

describe("caption preset adapter", () => {
  it("lists tagger caption presets and omits malformed records", async () => {
    const api = client([
      preset(),
      preset({ id: "bad-prompt", config: { prompt: 4, language: "en" } }),
      preset({ id: "bad-language", config: { prompt: "Prompt", language: null } }),
    ])

    const service = createCaptionPresetService(api)

    expect(await service.list()).toEqual([
      { id: "preset-1", name: "Portrait", prompt: "Describe the portrait.", language: "en" },
    ])
    expect(api.list).toHaveBeenCalledWith("tagger-caption")
  })

  it("maps create, update, and delete operations to user preset payloads", async () => {
    const api = client()
    const service = createCaptionPresetService(api)

    await expect(service.create({
      name: "Portrait",
      prompt: "Describe the portrait.",
      language: "en",
    })).resolves.toMatchObject({ id: "created-Portrait", name: "Portrait" })
    expect(api.create).toHaveBeenCalledWith({
      name: "Portrait",
      train_type: "tagger-caption",
      config: { prompt: "Describe the portrait.", language: "en" },
    })

    await expect(service.update("preset-1", {
      name: "Portrait",
      prompt: "Updated prompt.",
      language: "zh-CN",
    })).resolves.toMatchObject({ id: "preset-1", prompt: "Updated prompt.", language: "zh-CN" })
    expect(api.update).toHaveBeenCalledWith("preset-1", {
      name: "Portrait",
      config: { prompt: "Updated prompt.", language: "zh-CN" },
    })

    await service.remove("preset-1")
    expect(api.remove).toHaveBeenCalledWith("preset-1")
  })
})

describe("legacy migration", () => {
  it("imports valid legacy prompts and removes browser data after all imports succeed", async () => {
    const api = client()
    const service = createCaptionPresetService(api)
    localStorage.setItem(LEGACY_CAPTION_TEMPLATES_KEY, JSON.stringify({
      "custom-one": "Legacy prompt one",
      "custom-two": "Legacy prompt two",
      empty: " ",
      invalid: 3,
    }))

    const migrated = await service.migrateLegacy([], localStorage)

    expect(api.create).toHaveBeenCalledTimes(2)
    expect(api.create).toHaveBeenNthCalledWith(1, {
      name: "custom-one",
      train_type: "tagger-caption",
      description: "legacy-tagger-caption:custom-one",
      config: { prompt: "Legacy prompt one", language: "en" },
    })
    expect(migrated).toHaveLength(2)
    expect(localStorage.getItem(LEGACY_CAPTION_TEMPLATES_KEY)).toBeNull()
  })

  it("retains browser data when any import fails", async () => {
    const api = client()
    api.create
      .mockResolvedValueOnce(preset({ id: "created-one" }))
      .mockRejectedValueOnce(new Error("offline"))
    const service = createCaptionPresetService(api)
    const legacy = JSON.stringify({ one: "One", two: "Two" })
    localStorage.setItem(LEGACY_CAPTION_TEMPLATES_KEY, legacy)

    await expect(service.migrateLegacy([], localStorage)).rejects.toThrow("offline")

    expect(localStorage.getItem(LEGACY_CAPTION_TEMPLATES_KEY)).toBe(legacy)
  })

  it("skips records already carrying the deterministic legacy marker", async () => {
    const api = client()
    const service = createCaptionPresetService(api)
    const existing = preset({
      id: "existing-one",
      description: "legacy-tagger-caption:one",
      config: { prompt: "One", language: "en" },
    })
    localStorage.setItem(LEGACY_CAPTION_TEMPLATES_KEY, JSON.stringify({ one: "One", two: "Two" }))

    const migrated = await service.migrateLegacy([existing], localStorage)

    expect(api.create).toHaveBeenCalledTimes(1)
    expect(api.create).toHaveBeenCalledWith(expect.objectContaining({
      description: "legacy-tagger-caption:two",
    }))
    expect(migrated.map(item => item.id)).toEqual(["existing-one", "created-two"])
    expect(localStorage.getItem(LEGACY_CAPTION_TEMPLATES_KEY)).toBeNull()
  })

  it("ignores malformed legacy storage without creating records", async () => {
    const api = client()
    const service = createCaptionPresetService(api)
    localStorage.setItem(LEGACY_CAPTION_TEMPLATES_KEY, "{")

    await expect(service.migrateLegacy([], localStorage)).resolves.toEqual([])

    expect(api.create).not.toHaveBeenCalled()
    expect(localStorage.getItem(LEGACY_CAPTION_TEMPLATES_KEY)).toBe("{")
  })
})
