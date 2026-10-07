import { computed, ref, type Ref } from "vue"
import { llmApi, type LlmConfig } from "../api/llm"

export function useLlmProfiles(capability: "text" | "vision", language?: Ref<string>) {
  const config = ref<LlmConfig>({ version: 5, profiles: [], routes: {}, prompt_presets: [], cache: { caption: true, translation: true } })
  const loading = ref(false)
  const error = ref("")
  const profiles = computed(() => config.value.profiles.filter(profile => profile.enabled && profile.ready && profile.capabilities.includes(capability)
    && (!language || profile.languages.includes(language.value) || profile.languages.includes("*")))
    .sort((a, b) => Number(b.source === "remote") - Number(a.source === "remote")))
  let generation = 0
  let pending: Promise<void> | null = null
  let controller: AbortController | null = null
  function invalidate() { generation += 1; controller?.abort(); controller = null; pending = null; loading.value = false }
  function load(): Promise<void> {
    if (pending) return pending
    const revision = generation
    controller = new AbortController()
    const signal = controller.signal
    loading.value = true
    const operation = (async () => {
      try {
        const next = await llmApi.profiles(signal)
        if (revision === generation) { config.value = next; error.value = "" }
      } catch (caught) {
        if (revision === generation) error.value = caught instanceof Error ? caught.message : String(caught)
      }
    })().finally(() => { if (pending === operation) { pending = null; loading.value = false } })
    pending = operation
    return pending
  }
  return { config, profiles, loading, error, load, invalidate }
}
