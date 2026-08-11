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

export function useDatasetTagFilter<T extends { tags: string[] }>(items: Ref<T[]>, globalTags: Ref<TagCount[]>) {
  const state = reactive({
    selectedTags: new Set<string>(),
    logic: "and" as TagFilterLogic,
    search: "",
    searchMode: "substring" as TagSearchMode,
    sortBy: "frequency" as TagSortBy,
    order: "desc" as SortOrder,
  })

  const filteredItems = computed(() => filterItemsByTags(items.value, state.selectedTags, state.logic))
  const visibleTagList = computed(() => searchTagList(sortTagList(globalTags.value, state.sortBy, state.order), state.search, state.searchMode))
  const hasActiveFilter = computed(() => state.selectedTags.size > 0)

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
  }

  return { state, filteredItems, visibleTagList, hasActiveFilter, toggleTag, clearTags, reset }
}
