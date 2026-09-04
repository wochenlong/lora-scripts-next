<script setup lang="ts">
import { computed, onActivated, onDeactivated, onUnmounted, ref, watch } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { useI18n } from "vue-i18n"
import { datasetApi, type ChangedItem, type DatasetHistory, type DatasetItem } from "../api/dataset"
import TagFilterPanel from "../components/dataset/TagFilterPanel.vue"
import PathPickerDialog from "../components/PathPickerDialog.vue"
import { useDatasetTagFilter } from "../composables/useDatasetTagFilter"
import { useServerPathPick } from "../composables/useServerPathPick"
import { addTagToCaption, moveCaptionTag, removeTagFromCaption, splitCaptionTags } from "../dataset/caption"

const { t } = useI18n()

type RightPanelMode = "caption" | "filter" | "batch"

const PAGE_SIZE_KEY = "dataset-editor-page-size"
const DRAWER_WIDTH = "380px"
const path = ref("")
const root = ref("")
const items = ref<DatasetItem[]>([])
const tags = ref<Array<{ tag: string; count: number }>>([])
const categories = ref<Array<{ name: string; value: string; count: number }>>([])
const category = ref("")
const query = ref("")
const selected = ref("")
const selectedPaths = ref(new Set<string>())
const lastSelectedIndex = ref<number>()
const caption = ref("")
const append = ref("")
const remove = ref("")
const replaceFrom = ref("")
const replaceTo = ref("")
const clean = ref(false)
const sort = ref(false)
const underscoreToSpace = ref(false)
const stripEscapeChars = ref(false)
const loading = ref(false)
const picking = ref(false)
const {
  open: pathPickerOpen,
  mode: pathPickerMode,
  initialPath: pathPickerInitial,
  nameFilter: pathPickerFilter,
  pick: pickServerPath,
  onConfirm: onPathConfirm,
  onCancel: onPathCancel,
} = useServerPathPick()
const appendPosition = ref<"front" | "back">("back")
const newCaptionTag = ref("")
const page = ref(1)
const pageSize = ref(Number(localStorage.getItem(PAGE_SIZE_KEY)) || 48)
const historyOpen = ref(false)
const rightPanelMode = ref<RightPanelMode>("caption")
const selectMenuOpen = ref(false)
const sessionHistory = ref<DatasetHistory>({ can_undo: false, can_redo: false, changes: [] })
const previewOpen = ref(false)

function onPreviewKeydown(event: KeyboardEvent) {
  if (event.key !== "Escape") return
  previewOpen.value = false
  selectMenuOpen.value = false
  if (rightPanelMode.value !== "caption") rightPanelMode.value = "caption"
}

const { state: tagFilter, filteredItems: tagFilteredItems, visibleTagList, hasActiveFilter, toggleTag, clearTags, reset: resetTagFilter } =
  useDatasetTagFilter(items, tags)

const filtered = computed(() =>
  tagFilteredItems.value.filter(
    (item) =>
      (!category.value || item.category === category.value) &&
      (!query.value ||
        item.caption.toLowerCase().includes(query.value.toLowerCase()) ||
        item.name.toLowerCase().includes(query.value.toLowerCase()) ||
        item.tags.some((tag) => tag.toLowerCase().includes(query.value.toLowerCase()))),
  ),
)
const pageCount = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize.value)))
const paged = computed(() => filtered.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))
const current = computed(() => items.value.find((item) => item.relative_path === selected.value))
const targets = computed(() =>
  selectedPaths.value.size ? items.value.filter((item) => selectedPaths.value.has(item.relative_path)) : filtered.value,
)
const captionTags = computed(() => splitCaptionTags(caption.value))
const hasWorkingFilter = computed(
  () => Boolean(category.value) || Boolean(query.value.trim()) || hasActiveFilter.value,
)
const totalImageCount = computed(() => items.value.length)
const workingScopeCount = computed(() => filtered.value.length)
const workingScopeFullySelected = computed(
  () =>
    filtered.value.length > 0 &&
    filtered.value.every((item) => selectedPaths.value.has(item.relative_path)),
)
const selectAllLabel = computed(() =>
  workingScopeFullySelected.value
    ? t("datasetEditor.gallery.deselectAll", { n: workingScopeCount.value })
    : hasWorkingFilter.value
      ? t("datasetEditor.gallery.selectFiltered", { n: workingScopeCount.value })
      : t("datasetEditor.gallery.selectAll", { n: workingScopeCount.value }),
)
const panelTitle = computed(() => {
  if (rightPanelMode.value === "filter") return t("datasetEditor.filter.drawerTitle")
  if (rightPanelMode.value === "batch") {
    return selectedPaths.value.size
      ? t("datasetEditor.batch.drawerTitleSelected", { n: selectedPaths.value.size })
      : t("datasetEditor.batch.drawerTitle")
  }
  return t("datasetEditor.caption.panelTitle")
})

