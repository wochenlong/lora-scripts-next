// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import {
  isSafePluginHostUrl,
  isSafePluginServerUiUrl,
  isSafePluginUiUrl,
  isValidArtifactId,
  isValidPluginId,
  isPluginConfirmationProjection,
  pluginsApi,
  resetPluginHostAuthorityForTests,
  type MarketplaceEntry,
} from "./plugins"

describe("plugin host URL policy", () => {
  it("accepts only same-origin plugin-host API paths", () => {
    expect(isSafePluginHostUrl("/api/plugin-host/ui/sample/panel.html")).toBe(true)
    expect(isSafePluginHostUrl("/api/plugins/sample/panel.html")).toBe(false)
    expect(isSafePluginHostUrl("https://provider.example/panel.html")).toBe(false)
    expect(isSafePluginHostUrl("//provider.example/panel.html")).toBe(false)
    expect(isSafePluginHostUrl("javascript:alert(1)")).toBe(false)
    expect(isSafePluginHostUrl("/api/plugin-host/ui/%2e%2e/admin")).toBe(false)
    expect(isSafePluginHostUrl("/api/plugin-host/ui/sample\\..\\admin")).toBe(false)
  })

  it("binds iframe entry URLs to the owning plugin namespace", () => {
    expect(isSafePluginUiUrl("/api/plugin-host/ui/sample-plugin/0.1.0/index.html", "sample-plugin")).toBe(true)
    expect(isSafePluginUiUrl("/api/plugin-host/ui/other-plugin/0.1.0/index.html", "sample-plugin")).toBe(false)
    expect(isSafePluginUiUrl("/api/plugin-host/extensions", "sample-plugin")).toBe(false)
  })

  it("accepts only explicit 127.0.0.1 loopback root URLs for server-mode UI", () => {
    expect(isSafePluginServerUiUrl("http://127.0.0.1:4518")).toBe(true)
    expect(isSafePluginServerUiUrl("http://127.0.0.1:1")).toBe(true)
    expect(isSafePluginServerUiUrl("http://127.0.0.1:65535")).toBe(true)
    // Hostname, scheme, credentials, and path variants must not pass.
    expect(isSafePluginServerUiUrl("http://localhost:4518")).toBe(false)
    expect(isSafePluginServerUiUrl("http://127.0.0.1")).toBe(false)
    expect(isSafePluginServerUiUrl("https://127.0.0.1:4518")).toBe(false)
    expect(isSafePluginServerUiUrl("http://127.0.0.2:4518")).toBe(false)
    expect(isSafePluginServerUiUrl("http://10.0.0.1:4518")).toBe(false)
    expect(isSafePluginServerUiUrl("http://user:pass@127.0.0.1:4518")).toBe(false)
    // Root document: the trailing-slash spelling of the same root passes.
    expect(isSafePluginServerUiUrl("http://127.0.0.1:4518/")).toBe(true)
    expect(isSafePluginServerUiUrl("http://127.0.0.1:4518/admin")).toBe(false)
    // Only a single `cwd` query param (an absolute path) is permitted; any
    // other param, a relative/traversal path, or extra params must not pass.
    expect(isSafePluginServerUiUrl("http://127.0.0.1:4518?x=1")).toBe(false)
    expect(isSafePluginServerUiUrl("http://127.0.0.1:4518?cwd=C%3A%5Cwork%5Cproj")).toBe(true)
    expect(isSafePluginServerUiUrl("http://127.0.0.1:4518?cwd=%2Fhome%2Fuser%2Fproj")).toBe(true)
    expect(isSafePluginServerUiUrl("http://127.0.0.1:4518?cwd=relative%5Cdir")).toBe(false)
    expect(isSafePluginServerUiUrl("http://127.0.0.1:4518?cwd=C%3A%5C..%5C..")).toBe(false)
    expect(isSafePluginServerUiUrl("http://127.0.0.1:4518?cwd=C%3A%5Cproj&x=1")).toBe(false)
    expect(isSafePluginServerUiUrl("http://127.0.0.1:99999")).toBe(false)
    expect(isSafePluginServerUiUrl("javascript:alert(1)")).toBe(false)
    expect(isSafePluginServerUiUrl("")).toBe(false)
    expect(isSafePluginServerUiUrl(undefined)).toBe(false)
  })

  it("accepts stable logical plugin ids and rejects path-like ids", () => {
    expect(isValidPluginId("sample-plugin.v1")).toBe(true)
    expect(isValidPluginId("../sample-plugin")).toBe(false)
    expect(isValidPluginId("sample/plugin")).toBe(false)
    expect(isValidArtifactId("training-config:draft-003")).toBe(true)
    expect(isValidArtifactId("../draft-003")).toBe(false)
  })
})

