import { computed, ref } from "vue"
import { datasetApi, type TagTranslation, type TagTranslationProvider } from "../api/dataset"

const entries = ref<Record<string, TagTranslation>>({})
const loading = ref(false)
const error = ref("")
const activeProvider = ref<TagTranslationProvider>("danbooru")
const activeLocale = ref("zh-CN")
let generation = 0

function cacheKey(tag: string, provider: TagTranslationProvider, locale: string) {
  return `${locale}\u0000${provider}\u0000${tag}`
}

export function useTagTranslations() {
  const translations = computed(() => entries.value)

  async function resolve(tags: string[], provider: TagTranslationProvider, locale = "zh-CN") {
    activeProvider.value = provider
    activeLocale.value = locale
    const unique = [...new Set(tags.map((tag) => tag.trim()).filter(Boolean))]
    const missing = unique.filter((tag) => {
      const entry = entries.value[cacheKey(tag, provider, locale)]
      return !entry || entry.status !== "hit"
    })
    if (!missing.length) return
    const requestGeneration = ++generation
    loading.value = true
    error.value = ""
    try {
      const response = await datasetApi.tagTranslations(missing, provider, locale)
      if (requestGeneration !== generation) return
      const next = { ...entries.value }
      for (const item of response.items) next[cacheKey(item.tag, provider, locale)] = item
      entries.value = next
    } catch (caught) {
      if (requestGeneration === generation) error.value = caught instanceof Error ? caught.message : String(caught)
    } finally {
      if (requestGeneration === generation) loading.value = false
    }
  }

  function translationFor(tag: string, provider = activeProvider.value, locale = activeLocale.value) {
    return entries.value[cacheKey(tag, provider, locale)]?.translation || ""
  }

  function clearCache() {
    generation += 1
    entries.value = {}
    error.value = ""
    loading.value = false
  }

  return { translations, loading, error, resolve, translationFor, clearCache }
}
