import assert from "node:assert/strict"
import test from "node:test"
import { mkdtemp, readFile, rm } from "node:fs/promises"
import os from "node:os"
import path from "node:path"
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

test("provider status never returns the raw API key", async () => {
  const registry = new ProviderRegistry()
  const key = "sk-status-must-not-leak"
  await registry.save("deepseek", {
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

test("persistent registry writes Pi-compatible isolated auth and model files", async (context) => {
  const root = await mkdtemp(path.join(os.tmpdir(), "next-trainer-provider-"))
  context.after(() => rm(root, { recursive: true, force: true }))
  const key = "sk-persisted-test-placeholder"
  const registry = await ProviderRegistry.open(root)
  await registry.save("qwen", {
    providerId: "siliconflow",
    modelId: "Qwen/Qwen3.6-27B",
    endpoint: "https://api.siliconflow.cn/v1/chat/completions",
    apiKey: key,
  })

  const authText = await readFile(path.join(root, "auth.json"), "utf8")
  const modelsText = await readFile(path.join(root, "models.json"), "utf8")
  const profilesText = await readFile(path.join(root, "provider-profiles.json"), "utf8")
  assert.deepEqual(JSON.parse(authText)["next-trainer-qwen"], { type: "api_key", key })
  assert.equal(modelsText.includes(key), false)
  assert.equal(profilesText.includes(key), false)
  assert.equal(JSON.parse(modelsText).providers["next-trainer-qwen"].api, "openai-completions")

  const reopened = await ProviderRegistry.open(root)
  assert.equal(reopened.status("qwen").modelId, "Qwen/Qwen3.6-27B")
  assert.equal(JSON.stringify(reopened.status("qwen")).includes(key), false)
  assert.equal(await reopened.remove("qwen"), true)
  assert.equal((await readFile(path.join(root, "auth.json"), "utf8")).includes(key), false)
})
