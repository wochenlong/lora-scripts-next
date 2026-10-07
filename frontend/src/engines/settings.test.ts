// @vitest-environment jsdom
import { beforeEach, afterEach, expect, it, vi } from "vitest"

beforeEach(() => { vi.resetModules(); localStorage.clear() })
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); vi.useRealTimers() })

async function setup() {
  const settings = await import("./settings")
  const prefs = await import("./prefs")
  const order = await import("./listPreferences")
  return { ...settings, ...prefs, ...order }
}
function response(data: unknown, status = 200) {
  return new Response(JSON.stringify(status === 200 ? { status: "success", data } : { status: "error", message: "stale revision" }), { status })
}

it("hydrates server authority, serializes patches, and merges against current preferences", async () => {
  let server = { schema_version: 1, revision: 4, engine_prefs: { defaultEngine: "musubi", rememberLast: true, lastByModel: {} }, engine_order: ["musubi"] }
  const requests: { revision: number; patch: object }[] = []
  vi.stubGlobal("fetch", vi.fn(async (_url, options) => {
    if (options?.method === "PATCH") {
      const body = JSON.parse(options.body)
      requests.push(body)
      expect(body.revision).toBe(server.revision)
      server = { ...server, ...body.patch, revision: server.revision + 1 }
    }
    return response(server)
  }))
  localStorage.setItem("nt.training.enginePrefs", '{"defaultEngine":"ai-toolkit"}')
  const api = await setup()
  await api.loadEngineSettings()
  expect(api.readEnginePrefs().defaultEngine).toBe("musubi")
  await Promise.all([
    api.rememberSelection("anima", "anima-fast", "lora"),
    api.writeEnginePrefs({ defaultEngine: "kohya" }),
    api.rememberSelection("flux", "musubi", "lora"),
    api.saveEngineOrder(["kohya", "musubi"]),
  ])
  expect(requests.map((r) => r.revision)).toEqual([4, 5, 6, 7])
  expect(api.readEnginePrefs()).toMatchObject({ defaultEngine: "kohya", lastByModel: {
    anima: { engine: "anima-fast", target: "lora" }, flux: { engine: "musubi", target: "lora" },
  } })
  expect(localStorage.getItem("nt.training.enginePrefs")).toBe('{"defaultEngine":"ai-toolkit"}')
})

it("refetches on conflict without retrying the patch or applying queued stale changes", async () => {
  const fetcher = vi.fn()
    .mockResolvedValueOnce(response({ schema_version: 1, revision: 0 }))
    .mockResolvedValueOnce(response(null, 409))
    .mockResolvedValueOnce(response({ schema_version: 1, revision: 1, engine_prefs: { defaultEngine: "musubi", rememberLast: false } }))
  vi.stubGlobal("fetch", fetcher)
  const api = await setup()
  await api.loadEngineSettings()
  const results = await Promise.allSettled([api.writeEnginePrefs({ defaultEngine: "ai-toolkit" }), api.saveEngineOrder(["kohya"])])
  expect(results.map((r) => r.status)).toEqual(["rejected", "rejected"])
  expect(fetcher).toHaveBeenCalledTimes(3)
  expect(api.readEnginePrefs().defaultEngine).toBe("musubi")
  expect(api.engineSettingsState.error).toBeTruthy()
})

it("keeps startup failures visible and blocks saves until a successful retry", async () => {
  const fetcher = vi.fn().mockRejectedValueOnce(new Error("offline"))
  vi.stubGlobal("fetch", fetcher)
  const api = await setup()
  await expect(api.loadEngineSettings()).rejects.toThrow("offline")
  await expect(api.writeEnginePrefs({ rememberLast: false })).rejects.toThrow()
  expect(api.engineSettingsState.error).toContain("offline")
  expect(fetcher).toHaveBeenCalledTimes(1)
  fetcher.mockResolvedValue(response({ schema_version: 1, revision: 0 }))
  await api.loadEngineSettings()
  expect(api.engineSettingsState.error).toBe("")
})

