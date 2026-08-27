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
    // Hostname, scheme, credentials, path, and query variants must not pass.
    expect(isSafePluginServerUiUrl("http://localhost:4518")).toBe(false)
    expect(isSafePluginServerUiUrl("http://127.0.0.1")).toBe(false)
    expect(isSafePluginServerUiUrl("https://127.0.0.1:4518")).toBe(false)
    expect(isSafePluginServerUiUrl("http://127.0.0.2:4518")).toBe(false)
    expect(isSafePluginServerUiUrl("http://10.0.0.1:4518")).toBe(false)
    expect(isSafePluginServerUiUrl("http://user:pass@127.0.0.1:4518")).toBe(false)
    // Root document: the trailing-slash spelling of the same root passes.
    expect(isSafePluginServerUiUrl("http://127.0.0.1:4518/")).toBe(true)
    expect(isSafePluginServerUiUrl("http://127.0.0.1:4518/admin")).toBe(false)
    expect(isSafePluginServerUiUrl("http://127.0.0.1:4518?x=1")).toBe(false)
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
})
