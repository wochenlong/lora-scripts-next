// @vitest-environment jsdom
import { describe, expect, it, vi } from "vitest"
import { HostPluginBridge, type BridgeFrameTarget, type BridgeMessageChannel, type BridgeMessagePort } from "./pluginBridge"
import {
  BRIDGE_REQUEST_TYPES,
  PLUGIN_BRIDGE_PROTOCOL,
  parseBridgeRequestEnvelope,
  type BridgeRequestEnvelope,
  type BridgeResponseEnvelope,
} from "./pluginBridgeSchemas"

class FakePort implements BridgeMessagePort {
  onmessage: ((event: MessageEvent<unknown>) => void) | null = null
  readonly sent: unknown[] = []
  started = false
  closed = false

  postMessage(message: unknown) {
    this.sent.push(message)
  }

  start() {
    this.started = true
  }

  close() {
    this.closed = true
  }

  receive(message: unknown) {
    this.onmessage?.({ data: message } as MessageEvent<unknown>)
  }
}

class FakeFrame implements BridgeFrameTarget {
  readonly sent: Array<{ message: unknown; targetOrigin: string; transfer?: Transferable[] }> = []

  postMessage(message: unknown, targetOrigin: string, transfer?: Transferable[]) {
    this.sent.push({ message, targetOrigin, transfer })
  }
}

function ready(pluginId = "sample-plugin", protocolVersion: string = PLUGIN_BRIDGE_PROTOCOL) {
  return { type: "READY", pluginId, protocolVersion }
}

function request(overrides: Partial<BridgeRequestEnvelope> = {}): BridgeRequestEnvelope {
  return {
    protocol: PLUGIN_BRIDGE_PROTOCOL,
    pluginId: "sample-plugin",
    instanceId: "instance-1",
    seq: 1,
    requestId: "request-1",
    type: "theme.get",
    payload: {},
    ...overrides,
  }
}

function buildHarness(capabilities: BridgeRequestEnvelope["type"][] = ["theme.get"]) {
  const frame = new FakeFrame()
  const channels: Array<{ port1: FakePort; port2: FakePort }> = []
  const handler = vi.fn(async (input: BridgeRequestEnvelope) => ({ handled: input.type }))
  const bridge = new HostPluginBridge({
    pluginId: "sample-plugin",
    instanceId: "instance-1",
    frameTarget: frame,
    grantedCapabilities: capabilities,
    handleRequest: handler,
    nonceFactory: () => "a".repeat(64),
    requestIdFactory: () => `response-${handler.mock.calls.length}`,
    channelFactory: () => {
      const channel = { port1: new FakePort(), port2: new FakePort() }
      channels.push(channel)
      return channel as BridgeMessageChannel
    },
    locale: () => "en-US",
    themeTokens: () => ({ "--bg": "#fff" }),
    activeSession: () => "session-1",
  })
  bridge.start()
  return { bridge, frame, channels, handler }
}

function windowMessage(source: BridgeFrameTarget, data: unknown) {
  return { source, data } as unknown as MessageEvent<unknown>
}

function connect(harness: ReturnType<typeof buildHarness>) {
  harness.bridge.acceptWindowMessage(windowMessage(harness.frame, ready()))
  const port = harness.channels.at(-1)!.port1
  port.receive({
    type: "HELLO",
    pluginId: "sample-plugin",
    instanceId: "instance-1",
    protocolVersion: PLUGIN_BRIDGE_PROTOCOL,
    nonce: "a".repeat(64),
  })
  return port
}

async function settle() {
  await Promise.resolve()
  await Promise.resolve()
}