it("imports only absent server fields and preserves the legacy keys", async () => {
  let server: Record<string, unknown> = { schema_version: 1, revision: 0, engine_prefs: { defaultEngine: "musubi", rememberLast: false } }
  const fetcher = vi.fn(async (_url, options) => {
    if (options?.method === "PATCH") server = { ...server, ...JSON.parse(options.body).patch, revision: 1 }
    return response(server)
  })
  vi.stubGlobal("fetch", fetcher)
  localStorage.setItem("nt.training.enginePrefs", '{"defaultEngine":"ai-toolkit"}')
  localStorage.setItem("nt.settings.engineOrder", '["musubi","kohya"]')
  const api = await setup()
  await api.loadEngineSettings()
  expect(api.legacyEngineImport()).toEqual({ engine_order: ["musubi", "kohya"] })
  await api.importLegacyEngineSettings()
  expect(api.readEnginePrefs().defaultEngine).toBe("musubi")
  expect(api.legacyEngineImport()).toEqual({})
  expect(localStorage.getItem("nt.settings.engineOrder")).toBe('["musubi","kohya"]')
})

it("bounds a hanging initial GET and exposes the timeout for retry", async () => {
  vi.useFakeTimers()
  const timeout = vi.spyOn(AbortSignal, "timeout").mockImplementation((milliseconds) => {
    const controller = new AbortController()
    setTimeout(() => controller.abort(new Error("settings timeout")), milliseconds)
    return controller.signal
  })
  vi.stubGlobal("fetch", vi.fn((_url, options) => new Promise((_resolve, reject) => {
    options?.signal?.addEventListener("abort", () => reject(options.signal.reason))
  })))
  const api = await setup()
  const loaded = api.loadEngineSettings()
  const rejection = expect(loaded).rejects.toThrow("settings timeout")
  await vi.advanceTimersByTimeAsync(10_000)
  expect(timeout).toHaveBeenCalledWith(10_000)
  await rejection
  expect(api.engineSettingsState.loading).toBe(false)
  expect(api.engineSettingsState.ready).toBe(false)
  expect(api.engineSettingsState.error).toContain("timeout")
})

it("bounds a hanging PATCH, reconciles server state, and releases the queue", async () => {
  vi.useFakeTimers()
  const timeout = vi.spyOn(AbortSignal, "timeout").mockImplementation((milliseconds) => {
    const controller = new AbortController()
    setTimeout(() => controller.abort(new Error("write timeout")), milliseconds)
    return controller.signal
  })
  const fetcher = vi.fn()
    .mockResolvedValueOnce(response({ schema_version: 1, revision: 2, engine_prefs: { defaultEngine: "kohya", rememberLast: true } }))
    .mockImplementationOnce((_url, options) => new Promise((_resolve, reject) => {
      options?.signal?.addEventListener("abort", () => reject(options.signal.reason))
    }))
    .mockResolvedValueOnce(response({ schema_version: 1, revision: 3, engine_prefs: { defaultEngine: "musubi", rememberLast: true } }))
    .mockResolvedValueOnce(response({ schema_version: 1, revision: 4, engine_prefs: { defaultEngine: "ai-toolkit", rememberLast: true } }))
  vi.stubGlobal("fetch", fetcher)
  const api = await setup()
  await api.loadEngineSettings()
  const first = api.writeEnginePrefs({ defaultEngine: "kohya" })
  const second = api.writeEnginePrefs({ defaultEngine: "ai-toolkit" })
  await vi.advanceTimersByTimeAsync(10_000)
  await expect(first).rejects.toThrow("timeout")
  await expect(second).rejects.toThrow()
  expect(timeout).toHaveBeenCalledWith(10_000)
  expect(fetcher).toHaveBeenCalledTimes(3)
  expect(api.readEnginePrefs().defaultEngine).toBe("musubi")
})

it("imports only supported legacy engines and remembered selections", async () => {
  const fetcher = vi.fn().mockResolvedValue(response({ schema_version: 1, revision: 0 }))
  vi.stubGlobal("fetch", fetcher)
  localStorage.setItem("nt.training.enginePrefs", JSON.stringify({
    defaultEngine: "stale-engine",
    rememberLast: true,
    lastByModel: {
      good: { engine: "anima-fast", target: "lora" },
      staleEngine: { engine: "gone", target: "lora" },
      staleTarget: { engine: "kohya", target: "unsupported" },
      malformed: "not-an-object",
    },
  }))
  localStorage.setItem("nt.settings.engineOrder", '["musubi","gone",42,"ai-toolkit","musubi"]')
  const api = await setup()
  await api.loadEngineSettings()
  expect(api.legacyEngineImport()).toEqual({
    engine_prefs: {
      defaultEngine: "kohya",
      rememberLast: true,
      lastByModel: { good: { engine: "anima-fast", target: "lora" } },
    },
    engine_order: ["musubi", "ai-toolkit"],
  })
})
