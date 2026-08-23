import { describe, expect, test, vi } from "vitest";

import {
  PLUGIN_BRIDGE_PROTOCOL,
  PluginBridgeClient,
  PluginBridgeError,
} from "../src/bridge/plugin-bridge-client.ts";

class FakePort {
  onmessage: ((event: MessageEvent<unknown>) => void) | null = null;
  readonly sent: unknown[] = [];
  started = false;
  closed = false;

  postMessage(message: unknown) { this.sent.push(message); }
  start() { this.started = true; }
  close() { this.closed = true; }
  emit(data: unknown) { this.onmessage?.({ data } as MessageEvent<unknown>); }
}

class FakeScope {
  listener: ((event: MessageEvent<unknown>) => void) | null = null;
  addEventListener(_type: "message", listener: (event: MessageEvent<unknown>) => void) { this.listener = listener; }
  removeEventListener(_type: "message", listener: (event: MessageEvent<unknown>) => void) {
    if (this.listener === listener) this.listener = null;
  }
  emit(data: unknown, source: unknown, port: FakePort) {
    this.listener?.({ data, source, ports: [port] } as unknown as MessageEvent<unknown>);
  }
}

function connect(capabilities: string[] = ["session.list", "provider.list"]) {
  const scope = new FakeScope();
  const parent = { postMessage: vi.fn() };
  const port = new FakePort();
  let requestId = 0;
  const diagnostics: string[] = [];
  const client = new PluginBridgeClient({
    pluginId: "next-trainer-pi-agent",
    scope,
    parentTarget: parent,
    requestIdFactory: () => `request-${++requestId}`,
    onDiagnostic: (message) => diagnostics.push(message),
  });
  const ready = client.start();
  scope.emit({
    type: "CHALLENGE",
    protocolVersion: PLUGIN_BRIDGE_PROTOCOL,
    pluginId: "next-trainer-pi-agent",
    instanceId: "instance-1",
    nonce: "nonce-1",
  }, parent, port);
  port.emit({
    type: "WELCOME",
    protocolVersion: PLUGIN_BRIDGE_PROTOCOL,
    pluginId: "next-trainer-pi-agent",
    instanceId: "instance-1",
    grantedCapabilities: capabilities,
    themeTokens: {},
    locale: "zh-CN",
    activeSession: null,
  });
  return { client, diagnostics, parent, port, ready, scope };
}

describe("PluginBridgeClient", () => {
  test("completes the opaque-origin MessagePort handshake before RPC", async () => {
    const { client, parent, port, ready } = connect();
    expect(parent.postMessage).toHaveBeenCalledWith({
      type: "READY",
      pluginId: "next-trainer-pi-agent",
      protocolVersion: PLUGIN_BRIDGE_PROTOCOL,
    }, "*");
    expect(port.started).toBe(true);
    expect(port.sent[0]).toEqual({
      type: "HELLO",
      pluginId: "next-trainer-pi-agent",
      instanceId: "instance-1",
      protocolVersion: PLUGIN_BRIDGE_PROTOCOL,
      nonce: "nonce-1",
    });
    expect((await ready).locale).toBe("zh-CN");

    const response = client.request<string[]>("session.list", {});
    expect(port.sent[1]).toMatchObject({ seq: 1, requestId: "request-1", type: "session.list" });
    port.emit({
      protocol: PLUGIN_BRIDGE_PROTOCOL,
      pluginId: "next-trainer-pi-agent",
      instanceId: "instance-1",
      seq: 1,
      requestId: "host-1",
      replyTo: "request-1",
      type: "RESPONSE",
      ok: true,
      data: ["session-a"],
    });
    await expect(response).resolves.toEqual(["session-a"]);
  });

  test("rejects capabilities that were not granted without sending a request", async () => {
    const { client, port } = connect(["session.list"]);
    await expect(client.request("provider.list", {})).rejects.toMatchObject({
      code: "BRIDGE_CAPABILITY_DENIED",
    });
    expect(port.sent).toHaveLength(1);
  });

  test("ignores stale response sequence numbers and accepts the next monotonic response", async () => {
    const { client, diagnostics, port } = connect();
    const first = client.request("session.list", {});
    port.emit({
      protocol: PLUGIN_BRIDGE_PROTOCOL,
      pluginId: "next-trainer-pi-agent",
      instanceId: "instance-1",
      seq: 1,
      requestId: "host-1",
      replyTo: "request-1",
      type: "RESPONSE",
      ok: true,
      data: [],
    });
    await first;

    const second = client.request("provider.list", {});
    port.emit({
      protocol: PLUGIN_BRIDGE_PROTOCOL,
      pluginId: "next-trainer-pi-agent",
      instanceId: "instance-1",
      seq: 1,
      requestId: "host-replay",
      replyTo: "request-2",
      type: "RESPONSE",
      ok: true,
      data: ["replayed"],
    });
    expect(diagnostics.at(-1)).toContain("replayed or stale");
    port.emit({
      protocol: PLUGIN_BRIDGE_PROTOCOL,
      pluginId: "next-trainer-pi-agent",
      instanceId: "instance-1",
      seq: 2,
      requestId: "host-2",
      replyTo: "request-2",
      type: "RESPONSE",
      ok: true,
      data: ["provider-a"],
    });
    await expect(second).resolves.toEqual(["provider-a"]);
  });

  test("rejects in-flight requests when the port is closed", async () => {
    const { client, port } = connect();
    const pending = client.request("session.list", {});
    client.close();
    await expect(pending).rejects.toBeInstanceOf(PluginBridgeError);
    expect(port.closed).toBe(true);
  });

  test("delivers only identity-consistent monotonic event envelopes", () => {
    const { client, diagnostics, port } = connect(["session.subscribe"]);
    const events: unknown[] = [];
    client.onEvent((event) => events.push(event));
    const event = {
      type: "connected",
      eventId: "event-1",
      sessionId: "session-1",
      runId: 0,
      state: {
        id: "session-1",
        runId: 0,
        status: "idle",
        model: null,
        thinkingLevel: "auto",
        queue: { steering: [], followUp: [] },
      },
    };
    port.emit({
      protocol: PLUGIN_BRIDGE_PROTOCOL,
      pluginId: "next-trainer-pi-agent",
      instanceId: "instance-1",
      seq: 1,
      requestId: "host-event-1",
      type: "EVENT",
      eventId: "different-event",
      sessionId: "session-1",
      runId: 0,
      data: event,
    });
    expect(events).toHaveLength(0);
    expect(diagnostics.at(-1)).toContain("invalid bridge message");

    port.emit({
      protocol: PLUGIN_BRIDGE_PROTOCOL,
      pluginId: "next-trainer-pi-agent",
      instanceId: "instance-1",
      seq: 1,
      requestId: "host-event-2",
      type: "EVENT",
      eventId: "event-1",
      sessionId: "session-1",
      runId: 0,
      data: event,
    });
    expect(events).toEqual([event]);
  });
});