describe("HostPluginBridge handshake", () => {
  it("accepts READY only from the exact iframe source and transfers one port", () => {
    const harness = buildHarness()
    harness.bridge.acceptWindowMessage(windowMessage(new FakeFrame(), ready()))
    expect(harness.channels).toHaveLength(0)

    harness.bridge.acceptWindowMessage(windowMessage(harness.frame, ready()))
    expect(harness.channels).toHaveLength(1)
    expect(harness.channels[0].port1.started).toBe(true)
    expect(harness.frame.sent[0].targetOrigin).toBe("*")
    expect(harness.frame.sent[0].message).toMatchObject({
      type: "CHALLENGE",
      pluginId: "sample-plugin",
      instanceId: "instance-1",
      nonce: "a".repeat(64),
    })
    expect(harness.frame.sent[0].transfer).toHaveLength(1)
    harness.bridge.dispose()
  })

  it("rejects wrong plugin, protocol, nonce, and instance identity", () => {
    const harness = buildHarness()
    harness.bridge.acceptWindowMessage(windowMessage(harness.frame, ready("other-plugin")))
    harness.bridge.acceptWindowMessage(windowMessage(harness.frame, ready("sample-plugin", "bridge/0")))
    expect(harness.channels).toHaveLength(0)

    harness.bridge.acceptWindowMessage(windowMessage(harness.frame, ready()))
    const port = harness.channels[0].port1
    port.receive({
      type: "HELLO",
      pluginId: "sample-plugin",
      instanceId: "wrong-instance",
      protocolVersion: PLUGIN_BRIDGE_PROTOCOL,
      nonce: "wrong",
    })
    expect(port.closed).toBe(true)
    expect(harness.bridge.isConnected).toBe(false)
    harness.bridge.dispose()
  })

  it("welcomes a valid opaque-origin handshake without inspecting event.origin", () => {
    const harness = buildHarness()
    const port = connect(harness)
    expect(harness.bridge.isConnected).toBe(true)
    expect(port.sent[0]).toEqual({
      type: "WELCOME",
      protocolVersion: PLUGIN_BRIDGE_PROTOCOL,
      pluginId: "sample-plugin",
      instanceId: "instance-1",
      grantedCapabilities: ["theme.get"],
      themeTokens: { "--bg": "#fff" },
      locale: "en-US",
      activeSession: "session-1",
    })
    harness.bridge.dispose()
  })
})

