<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { useI18n } from "vue-i18n"
import { datasetApi, type ChangedItem, type DatasetHistory, type DatasetItem } from "../api/dataset"
import { schemasApi } from "../api/schemas"
import { addTagToCaption, removeTagFromCaption, splitCaptionTags } from "../dataset/caption"

const { t } = useI18n()

const QUICK_TAGS_KEY = "dataset-editor-quick-tags"
const PAGE_SIZE_KEY = "dataset-editor-page-size"
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
const appendPosition = ref<"front" | "back">("back")
const quickTag = ref("")
const newCaptionTag = ref("")
const quickTags = ref<string[]>([])
const page = ref(1)
const pageSize = ref(Number(localStorage.getItem(PAGE_SIZE_KEY)) || 48)
const historyOpen = ref(false)
const sessionHistory = ref<DatasetHistory>({ can_undo: false, can_redo: false, changes: [] })

const filtered = computed(() => items.value.filter((item) =>
  (!category.value || item.category === category.value) &&
  (!query.value || item.caption.toLowerCase().includes(query.value.toLowerCase()) || item.name.toLowerCase().includes(query.value.toLowerCase())),
))
const pageCount = computed(() => Math.max(1, Math.ceil(filtered.value.length / pageSize.value)))
const paged = computed(() => filtered.value.slice((page.value - 1) * pageSize.value, page.value * pageSize.value))
const current = computed(() => items.value.find((item) => item.relative_path === selected.value))
const targets = computed(() => selectedPaths.value.size ? items.value.filter((item) => selectedPaths.value.has(item.relative_path)) : filtered.value)
const popularTags = computed(() => tags.value.slice(0, 24))
const captionTags = computed(() => splitCaptionTags(caption.value))

function addCaptionTag() {
  const next = addTagToCaption(caption.value, newCaptionTag.value)
  if (next !== caption.value) caption.value = next
  newCaptionTag.value = ""
}

function removeCaptionTag(tag: string) {
  caption.value = removeTagFromCaption(caption.value, tag)
}

function choose(item: DatasetItem, event?: MouseEvent) {
  selected.value = item.relative_path
  caption.value = item.caption
  if (!event) return
  const index = filtered.value.findIndex((candidate) => candidate.relative_path === item.relative_path)
  const next = new Set(event.ctrlKey || event.metaKey || event.shiftKey ? selectedPaths.value : [])
  if (event.shiftKey && lastSelectedIndex.value !== undefined) {
    const [start, end] = [lastSelectedIndex.value, index].sort((a, b) => a - b)
    filtered.value.slice(start, end + 1).forEach((candidate) => next.add(candidate.relative_path))
  } else if ((event.ctrlKey || event.metaKey) && next.has(item.relative_path)) next.delete(item.relative_path)
  else next.add(item.relative_path)
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
    page.value = 1
    if (data.items[0]) choose(data.items[0])
    await refreshHistory()
    ElMessage.success(t("datasetEditor.scanMsg.loaded", { n: data.total }))
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : t("datasetEditor.scanMsg.fail")) }
  finally { loading.value = false }
}

async function save() {
  if (!current.value) return
  try {
    apply([await datasetApi.save(root.value, current.value.relative_path, caption.value)])
    await refreshHistory()
    ElMessage.success(t("datasetEditor.caption.saved"))
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : t("datasetEditor.caption.saveFail")) }
}

function splitTags(value: string) { return value.split(/[,，\n]/).map((item) => item.trim()).filter(Boolean) }

async function browsePath() {
  picking.value = true
  try { path.value = (await schemasApi.pickFile("folder")).path.replaceAll("\\", "/") }
  catch (error) { ElMessage.error(error instanceof Error ? error.message : t("schemaForm.pickFail")) }
  finally { picking.value = false }
}

async function batch() {
  if (!targets.value.length) return
  try {
    await ElMessageBox.confirm(t("datasetEditor.batch.confirm", { n: targets.value.length }), selectedPaths.value.size ? t("datasetEditor.batch.confirmSelected") : t("datasetEditor.batch.confirmFiltered"))
    const replacements = replaceFrom.value.trim() ? [{ from: replaceFrom.value.trim(), to: replaceTo.value.trim() }] : []
    const data = await datasetApi.batch({
      root: root.value, images: targets.value.map((item) => item.relative_path), append: splitTags(append.value), append_position: appendPosition.value, remove: splitTags(remove.value),
      replace: replacements, clean: clean.value, sort: sort.value, underscore_to_space: underscoreToSpace.value, strip_escape_chars: stripEscapeChars.value,
    })
    apply(data.items)
    await refreshHistory()
    ElMessage.success(t("datasetEditor.batch.done", { n: data.changed }))
  } catch (error) { if (error !== "cancel" && error !== "close") ElMessage.error(error instanceof Error ? error.message : t("datasetEditor.batch.fail")) }
}

