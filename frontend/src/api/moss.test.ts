// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest"
import { mossApi } from "./moss"
import { enginesApi } from "./engines"
import { trainingApi } from "./training"

vi.mock("../engines/downloadSources", () => ({ resolvedDownloadSourcesPayload: () => ({ pip_index_url: "https://example.invalid/simple" }) }))
function response(data: unknown, status = "success") {
  return new Response(JSON.stringify({ status, data, message: status === "fail" ? "mock failure" : undefined }))
}
afterEach(() => vi.restoreAllMocks())

describe("MOSS engine API", () => {
  it("normalizes a native runtime status for the shared settings catalog", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(response({ state: "ready", feature_enabled: true,
      runtime: { environment_path: "/runtime/moss", python: "/runtime/moss/python" }, facts: { audit: { ok: true } } }))
    expect(await enginesApi.status("moss")).toMatchObject({ id: "moss", state: "ready", featureEnabled: true,
      runtime: { environmentPath: "/runtime/moss", python: "/runtime/moss/python" }, facts: { audit: { ok: true } } })
    expect(fetch).toHaveBeenCalledWith("/api/engines/moss/status", expect.anything())
  })

  it("maps install and repair task/stream responses using shared download settings", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(async () => response({ task_id: "moss-install", log_stream: "/api/log", progress_stream: "/api/progress",
      status: { state: "installing", feature_enabled: true } }))
    for (const action of ["install", "repair"] as const) {
      expect(await enginesApi[action]("moss")).toMatchObject({ taskId: "moss-install", logStream: "/api/log", progressStream: "/api/progress", status: { id: "moss", state: "installing" } })
      expect(fetch).toHaveBeenLastCalledWith(`/api/engines/moss/${action}`, expect.objectContaining({ method: "POST", body: JSON.stringify({ dry_run: false, pip_index_url: "https://example.invalid/simple" }) }))
    }
  })

  it("supports already-ready and uninstall responses without issuing training requests", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(response({ already_ready: true, status: { state: "ready", feature_enabled: true } })).mockResolvedValueOnce(response({}))
    expect(await enginesApi.install("moss")).toMatchObject({ alreadyReady: true, status: { id: "moss", state: "ready" } })
    expect(await enginesApi.uninstall("moss")).toEqual({ id: "moss", state: "not_installed", featureEnabled: true })
    expect(fetch).toHaveBeenLastCalledWith("/api/engines/moss/uninstall", expect.objectContaining({ method: "POST", body: "{}" }))
  })

  it("submits native configs unchanged to preflight and dry-run", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(async () => response({ ok: true, warnings: [] }))
    const config = { model_train_type: "moss-image-anima-lora", model_dir: "/models", src: "/images", rank: 16, run_preprocess: true, compile: false }
    await trainingApi.mossPreflight(config)
    expect(fetch).toHaveBeenLastCalledWith("/api/engines/moss/preflight", expect.objectContaining({ method: "POST", body: JSON.stringify(config) }))
    await mossApi.dryRun(config)
    expect(fetch).toHaveBeenLastCalledWith("/api/engines/moss/dry-run", expect.objectContaining({ method: "POST", body: JSON.stringify(config) }))
  })

  it("propagates server failures", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(response({}, "fail"))
    await expect(enginesApi.install("moss")).rejects.toThrow("mock failure")
  })
})
