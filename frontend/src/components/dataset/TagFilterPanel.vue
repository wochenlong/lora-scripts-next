<script setup lang="ts">
import { useI18n } from "vue-i18n"
import { ElButton, ElCheckbox, ElInput, ElOption, ElRadio, ElRadioGroup, ElSelect } from "element-plus"
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

function emitLogic(value: string | number | boolean | undefined) {
  emit("update:logic", String(value) as TagFilterLogic)
}
</script>

<template>
  <div class="tag-filter-box">
    <strong>{{ t("datasetEditor.tagFilter.title") }}</strong>
    <el-input :model-value="search" :placeholder="t('datasetEditor.tagFilter.searchPlaceholder')" @update:model-value="emit('update:search', $event)" />
    <div class="tag-filter-controls">
      <el-select :model-value="sortBy" :aria-label="t('datasetEditor.tagFilter.sortLabel')" @update:model-value="emit('update:sortBy', $event)">
        <el-option value="frequency" :label="t('datasetEditor.tagFilter.sortFrequency')" />
        <el-option value="alphabetical" :label="t('datasetEditor.tagFilter.sortAlphabetical')" />
        <el-option value="length" :label="t('datasetEditor.tagFilter.sortLength')" />
        <el-option value="tokenLength" :label="t('datasetEditor.tagFilter.sortTokenLength')" />
      </el-select>
      <el-select :model-value="order" :aria-label="t('datasetEditor.tagFilter.orderLabel')" @update:model-value="emit('update:order', $event)">
        <el-option value="desc" :label="t('datasetEditor.tagFilter.orderDesc')" />
        <el-option value="asc" :label="t('datasetEditor.tagFilter.orderAsc')" />
      </el-select>
      <el-select :model-value="searchMode" :aria-label="t('datasetEditor.tagFilter.searchModeLabel')" @update:model-value="emit('update:searchMode', $event)">
        <el-option value="substring" :label="t('datasetEditor.tagFilter.searchModeSubstring')" />
        <el-option value="prefix" :label="t('datasetEditor.tagFilter.searchModePrefix')" />
        <el-option value="suffix" :label="t('datasetEditor.tagFilter.searchModeSuffix')" />
      </el-select>
    </div>
    <el-radio-group :model-value="logic" class="tag-filter-logic" @update:model-value="emitLogic">
      <el-radio v-for="mode in (['and', 'or', 'none'] as TagFilterLogic[])" :key="mode" :value="mode">
        {{ t(`datasetEditor.tagFilter.logic.${mode}`) }}
      </el-radio>
    </el-radio-group>
    <div class="tag-filter-list">
      <el-checkbox v-for="entry in tags" :key="entry.tag" :model-value="selectedTags.has(entry.tag)" class="tag-filter-item" @change="emit('toggleTag', entry.tag)">
        <span>{{ entry.tag }}</span>
        <small>{{ entry.count }}</small>
      </el-checkbox>
      <p v-if="!tags.length" class="tag-filter-meta">{{ t("datasetEditor.tagFilter.empty") }}</p>
    </div>
    <small v-if="selectedTags.size" class="tag-filter-meta">{{ t("datasetEditor.tagFilter.selectedCount", { k: selectedTags.size }) }}</small>
    <el-input :model-value="excludeInput" :placeholder="t('datasetEditor.tagFilter.excludePlaceholder')" :title="t('datasetEditor.tagFilter.excludeTip')" @update:model-value="emit('update:excludeInput', $event)" />
    <div class="tag-filter-actions">
      <el-button :disabled="!selectedTags.size" @click="emit('clear')">{{ t("datasetEditor.tagFilter.clear") }}</el-button>
      <el-button v-if="showSelectAll" :disabled="!filteredCount" :title="t('datasetEditor.tagFilter.selectAllTip')" @click="emit('selectAll')">
        {{ t("datasetEditor.tagFilter.selectAll", { n: filteredCount }) }}
      </el-button>
    </div>
  </div>
</template>

\n