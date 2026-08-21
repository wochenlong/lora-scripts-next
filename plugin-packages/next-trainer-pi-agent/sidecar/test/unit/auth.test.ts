import assert from "node:assert/strict"
import test from "node:test"
import { redactForDiagnostics, requireBearer, secretsEqual } from "../../src/auth.ts"
import { SidecarError } from "../../src/errors.ts"

test("bearer authentication is exact and timing-safe comparable", () => {
  const token = "a".repeat(32)
  assert.equal(secretsEqual(token, token), true)
  assert.equal(secretsEqual(token, "b".repeat(32)), false)
  assert.doesNotThrow(() => requireBearer(new Request("http://127.0.0.1/", {
    headers: { authorization: `Bearer ${token}` },
  }), token))
  assert.throws(
    () => requireBearer(new Request("http://127.0.0.1/"), token),
    (error: unknown) => error instanceof SidecarError && error.code === "SIDECAR_AUTH_REQUIRED",
  )
})

test("diagnostic redaction removes nested credential fields", () => {
  const secret = "sk-test-do-not-leak"
  const redacted = redactForDiagnostics({ apiKey: secret, nested: { Authorization: secret, safe: "ok" } })
  const serialized = JSON.stringify(redacted)
  assert.equal(serialized.includes(secret), false)
  assert.equal(serialized.includes("ok"), true)
})
