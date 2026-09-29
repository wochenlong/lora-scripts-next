import { computed, reactive, type Ref } from "vue"
import {
  filterItemsByTags,
  searchTagList,
  sortTagList,
  type SortOrder,
  type TagCount,
  type TagFilterLogic,
  type TagSearchMode,
  type TagSortBy,
} from "../dataset/tagFilter"

export interface DatasetTagFilterState {
  selectedTags: Set<string>
  logic: TagFilterLogic
  search: string
  searchMode: TagSearchMode
  sortBy: TagSortBy
  order: SortOrder
  excludeInput: string
}

function createState(): DatasetTagFilterState {
  return {
    selectedTags: new Set<string>(),
    logic: "and" as TagFilterLogic,
    search: "",
    searchMode: "substring" as TagSearchMode,
    sortBy: "frequency" as TagSortBy,
    order: "desc" as SortOrder,
    excludeInput: "",
  }
}

export function useDatasetTagFilter<T extends { tags: string[] }>(
  items: Ref<T[]>,
  globalTags: Ref<TagCount[]>,
  sharedState?: DatasetTagFilterState,
) {
  const state = reactive(sharedState || createState())

  const excludedTags = computed(() => new Set(state.excludeInput.split(/[,，\n]/).map((tag) => tag.trim()).filter(Boolean)))
  const filteredItems = computed(() => filterItemsByTags(items.value, state.selectedTags, state.logic, excludedTags.value))
  const visibleTagList = computed(() => searchTagList(sortTagList(globalTags.value, state.sortBy, state.order), state.search, state.searchMode))
  const hasActiveFilter = computed(() => state.selectedTags.size > 0 || excludedTags.value.size > 0)

  function toggleTag(tag: string) {
    const next = new Set(state.selectedTags)
    if (next.has(tag)) next.delete(tag)
    else next.add(tag)
    state.selectedTags = next
  }

  function clearTags() {
    state.selectedTags = new Set()
  }

  function reset() {
    clearTags()
    state.search = ""
    state.excludeInput = ""
  }

  return { state, filteredItems, visibleTagList, hasActiveFilter, excludedTags, toggleTag, clearTags, reset }
}
