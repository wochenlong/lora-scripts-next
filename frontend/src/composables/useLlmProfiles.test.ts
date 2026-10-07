import { afterEach, describe, expect, it, vi } from "vitest"
import { ref } from "vue"
import { llmApi, type LlmConfig } from "../api/llm"
import { useLlmProfiles } from "./useLlmProfiles"
vi.mock("../api/llm", () => ({ llmApi: { profiles: vi.fn() } }))
afterEach(() => vi.resetAllMocks())
const config: LlmConfig = { version: 5, routes: {}, prompt_presets: [], cache: {}, profiles: [
  { id: "local", name: "local", model: "m", endpoint: "http://localhost:8080/v1/chat/completions", source: "local-endpoint", capabilities: ["vision"], languages: ["zh-CN"], api_key: "", enabled: true, ready: true },
  { id: "remote", name: "remote", model: "m", endpoint: "https://example.test/chat/completions", source: "remote", capabilities: ["text", "vision"], languages: ["zh-CN"], api_key: "********", enabled: true, ready: true },
  { id: "text", name: "text", model: "m", endpoint: "https://example.test/chat/completions", source: "remote", capabilities: ["text"], languages: ["zh-CN"], api_key: "", enabled: true, ready: true },
] }
describe("shared profile lifecycle", () => {
  it("applies readiness/capability/language filters with remote first", async () => {
    vi.mocked(llmApi.profiles).mockResolvedValue(config)
    const language = ref("zh-CN")
    const profiles = useLlmProfiles("vision", language)
    await profiles.load()
    expect(profiles.profiles.value.map(profile => profile.id)).toEqual(["remote", "local"])
    language.value = "ja"
    expect(profiles.profiles.value).toEqual([])
  })
  it("aborts obsolete requests and does not commit after invalidation", async () => {
    let finish!: (value: LlmConfig) => void
    vi.mocked(llmApi.profiles).mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    const profiles = useLlmProfiles("vision")
    const pending = profiles.load()
    const signal = vi.mocked(llmApi.profiles).mock.calls[0][0]!
    profiles.invalidate()
    expect(signal.aborted).toBe(true)
    finish(config)
    await pending
    expect(profiles.config.value.profiles).toEqual([])
  })
})
