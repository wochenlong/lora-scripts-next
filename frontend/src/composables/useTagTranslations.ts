import { computed, ref } from "vue"
import { datasetApi, type TagTranslation, type TagTranslationProvider } from "../api/dataset"

const STORAGE_KEY = "dataset-tag-translation-cache-v1"
const MAX_ENTRIES = 2000

function readEntries(): Record<string, TagTranslation> {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null")
    return parsed && typeof parsed === "object" ? parsed as Record<string, TagTranslation> : {}
  } catch {
    return {}
  }
}

const entries = ref<Record<string, TagTranslation>>(readEntries())
const loading = ref(false)
const error = ref("")
const activeProvider = ref<TagTranslationProvider>("danbooru")
const activeLocale = ref("zh-CN")
const progress = ref({ completed: 0, total: 0 })
const unresolved = ref(0)
let generation = 0

function cacheKey(tag: string, provider: TagTranslationProvider, locale: string) {
  return `${locale}\u0000${provider}\u0000${tag}`
}

function persistEntries() {
  try {
    const pairs = Object.entries(entries.value)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(Object.fromEntries(pairs.slice(-MAX_ENTRIES))))
  } catch {
    // Browser storage is an optimization; translation display must keep working.
  }
}

export function useTagTranslations() {
  const translations = computed(() => entries.value)

  async function resolve(tags: string[], provider: TagTranslationProvider, locale = "zh-CN", localOnly = false) {
    activeProvider.value = provider
    activeLocale.value = locale
    const unique = [...new Set(tags.map((tag) => tag.trim()).filter(Boolean))]
    const missing = unique.filter((tag) => {
      const entry = entries.value[cacheKey(tag, provider, locale)]
      return !entry || entry.status !== "hit"
    })
    progress.value = { completed: unique.length - missing.length, total: unique.length }
    unresolved.value = 0
    if (!missing.length) {
      loading.value = false
      return
    }
    const requestGeneration = ++generation
    loading.value = true
    error.value = ""
    try {
      const next = { ...entries.value }
      for (let start = 0; start < missing.length; start += 500) {
        const batch = missing.slice(start, start + 500)
        const response = localOnly
          ? await datasetApi.tagTranslations(batch, provider, locale, { localOnly: true })
          : await datasetApi.tagTranslations(batch, provider, locale)
        if (requestGeneration !== generation) return
        for (const item of response.items) next[cacheKey(item.tag, provider, locale)] = item
        unresolved.value += response.items.filter((item) => item.status !== "hit").length
        entries.value = next
        persistEntries()
        progress.value = {
          completed: unique.length - missing.length + Math.min(start + batch.length, missing.length),
          total: unique.length,
        }
      }
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
    try { localStorage.removeItem(STORAGE_KEY) } catch { /* ignore unavailable storage */ }
    error.value = ""
    loading.value = false
    progress.value = { completed: 0, total: 0 }
    unresolved.value = 0
  }

  function clearExternalCache() {
    generation += 1
    const preserved = Object.fromEntries(
      Object.entries(entries.value).filter(([key]) => key.includes("\u0000danbooru\u0000")),
    )
    entries.value = preserved
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(preserved)) } catch { /* ignore unavailable storage */ }
    error.value = ""
    loading.value = false
    progress.value = { completed: 0, total: 0 }
    unresolved.value = 0
  }

  function cancelCurrent() {
    generation += 1
    loading.value = false
    error.value = ""
    progress.value = { completed: 0, total: 0 }
    unresolved.value = 0
  }

  return { translations, loading, error, progress, unresolved, resolve, translationFor, clearCache, clearExternalCache, cancelCurrent }
}