describe("HostPluginBridge request validation", () => {
  it("dispatches a schema-valid, granted request and returns a correlated response", async () => {
    const harness = buildHarness()
    const port = connect(harness)
    port.receive(request())
    await settle()

    expect(harness.handler).toHaveBeenCalledTimes(1)
    expect(port.sent[1]).toMatchObject({
      type: "RESPONSE",
      ok: true,
      replyTo: "request-1",
      data: { handled: "theme.get" },
    })
    harness.bridge.dispose()
  })

  it("forwards only correlated session events over the connected MessagePort", () => {
    const harness = buildHarness()
    const port = connect(harness)
    expect(
      harness.bridge.postEvent({ eventId: "event-1", sessionId: "session-1", runId: 4, type: "prompt_done" }),
    ).toBe(true)
    expect(port.sent.at(-1)).toMatchObject({
      type: "EVENT",
      eventId: "event-1",
      sessionId: "session-1",
      runId: 4,
      data: { type: "prompt_done" },
    })
    expect(harness.bridge.postEvent({ connected: true })).toBe(false)
    harness.bridge.reset()
    expect(
      harness.bridge.postEvent({ eventId: "event-2", sessionId: "session-1", runId: 4, type: "agent_settled" }),
    ).toBe(false)
    harness.bridge.dispose()
  })

  it("rejects duplicate sequence and requestId without repeating the side effect", async () => {
    const harness = buildHarness()
    const port = connect(harness)
    port.receive(request())
    await settle()
    port.receive(request({ seq: 2 }))
    await settle()

    expect(harness.handler).toHaveBeenCalledTimes(1)
    expect(port.sent.at(-1)).toMatchObject({
      ok: false,
      replyTo: "request-1",
      error: { code: "BRIDGE_REPLAY_REJECTED" },
    })
    harness.bridge.dispose()
  })

  it("rejects stale sequence, unknown schema, extra fields, and denied capability", async () => {
    const harness = buildHarness(["theme.get"])
    const port = connect(harness)
    port.receive(request({ seq: 2 }))
    await settle()
    port.receive(request({ seq: 1, requestId: "request-stale" }))
    port.receive({ ...request({ seq: 3, requestId: "request-unknown" }), type: "unknown.method" })
    port.receive({ ...request({ seq: 4, requestId: "request-extra" }), extra: true })
    port.receive(request({ seq: 5, requestId: "request-denied", type: "locale.get" }))
    await settle()

    const errors = port.sent.slice(2) as BridgeResponseEnvelope[]
    expect(errors.map((item) => item.error?.code)).toEqual([
      "BRIDGE_REPLAY_REJECTED",
      "BRIDGE_SCHEMA_UNSUPPORTED",
      "BRIDGE_SCHEMA_UNSUPPORTED",
      "BRIDGE_CAPABILITY_DENIED",
    ])
    expect(harness.handler).toHaveBeenCalledTimes(1)
    harness.bridge.dispose()
  })

  it("enforces the frozen payload schema", async () => {
    const harness = buildHarness(["artifact.open"])
    const port = connect(harness)
    port.receive(request({ type: "artifact.open", payload: { artifactId: "artifact-1", path: "C:/secret" } }))
    await settle()
    expect(harness.handler).not.toHaveBeenCalled()
    expect(port.sent.at(-1)).toMatchObject({ error: { code: "BRIDGE_SCHEMA_UNSUPPORTED" } })
    harness.bridge.dispose()
  })

  it("binds provider keys to an exact profile endpoint and model", async () => {
    const harness = buildHarness(["provider.saveKey"])
    const port = connect(harness)
    port.receive(
      request({
        type: "provider.saveKey",
        payload: { profileId: "profile-1", endpoint: "https://api.example/v1", modelId: "model-1", key: "secret" },
      }),
    )
    await settle()
    expect(harness.handler).toHaveBeenCalledTimes(1)

    port.receive(
      request({
        seq: 2,
        requestId: "request-2",
        type: "provider.saveKey",
        payload: { profileId: "profile-1", key: "secret" },
      }),
    )
    await settle()
    expect(harness.handler).toHaveBeenCalledTimes(1)
    expect(port.sent.at(-1)).toMatchObject({ error: { code: "BRIDGE_SCHEMA_UNSUPPORTED" } })
    harness.bridge.dispose()
  })

  it("supports the complete approved session transport schema", async () => {
    const capabilities: BridgeRequestEnvelope["type"][] = [
      "session.getHistory",
      "session.getThinking",
      "session.compact",
      "session.setModel",
      "session.setThinkingLevel",
      "session.recallQueue",
    ]
    const harness = buildHarness(capabilities)
    const port = connect(harness)
    const requests: Array<Partial<BridgeRequestEnvelope>> = [
      { type: "session.getHistory", payload: { sessionId: "s1", cursor: "c1", limit: 50 } },
      { type: "session.getThinking", payload: { sessionId: "s1", entryId: "e1", blockIndex: 0 } },
      { type: "session.compact", payload: { sessionId: "s1", instructions: "Keep decisions" } },
      { type: "session.setModel", payload: { sessionId: "s1", model: { profileId: "p1", modelId: "m1" } } },
      { type: "session.setThinkingLevel", payload: { sessionId: "s1", level: "high" } },
      { type: "session.recallQueue", payload: { sessionId: "s1" } },
    ]
    requests.forEach((item, index) => port.receive(request({ ...item, seq: index + 1, requestId: `session-${index + 1}` })))
    await settle()
    expect(harness.handler).toHaveBeenCalledTimes(requests.length)
    harness.bridge.dispose()
  })

  it("accepts one canonical payload for every approved request type", () => {
    const payloads: Record<BridgeRequestEnvelope["type"], Record<string, unknown>> = {
      "session.list": {},
      "session.create": {
        name: "Audit session",
        model: { profileId: "deepseek", modelId: "deepseek-v4-flash" },
        thinkingLevel: "high",
      },
      "session.rename": { sessionId: "s1", name: "Renamed" },
      "session.delete": { sessionId: "s1" },
      "session.getState": { sessionId: "s1" },
      "session.getHistory": {
        sessionId: "s1",
        cursor: "c1",
        limit: 50,
        deferThinking: true,
        deferMedia: true,
      },
      "session.getThinking": { sessionId: "s1", entryId: "e1", blockIndex: 0 },
      "session.prompt": {
        sessionId: "s1",
        input: {
          text: "Review this image",
          images: [{ data: "base64", mimeType: "image/png", name: "sample.png" }],
          streamingBehavior: "followUp",
          clientSubmissionId: "submission-1",
        },
      },
      "session.cancel": { sessionId: "s1" },
      "session.compact": { sessionId: "s1", instructions: "Keep decisions" },
      "session.setModel": { sessionId: "s1", model: { profileId: "qwen", modelId: "Qwen/Qwen3.6-27B" } },
      "session.setThinkingLevel": { sessionId: "s1", level: "medium" },
      "session.recallQueue": { sessionId: "s1" },
      "session.subscribe": { sessionId: "s1", cursor: "event-4" },
      "provider.list": {},
      "provider.status": { profileId: "deepseek" },
      "provider.saveKey": {
        profileId: "deepseek",
        endpoint: "https://api.deepseek.com/v1/chat/completions",
        modelId: "deepseek-v4-flash",
        key: "test-key",
      },
      "provider.removeKey": { profileId: "deepseek" },
      "provider.test": { profileId: "deepseek" },
      "resource.pick": { kinds: ["dataset", "training-config"] },
      "resource.getSummary": { resourceId: "dataset-1" },
      "artifact.open": { artifactId: "artifact-1", title: "Config", kind: "training-config" },
      "artifact.download": { artifactId: "artifact-1", title: "Config", kind: "training-config" },
      "confirmation.request": {
        toolCallId: "tool-1",
      },
      "confirmation.getResult": { ticketId: "ticket-1" },
      "navigation.openExternal": { url: "https://example.com/reference" },
      "navigation.openPluginRoute": { route: "/plugins/sample-plugin/artifacts/artifact-1" },
      "theme.get": {},
      "locale.get": {},
      "context.get": {},
    }

    expect(Object.keys(payloads).sort()).toEqual([...BRIDGE_REQUEST_TYPES].sort())
    BRIDGE_REQUEST_TYPES.forEach((type, index) => {
      expect(
        parseBridgeRequestEnvelope(request({ type, payload: payloads[type], seq: index + 1, requestId: `canonical-${index}` })),
      ).toMatchObject({ ok: true })
    })
  })

  it("rejects legacy or incomplete nested DTOs", () => {
    const invalidRequests: Array<Partial<BridgeRequestEnvelope>> = [
      { type: "session.create", payload: { model: { provider: "deepseek", modelId: "m1" } } },
      { type: "session.getHistory", payload: { sessionId: "s1", deferThinking: "yes" } },
      { type: "session.prompt", payload: { sessionId: "s1", input: { text: "missing submission id" } } },
      { type: "session.setThinkingLevel", payload: { sessionId: "s1", level: "unbounded" } },
      { type: "provider.status", payload: {} },
      { type: "resource.pick", payload: { kind: "dataset" } },
      { type: "artifact.open", payload: { artifactId: "artifact-1" } },
      { type: "confirmation.request", payload: { action: "caption.commit", title: "Untrusted", summary: "Untrusted" } },
    ]

    invalidRequests.forEach((input, index) => {
      expect(parseBridgeRequestEnvelope(request({ ...input, seq: index + 1, requestId: `invalid-${index}` }))).toMatchObject({
        ok: false,
        code: "BRIDGE_SCHEMA_UNSUPPORTED",
      })
    })
  })

  it("does not expose handler error details to the plugin frame", async () => {
    const harness = buildHarness()
    harness.handler.mockRejectedValueOnce(new Error("C:/Users/name/auth.json contained sk-sensitive"))
    const port = connect(harness)
    port.receive(request())
    await settle()
    expect(port.sent.at(-1)).toMatchObject({
      ok: false,
      error: { code: "BRIDGE_REQUEST_FAILED", message: "The host could not complete this request." },
    })
    expect(JSON.stringify(port.sent.at(-1))).not.toContain("auth.json")
    expect(JSON.stringify(port.sent.at(-1))).not.toContain("sk-sensitive")
    harness.bridge.dispose()
  })
})

