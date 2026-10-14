import { computed, ref } from "vue"
import { datasetApi, type TagTranslation, type TagTranslationProvider } from "../api/dataset"

const STORAGE_KEY = "dataset-tag-translation-cache-v2"
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
const transient = ref<Record<string, TagTranslation>>({})
let cacheEnabled = true
let profileRevision = ""
const loading = ref(false)
const error = ref("")
const activeProvider = ref<TagTranslationProvider>("danbooru")
const activeLocale = ref("zh-CN")
const progress = ref({ completed: 0, total: 0 })
const unresolved = ref(0)
let generation = 0

function cacheKey(tag: string, provider: TagTranslationProvider, locale: string) {
  return provider === "danbooru" ? `${locale}\u0000${provider}\u0000${tag}`
    : `${locale}\u0000${provider}\u0000${profileRevision}\u0000${tag}`
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
  const translations = computed(() => ({ ...entries.value, ...transient.value }))

  function configureCache(enabled: boolean, revision: string) {
    if (enabled === cacheEnabled && revision === profileRevision) return
    clearExternalCache()
    cacheEnabled = enabled
    profileRevision = revision
  }

  async function resolve(tags: string[], provider: TagTranslationProvider, locale = "zh-CN", localOnly = false) {
    // A cache hit also supersedes earlier work; otherwise its late response
    // could replace the active result and progress after this call returns.
    const requestGeneration = ++generation
    activeProvider.value = provider
    activeLocale.value = locale
    error.value = ""
    const unique = [...new Set(tags.map((tag) => tag.trim()).filter(Boolean))]
    const reusable = provider === "danbooru" || cacheEnabled
    if (!reusable) transient.value = {}
    const missing = unique.filter((tag) => {
      if (!reusable) return true
      const entry = entries.value[cacheKey(tag, provider, locale)]
      return !entry || entry.status !== "hit" || (localOnly && entry.source !== "danbooru")
    })
    progress.value = { completed: unique.length - missing.length, total: unique.length }
    unresolved.value = 0
    if (!missing.length) {
      loading.value = false
      return
    }
    loading.value = true
    try {
      const next = reusable ? { ...entries.value } : { ...transient.value }
      for (let start = 0; start < missing.length; start += 500) {
        const batch = missing.slice(start, start + 500)
        const response = localOnly
          ? await datasetApi.tagTranslations(batch, provider, locale, { localOnly: true })
          : await datasetApi.tagTranslations(batch, provider, locale)
        if (requestGeneration !== generation) return
        for (const item of response.items) next[cacheKey(item.tag, provider, locale)] = item
        unresolved.value += response.items.filter((item) => item.status !== "hit").length
        if (reusable) {
          entries.value = { ...next }
          persistEntries()
        } else transient.value = { ...next }
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
    const key = cacheKey(tag, provider, locale)
    const reusable = provider === "danbooru" || cacheEnabled
    return (transient.value[key] ?? (reusable ? entries.value[key] : undefined))?.translation || ""
  }

  function clearCache() {
    generation += 1
    entries.value = {}
    transient.value = {}
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
    transient.value = {}
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

  return { translations, loading, error, progress, unresolved, resolve, translationFor, clearCache, clearExternalCache, cancelCurrent, configureCache }
}
