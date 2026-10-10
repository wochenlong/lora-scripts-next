import { reactive, ref } from "vue"
import type { DatasetHistory, DatasetItem, TagTranslationProvider } from "../api/dataset"
import type { DatasetTagFilterState } from "./useDatasetTagFilter"
import type { SortOrder, TagFilterLogic, TagSearchMode, TagSortBy } from "../dataset/tagFilter"

const STORAGE_KEY = "dataset-editor-session-v1"
const MAX_DRAFTS = 500

interface PersistedSession {
  lastPath?: string
  lastRoot?: string
  selected?: string
  drafts?: Record<string, string>
  showTranslations?: boolean
  translationProvider?: TagTranslationProvider
  category?: string
  query?: string
  page?: number
  rightPanelMode?: "caption" | "filter" | "batch"
  tagFilter?: {
    selectedTags?: string[]
    logic?: TagFilterLogic
    search?: string
    searchMode?: TagSearchMode
    sortBy?: TagSortBy
    order?: SortOrder
    excludeInput?: string
  }
}

function readPersisted(): PersistedSession {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null") as PersistedSession | null
    return parsed && typeof parsed === "object" ? parsed : {}
  } catch {
    return {}
  }
}

const persisted = readPersisted()
const lastPath = ref(typeof persisted.lastPath === "string" ? persisted.lastPath : "")
const lastRoot = ref(typeof persisted.lastRoot === "string" ? persisted.lastRoot : "")
const selected = ref(typeof persisted.selected === "string" ? persisted.selected : "")
const drafts = ref<Record<string, string>>(persisted.drafts && typeof persisted.drafts === "object" ? { ...persisted.drafts } : {})
const showTranslations = ref(Boolean(persisted.showTranslations))
// Only the dictionary and LLM sources are offered; legacy auto/mymemory values
// fall back to the offline dictionary.
const translationProvider = ref<TagTranslationProvider>(persisted.translationProvider === "llm" ? "llm" : "danbooru")
const category = ref(typeof persisted.category === "string" ? persisted.category : "")
const query = ref(typeof persisted.query === "string" ? persisted.query : "")
const page = ref(typeof persisted.page === "number" && persisted.page > 0 ? persisted.page : 1)
const rightPanelMode = ref<"caption" | "filter" | "batch">(persisted.rightPanelMode || "caption")
const tagFilter = reactive<DatasetTagFilterState>({
  selectedTags: new Set(persisted.tagFilter?.selectedTags || []),
  logic: persisted.tagFilter?.logic || "and",
  search: persisted.tagFilter?.search || "",
  searchMode: persisted.tagFilter?.searchMode || "substring",
  sortBy: persisted.tagFilter?.sortBy || "frequency",
  order: persisted.tagFilter?.order || "desc",
  excludeInput: persisted.tagFilter?.excludeInput || "",
})

// These values live for the lifetime of the SPA. They allow a route switch to
// return instantly without retaining the whole Dataset page in KeepAlive.
const items = ref<DatasetItem[]>([])
const tags = ref<Array<{ tag: string; count: number }>>([])
const categories = ref<Array<{ name: string; value: string; count: number }>>([])
const selectedPaths = ref(new Set<string>())
const history = ref<DatasetHistory>({ can_undo: false, can_redo: false, changes: [] })

function draftKey(root: string, relativePath: string) {
  return `${root}\u0000${relativePath}`
}

function persist() {
  const entries = Object.entries(drafts.value)
  const limited = entries.length > MAX_DRAFTS ? entries.slice(entries.length - MAX_DRAFTS) : entries
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      lastPath: lastPath.value,
      lastRoot: lastRoot.value,
      selected: selected.value,
      drafts: Object.fromEntries(limited),
      showTranslations: showTranslations.value,
      translationProvider: translationProvider.value,
      category: category.value,
      query: query.value,
      page: page.value,
      rightPanelMode: rightPanelMode.value,
      tagFilter: {
        selectedTags: [...tagFilter.selectedTags],
        logic: tagFilter.logic,
        search: tagFilter.search,
        searchMode: tagFilter.searchMode,
        sortBy: tagFilter.sortBy,
        order: tagFilter.order,
        excludeInput: tagFilter.excludeInput,
      },
    } satisfies PersistedSession))
  } catch {
    // A full or unavailable storage must not break dataset editing.
  }
}

function rememberDataset(path: string, root: string) {
  lastPath.value = path
  lastRoot.value = root
  persist()
}

function rememberSelection(relativePath: string) {
  selected.value = relativePath
  persist()
}

function getDraft(root: string, relativePath: string) {
  return drafts.value[draftKey(root, relativePath)]
}

function setDraft(root: string, relativePath: string, caption: string) {
  if (!root || !relativePath) return
  const key = draftKey(root, relativePath)
  drafts.value = { ...drafts.value, [key]: caption }
  persist()
}

function clearDraft(root: string, relativePath: string) {
  const key = draftKey(root, relativePath)
  if (!(key in drafts.value)) return
  const next = { ...drafts.value }
  delete next[key]
  drafts.value = next
  persist()
}

function clearDrafts(root: string, relativePaths: string[]) {
  if (!relativePaths.length) return
  const next = { ...drafts.value }
  let changed = false
  for (const relativePath of relativePaths) {
    const key = draftKey(root, relativePath)
    if (key in next) {
      delete next[key]
      changed = true
    }
  }
  if (changed) {
    drafts.value = next
    persist()
  }
}

function rememberPreferences() {
  persist()
}

function resetInMemoryDataset() {
  items.value = []
  tags.value = []
  categories.value = []
  selectedPaths.value = new Set()
  selected.value = ""
  history.value = { can_undo: false, can_redo: false, changes: [] }
}

function unload() {
  const prefix = `${lastRoot.value}\u0000`
  drafts.value = Object.fromEntries(Object.entries(drafts.value).filter(([key]) => !key.startsWith(prefix)))
  resetInMemoryDataset()
  lastRoot.value = ""
  lastPath.value = ""
  category.value = ""
  query.value = ""
  page.value = 1
  rightPanelMode.value = "caption"
  tagFilter.selectedTags.clear()
  tagFilter.search = ""
  tagFilter.excludeInput = ""
  persist()
}

export function useDatasetEditorSession() {
  return {
    unload,
    lastPath,
    lastRoot,
    selected,
    drafts,
    showTranslations,
    translationProvider,
    category,
    query,
    page,
    rightPanelMode,
    items,
    tags,
    categories,
    selectedPaths,
    history,
    tagFilter,
    rememberDataset,
    rememberSelection,
    getDraft,
    setDraft,
    clearDraft,
    clearDrafts,
    rememberPreferences,
    resetInMemoryDataset,
  }
}