describe("HostPluginBridge lifecycle", () => {
  it("closes the old port on a fresh READY and ignores late messages from it", async () => {
    const harness = buildHarness()
    const oldPort = connect(harness)
    harness.bridge.acceptWindowMessage(windowMessage(harness.frame, ready()))
    expect(oldPort.closed).toBe(true)
    expect(harness.channels).toHaveLength(2)

    oldPort.receive(request())
    await settle()
    expect(harness.handler).not.toHaveBeenCalled()
    harness.bridge.dispose()
  })

  it("clears the port and global listener on dispose", () => {
    const harness = buildHarness()
    const port = connect(harness)
    harness.bridge.dispose()
    expect(port.closed).toBe(true)
    expect(harness.bridge.isConnected).toBe(false)
    expect(harness.bridge.isStarted).toBe(false)

    harness.bridge.acceptWindowMessage(windowMessage(harness.frame, ready()))
    expect(harness.channels).toHaveLength(1)
  })

  it("drops an async response from a connection that was replaced", async () => {
    let releaseRequest: (() => void) | undefined
    const harness = buildHarness()
    harness.handler.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          releaseRequest = () => resolve({ handled: "theme.get" })
        }),
    )
    const oldPort = connect(harness)
    oldPort.receive(request())
    await settle()

    harness.bridge.acceptWindowMessage(windowMessage(harness.frame, ready()))
    const newPort = harness.channels[1].port1
    newPort.receive({
      type: "HELLO",
      pluginId: "sample-plugin",
      instanceId: "instance-1",
      protocolVersion: PLUGIN_BRIDGE_PROTOCOL,
      nonce: "a".repeat(64),
    })
    releaseRequest?.()
    await settle()

    expect(oldPort.sent).toHaveLength(1)
    expect(newPort.sent).toHaveLength(1)
    harness.bridge.dispose()
  })
})
