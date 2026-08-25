import { describe, expect, test, vi } from "vitest";

import { BridgeAgentTransport } from "../src/bridge/bridge-transport.ts";
import type { PluginBridgeClient } from "../src/bridge/plugin-bridge-client.ts";

describe("BridgeAgentTransport subscription admission", () => {
  test("waits for session.subscribe acknowledgement before sending the first prompt", async () => {
    let acknowledgeSubscription: (() => void) | undefined;
    const calls: string[] = [];
    const bridge = {
      onEvent: () => () => {},
      request: vi.fn((method: string) => {
        calls.push(method);
        if (method === "session.subscribe") {
          return new Promise((resolve) => { acknowledgeSubscription = () => resolve({ subscribed: true }); });
        }
        if (method === "session.prompt") {
          return Promise.resolve({
            accepted: true,
            sessionId: "session-1",
            runId: 1,
            clientSubmissionId: "submission-1",
            disposition: "started",
          });
        }
        return Promise.resolve(null);
      }),
    } as unknown as PluginBridgeClient;
    const transport = new BridgeAgentTransport(bridge);
    transport.sessions.subscribe("session-1", () => {});
    const prompt = transport.sessions.prompt("session-1", {
      text: "hello",
      clientSubmissionId: "submission-1",
    });

    await Promise.resolve();
    const callsBeforeAcknowledgement = [...calls];
    acknowledgeSubscription?.();
    await prompt;
    expect(callsBeforeAcknowledgement).toEqual(["session.subscribe"]);
    expect(calls).toEqual(["session.subscribe", "session.prompt"]);
  });
});