describe("plugin capability broker client", () => {
  const fetchMock = vi.fn<typeof fetch>()

  beforeEach(() => {
    resetPluginHostAuthorityForTests()
    fetchMock.mockReset()
    vi.stubGlobal("fetch", fetchMock)
    localStorage.clear()
    sessionStorage.clear()
  })

  afterEach(() => vi.unstubAllGlobals())

  it("keeps the run token in memory and sends only the typed broker envelope", async () => {
    fetchMock
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            status: "success",
            data: { runToken: "memory-only-token-value", header: "X-NextTrainer-Run-Token" },
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ok: true, requestId: "00000000-0000-4000-8000-000000000001", data: { id: "s1" } }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )

    const result = await pluginsApi.requestCapability(
      "sample-plugin",
      { type: "session.getState", payload: { sessionId: "s1" } },
      () => "00000000-0000-4000-8000-000000000001",
    )

    expect(result).toEqual({ id: "s1" })
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/plugin-host/bootstrap",
      expect.objectContaining({ method: "POST", body: "{}" }),
    )
    const brokerCall = fetchMock.mock.calls[1]
    expect(brokerCall[0]).toBe("/api/plugin-host/extensions/sample-plugin/requests")
    expect(brokerCall[1]?.headers).toEqual({
      "Content-Type": "application/json",
      "X-NextTrainer-Run-Token": "memory-only-token-value",
    })
    expect(JSON.parse(String(brokerCall[1]?.body))).toEqual({
      requestId: "00000000-0000-4000-8000-000000000001",
      method: "session.getState",
      params: { sessionId: "s1" },
    })
    expect(localStorage.length).toBe(0)
    expect(sessionStorage.length).toBe(0)
  })

  it("sends only approvedPermissions in the install body (backend contract forbids extra fields)", async () => {
    const entry: MarketplaceEntry = {
      id: "sample-plugin",
      name: "Sample",
      publisher_id: "publisher",
      description: "",
      icon: null,
      latest_version: "1.0.0",
      channel: "stable",
      host_compatibility: ">=2.9.2 <4.0.0",
      platforms: ["win32-x64"],
      package_size: 1,
      permissions_summary: ["training-config"],
      license: "MIT",
      release_notes_url: null,
      package_url: "https://market.example/sample.zip",
      sha256: "a".repeat(64),
      signature: "b".repeat(64),
      signing_key_id: "test-key",
      published_at: "2026-08-28T00:00:00Z",
    }
    fetchMock
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ status: "success", data: { runToken: "install-authority-token", header: "X-NextTrainer-Run-Token" } }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            status: "success",
            data: {
              operationId: "op-123",
              pluginId: "sample-plugin",
              version: "1.0.0",
              state: "running",
              phase: "acquiring",
              progress: { current: 0, total: 0, percent: null },
              errorCode: null,
              errorMessage: null,
              status: null,
              startedAt: "2026-08-29T00:00:00Z",
              finishedAt: null,
            },
          }),
          { status: 202, headers: { "Content-Type": "application/json" } },
        ),
      )

    const operation = await pluginsApi.installMarketplacePlugin(entry, ["training-config"])

    // Install is now asynchronous: the endpoint answers 202 with an operation
    // snapshot instead of the final plugin status.
    expect(operation.operationId).toBe("op-123")
    expect(operation.state).toBe("running")
    const installCall = fetchMock.mock.calls[1]
    expect(installCall[0]).toBe("/api/marketplace/plugins/sample-plugin/install")
    const body = JSON.parse(String(installCall[1]?.body))
    expect(body).toEqual({ approvedPermissions: ["training-config"] })
    expect("entry" in body).toBe(false)
  })

  it("reads, cancels, and streams install operations", async () => {
    const snapshot = {
      operationId: "a1b2c3d4e5f607182930415263748596",
      pluginId: "sample-plugin",
      version: "1.0.0",
      state: "succeeded" as const,
      phase: "done" as const,
      progress: { current: 10, total: 10, percent: 100 },
      errorCode: null,
      errorMessage: null,
      status: {
        id: "sample-plugin",
        state: "installed" as const,
        active_version: "1.0.0",
        previous_version: null,
        enabled: false,
        installed_versions: ["1.0.0"],
        reason: "",
        runtime_state: null,
        runtime_pid: null,
      },
      startedAt: "2026-08-29T00:00:00Z",
      finishedAt: "2026-08-29T00:00:05Z",
    }
    const json = (data: unknown, status = 200) =>
      new Response(JSON.stringify({ status: "success", data }), { status, headers: { "Content-Type": "application/json" } })

    fetchMock
      .mockResolvedValueOnce(
        json({ runToken: "ops-authority-token", header: "X-NextTrainer-Run-Token" }),
      )
      .mockResolvedValueOnce(json(snapshot))
      .mockResolvedValueOnce(json(snapshot))
      .mockResolvedValueOnce(
        new Response(
          [
            'event: connected',
            'data: {"status": "success", "data": {"connected": true}}',
            "",
            "event: progress",
            `data: ${JSON.stringify({ status: "success", data: { ...snapshot, state: "running", phase: "acquiring" } })}`,
            "",
            "event: done",
            `data: ${JSON.stringify({ status: "success", data: snapshot })}`,
            "",
          ].join("\n"),
          { status: 200, headers: { "Content-Type": "text/event-stream" } },
        ),
      )

    const got = await pluginsApi.getInstallOperation("sample-plugin", snapshot.operationId)
    expect(got.operationId).toBe(snapshot.operationId)
    const cancelled = await pluginsApi.cancelInstallOperation("sample-plugin", snapshot.operationId)
    expect(cancelled.state).toBe("succeeded")
    const cancelCall = fetchMock.mock.calls[2]
    expect(cancelCall[0]).toBe(`/api/marketplace/plugins/sample-plugin/operations/${snapshot.operationId}`)
    expect(cancelCall[1]?.method).toBe("DELETE")
    expect(String(cancelCall[1]?.body)).toBe("{}")

    const seen: string[] = []
    await pluginsApi.streamInstallOperation("sample-plugin", snapshot.operationId, (op) => {
      seen.push(`${op.state}:${op.phase}`)
    })
    expect(seen).toEqual(["running:acquiring", "succeeded:done"])
    const streamCall = fetchMock.mock.calls[3]
    expect(streamCall[0]).toBe(`/api/marketplace/plugins/sample-plugin/operations/${snapshot.operationId}/stream`)
  })

  it("refreshes stale authority once before a broker mutation is accepted", async () => {
    fetchMock
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ status: "success", data: { runToken: "old-authority-token", header: "X-NextTrainer-Run-Token" } }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(new Response("{}", { status: 403, headers: { "Content-Type": "application/json" } }))
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ status: "success", data: { runToken: "fresh-authority-token", header: "X-NextTrainer-Run-Token" } }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ok: true, requestId: "00000000-0000-4000-8000-000000000002", data: {} }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )

    await pluginsApi.requestCapability(
      "sample-plugin",
      { type: "session.cancel", payload: { sessionId: "s1" } },
      () => "00000000-0000-4000-8000-000000000002",
    )
    expect(fetchMock).toHaveBeenCalledTimes(4)
    expect(fetchMock.mock.calls[3][1]?.headers).toMatchObject({ "X-NextTrainer-Run-Token": "fresh-authority-token" })
  })

  it("parses split SSE frames without exposing the token to the callback", async () => {
    const encoder = new TextEncoder()
    const stream = new ReadableStream({
      start(controller) {
        controller.enqueue(encoder.encode('event: connected\ndata: {"ok":true,"requestId":"00000000-0000-4000-8000-000000000003","data":{"connected":true}}\n\n'))
        controller.enqueue(encoder.encode('event: data\ndata: {"ok":true,"requestId":"00000000-0000-4000-8000-000000000003","data":{"eventId":"e1",'))
        controller.enqueue(encoder.encode('"sessionId":"s1","runId":1,"type":"prompt_done"}}\n\n'))
        controller.close()
      },
    })
    fetchMock
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ status: "success", data: { runToken: "stream-token-value", header: "X-NextTrainer-Run-Token" } }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(new Response(stream, { status: 200, headers: { "Content-Type": "text/event-stream" } }))
    const events: unknown[] = []

    await pluginsApi.streamCapability(
      "sample-plugin",
      { type: "session.subscribe", payload: { sessionId: "s1" } },
      (event) => events.push(event),
      undefined,
      () => "00000000-0000-4000-8000-000000000003",
    )

    expect(events).toEqual([
      { connected: true },
      { eventId: "e1", sessionId: "s1", runId: 1, type: "prompt_done" },
    ])
    expect(JSON.stringify(events)).not.toContain("stream-token-value")
  })

  it("resolves a host confirmation through the authority-protected endpoint", async () => {
    const projection = {
      ticketId: "ticket-1",
      pluginId: "sample-plugin",
      toolCallId: "tool-1",
      state: "approved",
      permission: "caption-commit",
      action: "caption.commit",
      title: "Apply captions",
      summary: "Update four files",
      artifactIds: ["changeset-1"],
      details: { files: 4 },
      createdAt: "2026-08-21T00:00:00Z",
      expiresAt: "2026-08-21T00:05:00Z",
      resolvedAt: "2026-08-21T00:01:00Z",
    }
    fetchMock
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ status: "success", data: { runToken: "confirmation-token", header: "X-NextTrainer-Run-Token" } }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ status: "success", data: projection }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )

    await expect(pluginsApi.resolveConfirmation("ticket-1", "approved")).resolves.toEqual(projection)
    expect(fetchMock.mock.calls[1][0]).toBe("/api/plugin-host/confirmations/ticket-1/resolve")
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toEqual({ decision: "approved" })
    expect(fetchMock.mock.calls[1][1]?.headers).toMatchObject({ "X-NextTrainer-Run-Token": "confirmation-token" })
  })

  it("rejects malformed or cross-plugin confirmation projections", () => {
    const value = {
      ticketId: "ticket-1",
      pluginId: "other-plugin",
      toolCallId: "tool-1",
      state: "presented",
      permission: "caption-commit",
      action: "caption.commit",
      title: "Apply captions",
      summary: "Update four files",
      details: {},
      artifactIds: [],
      createdAt: "2026-08-21T00:00:00Z",
      expiresAt: "2026-08-21T00:05:00Z",
      resolvedAt: null,
    }
    expect(isPluginConfirmationProjection(value, "sample-plugin")).toBe(false)
    expect(isPluginConfirmationProjection({ ...value, pluginId: "sample-plugin" }, "sample-plugin")).toBe(true)
  })

  it("restores only valid Host pending confirmation projections", async () => {
    const valid = {
      ticketId: "ticket-1",
      pluginId: "sample-plugin",
      toolCallId: "tool-1",
      state: "presented",
      permission: "caption-commit",
      action: "caption.commit",
      title: "Apply captions",
      summary: "Update four files",
      details: { files: 4 },
      artifactIds: ["changeset-1"],
      createdAt: "2026-08-21T00:00:00Z",
      expiresAt: "2026-08-21T00:05:00Z",
      resolvedAt: null,
    }
    fetchMock
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ status: "success", data: { runToken: "pending-list-token", header: "X-NextTrainer-Run-Token" } }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ status: "success", data: { confirmations: [valid, { ticketId: "../bad" }] } }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )

    await expect(pluginsApi.listPendingConfirmations()).resolves.toEqual([valid])
    expect(fetchMock.mock.calls[1][0]).toBe("/api/plugin-host/confirmations/pending")
    expect(fetchMock.mock.calls[1][1]?.headers).toMatchObject({ "X-NextTrainer-Run-Token": "pending-list-token" })
  })

  it("surfaces the host error code and message from a FastAPI detail envelope", async () => {
    // Structured route failures (e.g. the install-conflict HTTPException)
    // arrive as {detail:{code,message}} with a non-2xx status. The client
    // must forward the real reason instead of the generic "request failed"
    // text that hid why the marketplace button "did nothing".
    fetchMock
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ status: "success", data: { runToken: "authority-token-value", header: "X-NextTrainer-Run-Token" } }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ detail: { code: "MARKETPLACE_INSTALL_IN_PROGRESS", message: "An install is already running for this plugin." } }),
          { status: 409, headers: { "Content-Type": "application/json" } },
        ),
      )

    await expect(pluginsApi.uninstallMarketplacePlugin("sample-plugin")).rejects.toMatchObject({
      code: "MARKETPLACE_INSTALL_IN_PROGRESS",
      message: "An install is already running for this plugin.",
    })
  })

  it("falls back to a generic error when the host failure envelope is unstructured", async () => {
    fetchMock
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ status: "success", data: { runToken: "authority-token-value", header: "X-NextTrainer-Run-Token" } }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(new Response("gateway boom", { status: 502 }))

    await expect(pluginsApi.uninstallMarketplacePlugin("sample-plugin")).rejects.toMatchObject({
      code: "PLUGIN_HOST_RESPONSE_INVALID",
    })
  })
})