function openRightPanel(mode: RightPanelMode) {
  rightPanelMode.value = rightPanelMode.value === mode && mode !== "caption" ? "caption" : mode
}

function closeToolPanel() {
  rightPanelMode.value = "caption"
}

function addCaptionTag() {
  const next = addTagToCaption(caption.value, newCaptionTag.value)
  if (next !== caption.value) caption.value = next
  newCaptionTag.value = ""
}

function removeCaptionTag(tag: string) {
  caption.value = removeTagFromCaption(caption.value, tag)
}

const dragTagIndex = ref<number | null>(null)

function onChipDragStart(index: number, event: DragEvent) {
  dragTagIndex.value = index
  event.dataTransfer?.setData("text/plain", String(index))
  if (event.dataTransfer) event.dataTransfer.effectAllowed = "move"
}

function onChipDragOver(event: DragEvent) {
  event.preventDefault()
  if (event.dataTransfer) event.dataTransfer.dropEffect = "move"
}

function onChipDrop(toIndex: number, event: DragEvent) {
  event.preventDefault()
  const from = dragTagIndex.value
  dragTagIndex.value = null
  if (from == null || from === toIndex) return
  caption.value = moveCaptionTag(caption.value, from, toIndex)
}

function onChipDragEnd() {
  dragTagIndex.value = null
}

function choose(item: DatasetItem, event?: MouseEvent) {
  selected.value = item.relative_path
  caption.value = item.caption
  rightPanelMode.value = "caption"
  if (!event) return
  const index = filtered.value.findIndex((candidate) => candidate.relative_path === item.relative_path)
  const multi = event.ctrlKey || event.metaKey || event.shiftKey
  const next = new Set(multi ? selectedPaths.value : [])
  if (event.shiftKey && lastSelectedIndex.value !== undefined) {
    const [start, end] = [lastSelectedIndex.value, index].sort((a, b) => a - b)
    filtered.value.slice(start, end + 1).forEach((candidate) => next.add(candidate.relative_path))
  } else if (multi) {
    if (next.has(item.relative_path)) next.delete(item.relative_path)
    else next.add(item.relative_path)
  } else if (selectedPaths.value.has(item.relative_path) && selectedPaths.value.size === 1) {
    // Plain click on the only selected image toggles it off.
  } else {
    next.add(item.relative_path)
  }
  selectedPaths.value = next
  lastSelectedIndex.value = index
}

function apply(changes: ChangedItem[]) {
  const map = new Map(changes.map((item) => [item.image, item]))
  items.value = items.value.map((item) => {
    const change = map.get(item.relative_path)
    return change ? { ...item, caption: change.caption, tags: change.tags, caption_exists: change.caption_exists } : item
  })
  if (current.value) caption.value = current.value.caption
  rebuildTags()
}

