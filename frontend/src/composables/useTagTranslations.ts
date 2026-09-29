import { computed, ref } from "vue"
import { datasetApi, type TagTranslation, type TagTranslationProvider } from "../api/dataset"

export function useTagTranslations() {
  const entries = ref<Record<string, TagTranslation>>({})
  const loading = ref(false)
  const error = ref("")
  let generation = 0

  const translations = computed(() => entries.value)

  async function resolve(tags: string[], provider: TagTranslationProvider, locale = "zh-CN") {
    const unique = [...new Set(tags.map((tag) => tag.trim()).filter(Boolean))]
    const missing = unique.filter((tag) => !entries.value[tag] || entries.value[tag].status !== "hit")
    if (!missing.length) return
    const requestGeneration = ++generation
    loading.value = true
    error.value = ""
    try {
      const response = await datasetApi.tagTranslations(missing, provider, locale)
      if (requestGeneration !== generation) return
      const next = { ...entries.value }
      for (const item of response.items) next[item.tag] = item
      entries.value = next
    } catch (caught) {
      if (requestGeneration === generation) error.value = caught instanceof Error ? caught.message : String(caught)
    } finally {
      if (requestGeneration === generation) loading.value = false
    }
  }

  function translationFor(tag: string) {
    return entries.value[tag]?.translation || ""
  }

  function clear() {
    generation += 1
    entries.value = {}
    error.value = ""
    loading.value = false
  }

  return { translations, loading, error, resolve, translationFor, clear }
}
