<script setup lang="ts">
import { useI18n } from "vue-i18n"
import type { SortOrder, TagCount, TagFilterLogic, TagSearchMode, TagSortBy } from "../../dataset/tagFilter"

withDefaults(
  defineProps<{
    tags: TagCount[]
    selectedTags: ReadonlySet<string>
    logic: TagFilterLogic
    search: string
    searchMode: TagSearchMode
    sortBy: TagSortBy
    order: SortOrder
    excludeInput: string
    filteredCount: number
    showSelectAll?: boolean
  }>(),
  { showSelectAll: true },
)

const emit = defineEmits<{
  "update:logic": [value: TagFilterLogic]
  "update:search": [value: string]
  "update:searchMode": [value: TagSearchMode]
  "update:sortBy": [value: TagSortBy]
  "update:order": [value: SortOrder]
  "update:excludeInput": [value: string]
  toggleTag: [tag: string]
  clear: []
  selectAll: []
}>()

const { t } = useI18n()

function selectValue(event: Event): string {
  return (event.target as HTMLSelectElement).value
}
</script>

<template>
  <div class="tag-filter-box">
    <strong>{{ t("datasetEditor.tagFilter.title") }}</strong>
    <input :value="search" :placeholder="t('datasetEditor.tagFilter.searchPlaceholder')" @input="emit('update:search', ($event.target as HTMLInputElement).value)">
    <div class="tag-filter-controls">
      <select :value="sortBy" :aria-label="t('datasetEditor.tagFilter.sortLabel')" @change="emit('update:sortBy', selectValue($event) as TagSortBy)">
        <option value="frequency">{{ t("datasetEditor.tagFilter.sortFrequency") }}</option>
        <option value="alphabetical">{{ t("datasetEditor.tagFilter.sortAlphabetical") }}</option>
        <option value="length">{{ t("datasetEditor.tagFilter.sortLength") }}</option>
        <option value="tokenLength" :title="t('datasetEditor.tagFilter.tokenLengthTip')">{{ t("datasetEditor.tagFilter.sortTokenLength") }}</option>
      </select>
      <select :value="order" :aria-label="t('datasetEditor.tagFilter.orderLabel')" @change="emit('update:order', selectValue($event) as SortOrder)">
        <option value="desc">{{ t("datasetEditor.tagFilter.orderDesc") }}</option>
        <option value="asc">{{ t("datasetEditor.tagFilter.orderAsc") }}</option>
      </select>
      <select :value="searchMode" :aria-label="t('datasetEditor.tagFilter.searchModeLabel')" @change="emit('update:searchMode', selectValue($event) as TagSearchMode)">
        <option value="substring">{{ t("datasetEditor.tagFilter.searchModeSubstring") }}</option>
        <option value="prefix">{{ t("datasetEditor.tagFilter.searchModePrefix") }}</option>
        <option value="suffix">{{ t("datasetEditor.tagFilter.searchModeSuffix") }}</option>
      </select>
    </div>
    <div class="tag-filter-logic">
      <label v-for="mode in (['and', 'or', 'none'] as TagFilterLogic[])" :key="mode">
        <input type="radio" name="tag-filter-logic" :value="mode" :checked="logic === mode" @change="emit('update:logic', mode)">
        {{ t(`datasetEditor.tagFilter.logic.${mode}`) }}
      </label>
    </div>
    <div class="tag-filter-list">
      <label v-for="entry in tags" :key="entry.tag" class="tag-filter-item">
        <input type="checkbox" :checked="selectedTags.has(entry.tag)" @change="emit('toggleTag', entry.tag)">
        <span>{{ entry.tag }}</span>
        <small>{{ entry.count }}</small>
      </label>
      <p v-if="!tags.length" class="tag-filter-meta">{{ t("datasetEditor.tagFilter.empty") }}</p>
    </div>
    <small v-if="selectedTags.size" class="tag-filter-meta">{{ t("datasetEditor.tagFilter.selectedCount", { k: selectedTags.size }) }}</small>
    <input :value="excludeInput" :placeholder="t('datasetEditor.tagFilter.excludePlaceholder')" :title="t('datasetEditor.tagFilter.excludeTip')" @input="emit('update:excludeInput', ($event.target as HTMLInputElement).value)">
    <div class="tag-filter-actions">
      <button :disabled="!selectedTags.size" @click="emit('clear')">{{ t("datasetEditor.tagFilter.clear") }}</button>
      <button
        v-if="showSelectAll"
        :disabled="!filteredCount"
        :title="t('datasetEditor.tagFilter.selectAllTip')"
        @click="emit('selectAll')"
      >
        {{ t("datasetEditor.tagFilter.selectAll", { n: filteredCount }) }}
      </button>
    </div>
  </div>
</template>
