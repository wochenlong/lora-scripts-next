// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest"
import { kohakuMossApi } from "./kohakuMoss"
import { enginesApi } from "./engines"
import { trainingApi } from "./training"

function response(data: unknown, status = "success") {
  return new Response(JSON.stringify({ status, data, message: status === "fail" ? "mock failure" : undefined }))
}
afterEach(() => vi.restoreAllMocks())

describe("MOSS engine API", () => {
  it("normalizes a native runtime status for the shared settings catalog", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(response({ state: "ready", feature_enabled: true,
      runtime: { environment_path: "/runtime/moss", python: "/runtime/moss/python" }, facts: { audit: { ok: true } } }))
    expect(await enginesApi.status("kohaku-moss")).toMatchObject({ id: "kohaku-moss", state: "ready", featureEnabled: true,
      runtime: { environmentPath: "/runtime/moss", python: "/runtime/moss/python" }, facts: { audit: { ok: true } } })
    expect(fetch).toHaveBeenCalledWith("/api/engines/kohaku-moss/status", expect.anything())
  })

  it("maps install and repair responses while leaving download-source resolution to the server", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(async () => response({ task_id: "moss-install", log_stream: "/api/log", progress_stream: "/api/progress",
      status: { state: "installing", feature_enabled: true } }))
    for (const action of ["install", "repair"] as const) {
      expect(await enginesApi[action]("kohaku-moss")).toMatchObject({ taskId: "moss-install", logStream: "/api/log", progressStream: "/api/progress", status: { id: "kohaku-moss", state: "installing" } })
      expect(fetch).toHaveBeenLastCalledWith(`/api/engines/kohaku-moss/${action}`, expect.objectContaining({ method: "POST", body: JSON.stringify({ dry_run: false }) }))
    }
  })

  it("supports already-ready and uninstall responses without issuing training requests", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(response({ already_ready: true, status: { state: "ready", feature_enabled: true } })).mockResolvedValueOnce(response({}))
    expect(await enginesApi.install("kohaku-moss")).toMatchObject({ alreadyReady: true, status: { id: "kohaku-moss", state: "ready" } })
    expect(await enginesApi.uninstall("kohaku-moss")).toEqual({ id: "kohaku-moss", state: "not_installed", featureEnabled: true })
    expect(fetch).toHaveBeenLastCalledWith("/api/engines/kohaku-moss/uninstall", expect.objectContaining({ method: "POST", body: "{}" }))
  })

  it("submits native configs unchanged to preflight and dry-run", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockImplementation(async () => response({ ok: true, warnings: [] }))
    const config = { model_train_type: "kohaku-moss-image-lora", pretrained_model_name_or_path: "/models", train_data_dir: "/images", network_dim: 16, compile_mode: "off" }
    await trainingApi.kohakuMossPreflight(config)
    expect(fetch).toHaveBeenLastCalledWith("/api/engines/kohaku-moss/preflight", expect.objectContaining({ method: "POST", body: JSON.stringify(config) }))
    await kohakuMossApi.dryRun(config)
    expect(fetch).toHaveBeenLastCalledWith("/api/engines/kohaku-moss/dry-run", expect.objectContaining({ method: "POST", body: JSON.stringify(config) }))
  })

  it("propagates server failures", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(response({}, "fail"))
    await expect(enginesApi.install("kohaku-moss")).rejects.toThrow("mock failure")
  })
})