async function changeHistory(kind: "undo" | "redo") {
  try {
    const data = await datasetApi[kind](root.value)
    apply(data.items)
    await refreshHistory()
    ElMessage.success(data.changed ? (kind === "undo" ? t("datasetEditor.historyMsg.undone") : t("datasetEditor.historyMsg.redone")) : t("datasetEditor.historyMsg.none"))
  } catch (error) { ElMessage.error(error instanceof Error ? error.message : t("datasetEditor.historyMsg.fail")) }
}

function togglePageSelection() {
  const next = new Set(selectedPaths.value)
  const allSelected = paged.value.every((item) => next.has(item.relative_path))
  paged.value.forEach((item) => allSelected ? next.delete(item.relative_path) : next.add(item.relative_path))
  selectedPaths.value = next
}

function appendQuickTag(tag: string) {
  const next = new Set(splitTags(append.value))
  next.add(tag)
  append.value = [...next].join(", ")
}

function addQuickTag() {
  const value = quickTag.value.trim()
  if (!value || quickTags.value.includes(value)) return
  quickTags.value.push(value)
  quickTag.value = ""
  localStorage.setItem(QUICK_TAGS_KEY, JSON.stringify(quickTags.value))
}

function removeQuickTag(tag: string) {
  quickTags.value = quickTags.value.filter((item) => item !== tag)
  localStorage.setItem(QUICK_TAGS_KEY, JSON.stringify(quickTags.value))
}

watch([category, query, pageSize], () => { page.value = 1; localStorage.setItem(PAGE_SIZE_KEY, String(pageSize.value)) })
watch(pageCount, (count) => { if (page.value > count) page.value = count })
onMounted(() => {
  try { quickTags.value = JSON.parse(localStorage.getItem(QUICK_TAGS_KEY) || "[]") }
  catch { quickTags.value = [] }
})
</script>