function rebuildTags() {
  const counts = new Map<string, number>()
  items.value.forEach((item) => item.tags.forEach((tag) => counts.set(tag, (counts.get(tag) || 0) + 1)))
  tags.value = [...counts].map(([tag, count]) => ({ tag, count })).sort((a, b) => b.count - a.count || a.tag.localeCompare(b.tag))
}

async function refreshHistory() {
  if (root.value) sessionHistory.value = await datasetApi.history(root.value)
}

async function scan() {
  if (!path.value.trim()) return
  loading.value = true
  try {
    const data = await datasetApi.scan(path.value)
    root.value = data.root
    path.value = data.root
    items.value = data.items
    tags.value = data.tags.sort((a, b) => b.count - a.count)
    categories.value = data.categories
    selectedPaths.value = new Set()
    category.value = ""
    query.value = ""
    resetTagFilter()
    page.value = 1
    rightPanelMode.value = "caption"
    if (data.items[0]) choose(data.items[0])
    await refreshHistory()
    ElMessage.success(t("datasetEditor.scanMsg.loaded", { n: data.total }))
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t("datasetEditor.scanMsg.fail"))
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!current.value) return
  try {
    apply([await datasetApi.save(root.value, current.value.relative_path, caption.value)])
    await refreshHistory()
    ElMessage.success(t("datasetEditor.caption.saved"))
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t("datasetEditor.caption.saveFail"))
  }
}

function splitTags(value: string) {
  return value.split(/[,，\n]/).map((item) => item.trim()).filter(Boolean)
}

async function browsePath() {
  picking.value = true
  try {
    const next = await pickServerPath({ mode: "folder", initialPath: path.value })
    if (next) path.value = next
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t("schemaForm.pickFail"))
  } finally {
    picking.value = false
  }
}

async function batch() {
  if (!targets.value.length) return
  try {
    await ElMessageBox.confirm(
      t("datasetEditor.batch.confirm", { n: targets.value.length }),
      selectedPaths.value.size ? t("datasetEditor.batch.confirmSelected") : t("datasetEditor.batch.confirmFiltered"),
    )
    const replacements = replaceFrom.value.trim() ? [{ from: replaceFrom.value.trim(), to: replaceTo.value.trim() }] : []
    const data = await datasetApi.batch({
      root: root.value,
      images: targets.value.map((item) => item.relative_path),
      append: splitTags(append.value),
      append_position: appendPosition.value,
      remove: splitTags(remove.value),
      replace: replacements,
      clean: clean.value,
      sort: sort.value,
      underscore_to_space: underscoreToSpace.value,
      strip_escape_chars: stripEscapeChars.value,
    })
    apply(data.items)
    await refreshHistory()
    ElMessage.success(t("datasetEditor.batch.done", { n: data.changed }))
    rightPanelMode.value = "caption"
  } catch (error) {
    if (error !== "cancel" && error !== "close") ElMessage.error(error instanceof Error ? error.message : t("datasetEditor.batch.fail"))
  }
}

async function changeHistory(kind: "undo" | "redo") {
  try {
    const data = await datasetApi[kind](root.value)
    apply(data.items)
    await refreshHistory()
    ElMessage.success(
      data.changed
        ? kind === "undo"
          ? t("datasetEditor.historyMsg.undone")
          : t("datasetEditor.historyMsg.redone")
        : t("datasetEditor.historyMsg.none"),
    )
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t("datasetEditor.historyMsg.fail"))
  }
}

function selectWorkingScope() {
  if (workingScopeFullySelected.value) selectedPaths.value = new Set()
  else selectedPaths.value = new Set(filtered.value.map((item) => item.relative_path))
  selectMenuOpen.value = false
}

function selectEntireDataset() {
  selectedPaths.value = new Set(items.value.map((item) => item.relative_path))
  selectMenuOpen.value = false
}

function selectCurrentPageOnly() {
  selectedPaths.value = new Set(paged.value.map((item) => item.relative_path))
  selectMenuOpen.value = false
}

function clearSelection() {
  selectedPaths.value = new Set()
  selectMenuOpen.value = false
}

