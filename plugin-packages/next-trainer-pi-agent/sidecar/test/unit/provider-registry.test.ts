import assert from "node:assert/strict"
import test from "node:test"
import { normalizeChatCompletionsEndpoint, ProviderRegistry } from "../../src/pi/provider-registry.ts"
import { SidecarError } from "../../src/errors.ts"

test("provider endpoint normalization preserves the authorized endpoint boundary", () => {
  assert.deepEqual(normalizeChatCompletionsEndpoint("https://api.example.com/v1/chat/completions/"), {
    authorizedEndpoint: "https://api.example.com/v1/chat/completions",
    baseUrl: "https://api.example.com/v1",
  })
})

test("provider endpoint rejects insecure, credentialed, and non-chat URLs", () => {
  for (const endpoint of [
    "http://api.example.com/v1/chat/completions",
    "https://user:pass@api.example.com/v1/chat/completions",
    "https://api.example.com/v1/models",
    "https://api.example.com/v1/chat/completions?key=x",
  ]) {
    assert.throws(
      () => normalizeChatCompletionsEndpoint(endpoint),
      (error: unknown) => error instanceof SidecarError && error.code === "PROVIDER_ENDPOINT_INVALID",
    )
  }
})

test("provider status never returns the raw API key", () => {
  const registry = new ProviderRegistry()
  const key = "sk-status-must-not-leak"
  registry.save("deepseek", {
    providerId: "deepseek",
    modelId: "deepseek-v4-flash",
    endpoint: "https://api.deepseek.com/v1/chat/completions",
    apiKey: key,
  })
  const serialized = JSON.stringify(registry.status("deepseek"))
  assert.equal(serialized.includes(key), false)
  assert.equal(serialized.includes("apiKey"), false)
  assert.match(registry.status("deepseek").fingerprint, /^[0-9a-f]{12}$/)
})