<template>
  <div class="dataset-page">
    <aside class="dataset-side">
      <span class="eyebrow">DATASET EDITOR</span><h1>{{ t("datasetEditor.title") }}</h1>
      <label>{{ t("datasetEditor.pathLabel") }}<span class="path-row"><input v-model="path" @keyup.enter="scan"><button :disabled="picking" @click.prevent="browsePath">{{ t("schemaForm.browse") }}</button></span></label>
      <button class="primary-action" :disabled="loading" @click="scan">{{ loading ? t("datasetEditor.scanning") : t("datasetEditor.scan") }}</button>
      <label>{{ t("datasetEditor.categoryLabel") }}<select v-model="category"><option value="">{{ t("datasetEditor.allCategories") }}</option><option v-for="item in categories" :key="item.value" :value="item.value">{{ item.name }} ({{ item.count }})</option></select></label>
      <label>{{ t("datasetEditor.queryLabel") }}<input v-model="query"></label>
      <div class="batch-box"><strong>{{ t("datasetEditor.batch.title") }} {{ selectedPaths.size ? t("datasetEditor.batch.selected", { n: selectedPaths.size }) : t("datasetEditor.batch.filtered", { n: filtered.length }) }}</strong><input v-model="append" :placeholder="t('datasetEditor.batch.appendPlaceholder')"><select v-model="appendPosition" :aria-label="t('datasetEditor.batch.position')"><option value="back">{{ t("datasetEditor.batch.positionBack") }}</option><option value="front">{{ t("datasetEditor.batch.positionFront") }}</option></select><input v-model="remove" :placeholder="t('datasetEditor.batch.removePlaceholder')"><div class="replace-row"><input v-model="replaceFrom" :placeholder="t('datasetEditor.batch.replaceFrom')"><input v-model="replaceTo" :placeholder="t('datasetEditor.batch.replaceTo')"></div><label><input v-model="clean" type="checkbox">{{ t("datasetEditor.batch.clean") }}</label><label><input v-model="underscoreToSpace" type="checkbox">{{ t("datasetEditor.batch.underscore") }}</label><label><input v-model="stripEscapeChars" type="checkbox">{{ t("datasetEditor.batch.stripEscape") }}</label><label><input v-model="sort" type="checkbox">{{ t("datasetEditor.batch.sort") }}</label><button @click="batch">{{ t("datasetEditor.batch.apply") }}</button></div>
      <div class="quick-tag-box"><strong>{{ t("datasetEditor.quickTag.title") }}</strong><div><button v-for="item in quickTags" :key="item" @click="appendQuickTag(item)" @contextmenu.prevent="removeQuickTag(item)">{{ item }}</button><button v-for="item in popularTags" :key="item.tag" class="suggested" @click="appendQuickTag(item.tag)">{{ item.tag }} <small>{{ item.count }}</small></button></div><span><input v-model="quickTag" :placeholder="t('datasetEditor.quickTag.addPlaceholder')" @keyup.enter="addQuickTag"><button @click="addQuickTag">{{ t("datasetEditor.quickTag.add") }}</button></span><small>{{ t("datasetEditor.quickTag.hint") }}</small></div>
    </aside>
    <main class="dataset-gallery">
      <header><strong>{{ t("datasetEditor.gallery.count", { filtered: filtered.length, total: items.length, selected: selectedPaths.size }) }}</strong><div><button :disabled="!root" @click="togglePageSelection">{{ t("datasetEditor.gallery.togglePage") }}</button><button :disabled="!sessionHistory.can_undo" @click="changeHistory('undo')">{{ t("datasetEditor.gallery.undo") }}</button><button :disabled="!sessionHistory.can_redo" @click="changeHistory('redo')">{{ t("datasetEditor.gallery.redo") }}</button><button :disabled="!root" @click="historyOpen = true">{{ t("datasetEditor.gallery.history") }}</button></div></header>
      <div v-if="!root" class="dataset-empty"><strong>{{ t("datasetEditor.gallery.emptyTitle") }}</strong><span>{{ t("datasetEditor.gallery.emptyHint") }}</span></div>
      <div v-else class="image-grid"><button v-for="item in paged" :key="item.relative_path" :class="{ active: selected === item.relative_path, checked: selectedPaths.has(item.relative_path) }" @click="choose(item, $event)"><i v-if="selectedPaths.has(item.relative_path)">✓</i><img :src="item.image_url" :alt="item.name" loading="lazy"><span>{{ item.name }}</span></button></div>
      <footer class="dataset-pager"><button :disabled="page === 1" @click="page = 1">{{ t("datasetEditor.pager.first") }}</button><button :disabled="page === 1" @click="page--">{{ t("datasetEditor.pager.prev") }}</button><span>{{ page }} / {{ pageCount }}</span><button :disabled="page === pageCount" @click="page++">{{ t("datasetEditor.pager.next") }}</button><button :disabled="page === pageCount" @click="page = pageCount">{{ t("datasetEditor.pager.last") }}</button><select v-model.number="pageSize"><option v-for="size in [24,48,96,192]" :key="size" :value="size">{{ t("datasetEditor.pager.perPage", { size }) }}</option></select></footer>
    </main>
    <aside class="caption-panel"><div v-if="current"><img :src="current.image_url" :alt="current.name"><strong>{{ current.relative_path }}</strong><div class="caption-editor"><textarea v-model="caption" rows="10"></textarea><small class="caption-count">{{ t("datasetEditor.caption.chars", { n: caption.length }) }}</small></div><div class="caption-chips"><span v-for="tag in captionTags" :key="tag" class="chip">{{ tag }}<button :aria-label="t('datasetEditor.caption.removeAria', { tag })" @click="removeCaptionTag(tag)">×</button></span><span class="chip-add"><input v-model="newCaptionTag" :placeholder="t('datasetEditor.caption.addPlaceholder')" @keyup.enter="addCaptionTag"><button @click="addCaptionTag">{{ t("datasetEditor.caption.add") }}</button></span></div><button class="primary-action" @click="save">{{ t("datasetEditor.caption.save") }}</button></div><p v-else>{{ t("datasetEditor.caption.empty") }}</p></aside>
  </div>
  <el-dialog v-model="historyOpen" :title="t('datasetEditor.historyDialog.title')" width="min(820px, 94vw)"><div class="dataset-history"><article v-for="change in sessionHistory.changes" :key="`${change.label}-${change.items[0]?.image}`"><header><strong>{{ change.label }}</strong><span>{{ t("datasetEditor.historyDialog.count", { n: change.count }) }}</span></header><details><summary>{{ t("datasetEditor.historyDialog.detail") }}</summary><div v-for="item in change.items" :key="item.image"><code>{{ item.image }}</code><del>{{ item.before || t('datasetEditor.historyDialog.noCaption') }}</del><ins>{{ item.after || t('datasetEditor.historyDialog.noCaption') }}</ins></div></details></article><p v-if="!sessionHistory.changes.length">{{ t("datasetEditor.historyDialog.empty") }}</p></div></el-dialog>
</template>
