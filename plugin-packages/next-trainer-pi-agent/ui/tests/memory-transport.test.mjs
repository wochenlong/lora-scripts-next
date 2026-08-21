import assert from "node:assert/strict";
import test from "node:test";

import { MemoryTransport } from "../src/testing/memory-transport.ts";

test("a client can establish its subscription before prompt admission", async () => {
  const transport = new MemoryTransport();
  const session = await transport.sessions.create({});
  const unsubscribe = transport.sessions.subscribe(session.id, () => {});
  const receipt = await transport.sessions.prompt(session.id, {
    text: "hello",
    clientSubmissionId: "submission-1",
  });
  unsubscribe();
  assert.equal(receipt.accepted, true);
  assert.deepEqual(transport.operations.slice(-2), ["sessions.subscribe", "sessions.prompt"]);
});

test("a running session delegates steer and follow-up to its queue", async () => {
  const transport = new MemoryTransport();
  const session = await transport.sessions.create({});
  await transport.sessions.prompt(session.id, { text: "start", clientSubmissionId: "submission-1" });
  const rejected = await transport.sessions.prompt(session.id, { text: "duplicate", clientSubmissionId: "submission-2" });
  assert.equal(rejected.accepted, false);
  await transport.sessions.prompt(session.id, {
    text: "adjust",
    clientSubmissionId: "submission-3",
    streamingBehavior: "steer",
  });
  const recalled = await transport.sessions.recallQueue(session.id);
  assert.deepEqual(recalled, { steering: ["adjust"], followUp: [] });
});

test("provider status exposes only configuration metadata", async () => {
  const transport = new MemoryTransport();
  transport.seedProvider({
    id: "remote",
    label: "Remote",
    endpoint: "https://example.invalid/v1/chat/completions",
    modelId: "model",
    configured: false,
  });
  const status = await transport.providers.saveKey({
    id: "remote",
    endpoint: "https://example.invalid/v1/chat/completions",
    modelId: "model",
    key: "secret-value-1234",
  });
  assert.equal(status.configured, true);
  assert.equal(status.fingerprint, "••••1234");
  assert.equal("key" in status, false);
  assert.equal(JSON.stringify(status).includes("secret-value"), false);
});

test("deferred thinking is loaded only through the session transport", async () => {
  const transport = new MemoryTransport();
  const session = await transport.sessions.create({});
  transport.setThinking(session.id, "entry-1", 0, "private reasoning");
  assert.equal(await transport.sessions.getThinking(session.id, "entry-1", 0), "private reasoning");
});