function clearAllFilters() {
  category.value = ""
  query.value = ""
  clearTags()
  tagFilter.excludeInput = ""
  tagFilter.logic = "and"
}

watch([category, query, pageSize], () => {
  page.value = 1
  localStorage.setItem(PAGE_SIZE_KEY, String(pageSize.value))
})
watch(() => [tagFilter.logic, tagFilter.selectedTags.size, tagFilter.excludeInput], () => {
  page.value = 1
})
watch(pageCount, (count) => {
  if (page.value > count) page.value = count
})
onActivated(() => window.addEventListener("keydown", onPreviewKeydown))
onDeactivated(() => {
  window.removeEventListener("keydown", onPreviewKeydown)
  previewOpen.value = false
  selectMenuOpen.value = false
  historyOpen.value = false
})
onUnmounted(() => window.removeEventListener("keydown", onPreviewKeydown))
</script>

<template>
  <div class="dataset-page" :class="{ 'tool-panel-open': rightPanelMode !== 'caption' || Boolean(current) }">
    <div class="dataset-workspace">
      <header class="dataset-toolbar">
        <label class="dataset-toolbar-field dataset-toolbar-path">
          <span>{{ t("datasetEditor.pathLabel") }}</span>
          <span class="path-row">
            <input v-model="path" :placeholder="t('datasetEditor.toolbar.pathPlaceholder')" @keyup.enter="scan">
            <button
              type="button"
              class="dataset-browse-icon"
              :disabled="picking"
              :title="t('datasetEditor.toolbar.browseTip')"
              :aria-label="t('datasetEditor.toolbar.browseTip')"
              @click.prevent="browsePath"
            >
              <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <path d="M3 7.5A1.5 1.5 0 0 1 4.5 6H9l1.8 2.2H19.5A1.5 1.5 0 0 1 21 9.7v7.8a1.5 1.5 0 0 1-1.5 1.5h-15A1.5 1.5 0 0 1 3 17.5z" />
              </svg>
            </button>
            <button type="button" class="primary-action dataset-toolbar-scan" :disabled="loading" @click="scan">
              {{ loading ? t("datasetEditor.scanning") : t("datasetEditor.scan") }}
            </button>
          </span>
        </label>
        <label class="dataset-toolbar-field dataset-toolbar-folder">
          <span>{{ t("datasetEditor.toolbar.folderLabel") }}</span>
          <select v-model="category" :disabled="!root">
            <option value="">{{ t("datasetEditor.toolbar.folderAll", { n: totalImageCount || 0 }) }}</option>
            <option v-for="item in categories" :key="`tb-${item.value || '__root__'}`" :value="item.value">
              {{ item.name }} ({{ item.count }})
            </option>
          </select>
        </label>
        <label class="dataset-toolbar-field dataset-toolbar-search">
          <span>{{ t("datasetEditor.toolbar.searchLabel") }}</span>
          <input v-model="query" :placeholder="t('datasetEditor.filter.queryPlaceholder')" :disabled="!root">
        </label>
        <div class="dataset-toolbar-actions">
          <button
            type="button"
            class="dataset-tool-entry"
            :class="{ active: rightPanelMode === 'filter', hot: hasWorkingFilter }"
            :disabled="!root"
            @click="openRightPanel('filter')"
          >
            {{ t("datasetEditor.filter.toggle") }}
            <small v-if="hasWorkingFilter">{{ t("datasetEditor.filter.activeBadge") }}</small>
          </button>
          <button
            type="button"
            class="dataset-tool-entry dataset-batch-entry"
            :class="{ active: rightPanelMode === 'batch' || selectedPaths.size > 0 }"
            :disabled="!root"
            @click="openRightPanel('batch')"
          >
            {{ t("datasetEditor.batch.toolbar", { n: selectedPaths.size }) }}
          </button>
          <button type="button" :disabled="!sessionHistory.can_undo" @click="changeHistory('undo')">{{ t("datasetEditor.gallery.undo") }}</button>
          <button type="button" :disabled="!sessionHistory.can_redo" @click="changeHistory('redo')">{{ t("datasetEditor.gallery.redo") }}</button>
          <button type="button" :disabled="!root" @click="historyOpen = true">{{ t("datasetEditor.gallery.history") }}</button>
        </div>
      </header>

      <main class="dataset-gallery">
        <header class="dataset-gallery-bar">
          <strong>{{ t("datasetEditor.gallery.count", { n: items.length, filtered: filtered.length, total: items.length, selected: t("datasetEditor.batch.selected", { n: selectedPaths.size }) }) }}</strong>
          <div class="dataset-select-scope" :class="{ open: selectMenuOpen }">
            <button
              type="button"
              class="dataset-select-main"
              :class="{ active: workingScopeFullySelected }"
              :disabled="!root || !filtered.length"
              @click="selectWorkingScope"
            >
              {{ selectAllLabel }}
            </button>
            <button
              type="button"
              class="dataset-select-caret"
              :disabled="!root"
              :aria-label="t('datasetEditor.gallery.selectMenuAria')"
              :aria-expanded="selectMenuOpen"
              @click="selectMenuOpen = !selectMenuOpen"
            >
              ▼
            </button>
            <div v-if="selectMenuOpen" class="dataset-select-menu" role="menu">
              <button type="button" role="menuitem" :disabled="!items.length" @click="selectEntireDataset">
                {{ t("datasetEditor.gallery.selectEntire", { n: totalImageCount }) }}
              </button>
              <button type="button" role="menuitem" :disabled="!filtered.length" @click="selectWorkingScope">
                {{ t("datasetEditor.gallery.selectFiltered", { n: workingScopeCount }) }}
              </button>
              <button type="button" role="menuitem" :disabled="!paged.length" @click="selectCurrentPageOnly">
                {{ t("datasetEditor.gallery.selectPage", { n: paged.length }) }}
              </button>
              <button type="button" role="menuitem" :disabled="!selectedPaths.size" @click="clearSelection">
                {{ t("datasetEditor.gallery.clearSelection") }}
              </button>
            </div>
          </div>
        </header>
        <div v-if="!root" class="dataset-empty">
          <strong>{{ t("datasetEditor.gallery.emptyTitle") }}</strong>
          <span>{{ t("datasetEditor.gallery.emptyHint") }}</span>
        </div>
        <div v-else class="image-grid">
          <button
            v-for="item in paged"
            :key="item.relative_path"
            type="button"
            :class="{ active: selected === item.relative_path, checked: selectedPaths.has(item.relative_path) }"
            @click="choose(item, $event)"
          >
            <i v-if="selectedPaths.has(item.relative_path)">✓</i>
            <img :src="item.thumb_url" :alt="item.name" loading="lazy">
            <span>{{ item.name }}</span>
          </button>
        </div>
        <footer class="dataset-pager">
          <button type="button" :disabled="page === 1" @click="page = 1">{{ t("datasetEditor.pager.first") }}</button>
          <button type="button" :disabled="page === 1" @click="page--">{{ t("datasetEditor.pager.prev") }}</button>
          <span>{{ page }} / {{ pageCount }}</span>
          <button type="button" :disabled="page === pageCount" @click="page++">{{ t("datasetEditor.pager.next") }}</button>
          <button type="button" :disabled="page === pageCount" @click="page = pageCount">{{ t("datasetEditor.pager.last") }}</button>
          <select v-model.number="pageSize">
            <option v-for="size in [24, 48, 96, 192]" :key="size" :value="size">{{ t("datasetEditor.pager.perPage", { size }) }}</option>
          </select>
        </footer>
      </main>
    </div>

    <aside
      class="dataset-tool-panel"
      :class="[`is-${rightPanelMode}`, { glass: rightPanelMode !== 'caption' }]"
      :style="{ width: DRAWER_WIDTH }"
      :aria-label="panelTitle"
    >
      <header class="dataset-tool-panel-header">
        <strong>{{ panelTitle }}</strong>
        <button
          v-if="rightPanelMode !== 'caption'"
          type="button"
          class="dataset-tool-panel-close"
          :aria-label="t('datasetEditor.filter.close')"
          @click="closeToolPanel"
        >
          ×
        </button>
      </header>

      <div v-if="rightPanelMode === 'caption'" class="dataset-tool-panel-body caption-panel">
        <div v-if="current">
          <img
            class="caption-preview"
            :src="current.thumb_url + '&size=512'"
            :alt="current.name"
            :title="t('datasetEditor.caption.previewTip')"
            @click="previewOpen = true"
          >
          <span class="caption-filename" :title="current.relative_path">{{ current.name }}</span>
          <div class="caption-chips" @dragover="onChipDragOver">
            <span
              v-for="(tag, index) in captionTags"
              :key="`${index}:${tag}`"
              class="chip"
              :class="{ dragging: dragTagIndex === index }"
              draggable="true"
              :title="t('datasetEditor.caption.dragTip')"
              @dragstart="onChipDragStart(index, $event)"
              @drop="onChipDrop(index, $event)"
              @dragend="onChipDragEnd"
            >
              {{ tag }}
              <button type="button" :aria-label="t('datasetEditor.caption.removeAria', { tag })" @click="removeCaptionTag(tag)" @mousedown.stop>×</button>
            </span>
            <span class="chip-add">
              <input v-model="newCaptionTag" :placeholder="t('datasetEditor.caption.addPlaceholder')" @keyup.enter="addCaptionTag">
              <button type="button" @click="addCaptionTag">{{ t("datasetEditor.caption.add") }}</button>
            </span>
          </div>
          <small class="caption-drag-hint">{{ t("datasetEditor.caption.dragHint") }}</small>
          <details class="caption-raw">
            <summary>{{ t("datasetEditor.caption.rawToggle") }}</summary>
            <div class="caption-editor">
              <textarea v-model="caption" rows="8"></textarea>
              <small class="caption-count">{{ t("datasetEditor.caption.chars", { n: caption.length }) }}</small>
            </div>
          </details>
          <button type="button" class="primary-action" @click="save">{{ t("datasetEditor.caption.save") }}</button>
        </div>
        <p v-else>{{ t("datasetEditor.caption.empty") }}</p>
      </div>

      <div v-else-if="rightPanelMode === 'filter'" class="dataset-tool-panel-body dataset-filter-body">
        <label>
          {{ t("datasetEditor.queryLabel") }}
          <input v-model="query" :placeholder="t('datasetEditor.filter.queryPlaceholder')">
        </label>
        <label>
          {{ t("datasetEditor.categoryLabel") }}
          <select v-model="category">
            <option value="">{{ t("datasetEditor.allCategories") }} ({{ totalImageCount }})</option>
            <option v-for="item in categories" :key="item.value || '__root__'" :value="item.value">
              {{ item.name }} ({{ item.count }})
            </option>
          </select>
        </label>
        <TagFilterPanel
          :tags="visibleTagList"
          :selected-tags="tagFilter.selectedTags"
          :logic="tagFilter.logic"
          :search="tagFilter.search"
          :search-mode="tagFilter.searchMode"
          :sort-by="tagFilter.sortBy"
          :order="tagFilter.order"
          :exclude-input="tagFilter.excludeInput"
          :filtered-count="filtered.length"
          :show-select-all="false"
          @update:logic="tagFilter.logic = $event"
          @update:search="tagFilter.search = $event"
          @update:search-mode="tagFilter.searchMode = $event"
          @update:sort-by="tagFilter.sortBy = $event"
          @update:order="tagFilter.order = $event"
          @update:exclude-input="tagFilter.excludeInput = $event"
          @toggle-tag="toggleTag"
          @clear="clearTags"
        />
        <div class="dataset-tool-panel-footer">
          <button type="button" class="dataset-tool-secondary" :disabled="!hasWorkingFilter" @click="clearAllFilters">
            {{ t("datasetEditor.filter.clearAll") }}
          </button>
          <button type="button" class="primary-action" @click="closeToolPanel">{{ t("datasetEditor.filter.done") }}</button>
        </div>
      </div>

      <div v-else class="dataset-tool-panel-body batch-body">
        <p class="dataset-batch-summary">
          {{
            selectedPaths.size
              ? t("datasetEditor.batch.selected", { n: selectedPaths.size })
              : t("datasetEditor.batch.filtered", { n: filtered.length })
          }}
        </p>
        <input v-model="append" :placeholder="t('datasetEditor.batch.appendPlaceholder')">
        <select v-model="appendPosition" :aria-label="t('datasetEditor.batch.position')">
          <option value="back">{{ t("datasetEditor.batch.positionBack") }}</option>
          <option value="front">{{ t("datasetEditor.batch.positionFront") }}</option>
        </select>
        <input v-model="remove" :placeholder="t('datasetEditor.batch.removePlaceholder')">
        <div class="replace-row">
          <input v-model="replaceFrom" :placeholder="t('datasetEditor.batch.replaceFrom')">
          <input v-model="replaceTo" :placeholder="t('datasetEditor.batch.replaceTo')">
        </div>
        <label><input v-model="clean" type="checkbox">{{ t("datasetEditor.batch.clean") }}</label>
        <label><input v-model="underscoreToSpace" type="checkbox">{{ t("datasetEditor.batch.underscore") }}</label>
        <label><input v-model="stripEscapeChars" type="checkbox">{{ t("datasetEditor.batch.stripEscape") }}</label>
        <label><input v-model="sort" type="checkbox">{{ t("datasetEditor.batch.sort") }}</label>
        <div class="dataset-tool-panel-footer">
          <button type="button" class="dataset-tool-secondary" @click="closeToolPanel">{{ t("datasetEditor.batch.cancel") }}</button>
          <button type="button" class="primary-action" :disabled="!targets.length" @click="batch">
            {{ t("datasetEditor.batch.applyTo", { n: targets.length }) }}
          </button>
        </div>
      </div>
    </aside>
  </div>

  <div
    v-if="previewOpen && current"
    class="dataset-lightbox"
    role="dialog"
    :aria-label="t('datasetEditor.caption.previewAria')"
    @click="previewOpen = false"
  >
    <img :src="current.image_url" :alt="current.name">
  </div>

  <el-dialog v-model="historyOpen" :title="t('datasetEditor.historyDialog.title')" width="min(820px, 94vw)">
    <div class="dataset-history">
      <article v-for="change in sessionHistory.changes" :key="`${change.label}-${change.items[0]?.image}`">
        <header>
          <strong>{{ change.label }}</strong>
          <span>{{ t("datasetEditor.historyDialog.count", { n: change.count }) }}</span>
        </header>
        <details>
          <summary>{{ t("datasetEditor.historyDialog.detail") }}</summary>
          <div v-for="item in change.items" :key="item.image">
            <code>{{ item.image }}</code>
            <del>{{ item.before || t("datasetEditor.historyDialog.noCaption") }}</del>
            <ins>{{ item.after || t("datasetEditor.historyDialog.noCaption") }}</ins>
          </div>
        </details>
      </article>
      <p v-if="!sessionHistory.changes.length">{{ t("datasetEditor.historyDialog.empty") }}</p>
    </div>
  </el-dialog>

  <PathPickerDialog
    v-model="pathPickerOpen"
    :mode="pathPickerMode"
    :initial-path="pathPickerInitial"
    :name-filter="pathPickerFilter"
    @confirm="onPathConfirm"
    @cancel="onPathCancel"
  />
</template>
