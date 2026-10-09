<script setup lang="ts">
import { computed, onActivated, onBeforeUnmount, onDeactivated, ref, watch } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { useI18n } from "vue-i18n"
import { useRouter } from "vue-router"
import { FolderOpened, Folder, Search, MoreFilled, Fold, Expand, Warning, Loading, Refresh, Setting, Delete, Plus } from "@element-plus/icons-vue"
import { datasetsApi, type DatasetEntry, type DatasetOverview } from "../api/datasets"
import DatasetTrashDialog from "../components/dataset/DatasetTrashDialog.vue"
import DatasetDirectoryNode from "../components/dataset/DatasetDirectoryNode.vue"

const POLL_INTERVAL_MS = 1500
const READY_REFRESH_MS = 15000
const AUTO_REFRESH_KEY = "dataset-manage-auto-refresh"

const { t } = useI18n()
const router = useRouter()

const rootPath = ref("")
const rootExists = ref(true)
const datasets = ref<DatasetEntry[]>([])
const loading = ref(true)
const loadError = ref(false)
const refreshing = ref(false)
const rootDialogOpen = ref(false)
const rootInput = ref("")
const rootSaving = ref(false)
const createDialogOpen = ref(false)
const createName = ref("")
const creating = ref(false)
const trashOpen = ref(false)
const renaming = ref(false)
const autoRefresh = ref(localStorage.getItem(AUTO_REFRESH_KEY) === "1")
const treeOpen = ref(localStorage.getItem("dataset-tree-open") === "1"
  || (localStorage.getItem("dataset-tree-open") !== "0" && window.innerWidth > 760))
const search = ref("")
const sort = ref("updated")
watch(treeOpen, value => localStorage.setItem("dataset-tree-open", value ? "1" : "0"))
const visibleDatasets = computed(() => {
  const query = search.value.trim().toLocaleLowerCase()
  return datasets.value.filter(entry => entry.name.toLocaleLowerCase().includes(query)).sort((a, b) => {
    const value = (entry: DatasetEntry) => {
      if (sort.value === "images") return entry.overview?.file_count ?? -1
      if (sort.value === "created") return Date.parse(entry.created_at || "") || 0
      return Math.max(Date.parse(entry.overview?.updated_at || "") || 0, Date.parse(entry.updated_at || "") || 0)
    }
    return value(b) - value(a) || a.name.localeCompare(b.name)
  })
})
const rootLabel = computed(() => rootPath.value.replace(/\\/g, "/").split("/").filter(Boolean).pop() || "datasets")
function openDirectory(path: string) {
  const normalize = (value: string) => value.replace(/\\/g, "/").replace(/\/$/, "")
  const selected = normalize(path)
  const entry = datasets.value.find(item => selected === normalize(item.path) || selected.startsWith(`${normalize(item.path)}/`))
  if (!entry) return
  const directory = selected.slice(normalize(entry.path).length).replace(/^\//, "")
  void router.push({ path: "/dataset/manage", query: { dataset: entry.name, ...(directory ? { directory } : {}) } })
}
function entryAction(command: string, entry: DatasetEntry) {
  if (command === "manage") openDirectory(entry.path)
  else if (!entry.in_use) {
    if (command === "rename") void renameDataset(entry)
    else if (command === "delete") void deleteDataset(entry)
  }
}
let timer: number | undefined

function formatBytes(bytes: number | null | undefined) {
  if (bytes == null) return "-"
  if (bytes < 1024) return `${bytes} B`
  const units = ["KB", "MB", "GB", "TB"]
  let value = bytes / 1024
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${value.toFixed(value >= 100 ? 0 : 1)} ${units[unit]}`
}

function formatTime(iso: string | null | undefined) {
  if (!iso) return "-"
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? "-" : date.toLocaleString()
}

function overviewOf(entry: DatasetEntry): DatasetOverview | null {
  return entry.overview
}

function statValue(entry: DatasetEntry, field: "file_count" | "captioned_count" | "total_bytes" | "updated_at") {
  const overview = overviewOf(entry)
  if (!overview || overview.state !== "ready") return overview?.state === "error" ? "!" : "…"
  if (field === "total_bytes") return formatBytes(overview.total_bytes)
  if (field === "updated_at") return formatTime(overview.updated_at)
  return overview[field] ?? "-"
}

function needsPoll(entry: DatasetEntry) {
  const overview = entry.overview
  if (!overview || overview.state !== "ready") return true
  const computedAt = overview.computed_at ? Date.parse(overview.computed_at) : 0
  return Date.now() - computedAt > READY_REFRESH_MS
}

function hasUnsettled() {
  return datasets.value.some((entry) => !entry.overview || entry.overview.state === "computing")
}

async function refreshInUseFlags() {
  try {
    const data = await datasetsApi.list()
    const flags = new Map(data.datasets.map((item) => [item.name, item.in_use === true]))
    for (const entry of datasets.value) entry.in_use = flags.get(entry.name) ?? false
  } catch {}
}

async function pollOverviews(force = false) {
  const pending = force ? datasets.value : datasets.value.filter(needsPoll)
  await Promise.all([
    refreshInUseFlags(),
    ...pending.map(async (entry) => {
      try {
        const data = await datasetsApi.overview(entry.name, force)
        entry.overview = data.overview
      } catch {
        entry.overview = { state: "error", file_count: null, captioned_count: null, total_bytes: null, updated_at: null, error: "request failed" }
      }
    }),
  ])
  if (!autoRefresh.value && !hasUnsettled()) stopPolling()
}

function stopPolling() {
  window.clearInterval(timer)
  timer = undefined
}

function ensurePolling() {
  if (timer !== undefined) return
  timer = window.setInterval(() => void pollOverviews(), POLL_INTERVAL_MS)
}

watch(autoRefresh, (enabled) => {
  localStorage.setItem(AUTO_REFRESH_KEY, enabled ? "1" : "0")
  if (enabled) ensurePolling()
  else if (!hasUnsettled()) stopPolling()
})

async function load(silent = false) {
  if (refreshing.value) return
  loadError.value = false
  if (silent) refreshing.value = true
  else loading.value = true
  try {
    const data = await datasetsApi.list()
    rootPath.value = data.root
    rootExists.value = data.exists
    datasets.value = data.datasets
    void pollOverviews(true).then(() => {
      if (autoRefresh.value || hasUnsettled()) ensurePolling()
    })
  } catch (e) {
    loadError.value = true
    ElMessage.error(e instanceof Error ? e.message : t("datasetManage.msg.loadFail"))
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

function openRootDialog() {
  rootInput.value = rootPath.value
  rootDialogOpen.value = true
}

async function saveRoot() {
  if (!rootInput.value.trim() || rootSaving.value) return
  rootSaving.value = true
  try {
    const data = await datasetsApi.updateRoot(rootInput.value.trim())
    rootPath.value = data.root
    rootExists.value = data.exists
    rootDialogOpen.value = false
    ElMessage.success(t("datasetManage.msg.rootSaved"))
    await load(true)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : t("datasetManage.msg.rootSaveFail"))
  } finally {
    rootSaving.value = false
  }
}

async function createDataset() {
  const name = createName.value.trim()
  if (!name || creating.value) return
  creating.value = true
  try {
    await datasetsApi.create(name)
    createDialogOpen.value = false
    createName.value = ""
    ElMessage.success(t("datasetManage.msg.created"))
    await load(true)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : t("datasetManage.msg.createFail"))
  } finally {
    creating.value = false
  }
}

async function renameDataset(entry: DatasetEntry) {
  if (renaming.value) return
  let name: string
  try {
    const result = await ElMessageBox.prompt(t("datasetManage.rename"), {
      inputValue: entry.name,
      inputValidator: value => Boolean(value?.trim()) || t("datasetManage.createPlaceholder"),
    })
    name = result.value.trim()
  } catch { return }
  if (name === entry.name) return
  renaming.value = true
  try {
    await datasetsApi.rename(entry.name, name)
    ElMessage.success(t("datasetManage.renamed"))
    await load(true)
  } catch (caught) {
    ElMessage.error(caught instanceof Error ? caught.message : String(caught))
  } finally { renaming.value = false }
}

async function deleteDataset(entry: DatasetEntry) {
  try {
    await ElMessageBox.confirm(t("datasetManage.confirmDelete", { name: entry.name }), { type: "warning" })
  } catch {
    return
  }
  try {
    const data = await datasetsApi.deleteDataset(entry.name)
    ElMessage.success(t("datasetManage.msg.deleted", { n: data.deleted.length }))
    await load(true)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : t("datasetManage.msg.deleteFail"))
  }
}

function onUploaded() {
  void load(true)
}

onActivated(() => {
  void load()
})
onDeactivated(stopPolling)
onBeforeUnmount(stopPolling)
</script>

<template>
  <div class="dataset-manager-workspace" :class="{ 'tree-collapsed': !treeOpen }">
    <aside v-if="treeOpen" class="dataset-explorer" :aria-label="t('datasetManage.explorer')">
      <header><strong>{{ t("datasetManage.explorer") }}</strong><button class="dataset-icon-button" :title="t('datasetManage.collapseTree')" :aria-label="t('datasetManage.collapseTree')" @click="treeOpen = false"><Fold /></button></header>
      <div class="dataset-tree-root">
        <FolderOpened /><span :title="rootPath">{{ rootLabel }}</span>
        <button class="dataset-icon-button" :title="t('datasetManage.rootSettings')" :aria-label="t('datasetManage.rootSettings')" @click="openRootDialog"><Setting /></button>
      </div>
      <ul class="dataset-directory-tree">
        <DatasetDirectoryNode v-for="entry in datasets" :key="entry.path" :name="entry.name" :path="entry.path" :locked="entry.in_use" @select="openDirectory" />
      </ul>
      <button class="dataset-trash-link" @click="trashOpen = true"><Delete />{{ t("datasetManage.trash") }}</button>
    </aside>
    <main class="dataset-manage dataset-list-main">
      <header class="dataset-list-heading">
        <div>
          <button v-if="!treeOpen" class="dataset-icon-button" :title="t('datasetManage.explorer')" :aria-label="t('datasetManage.explorer')" @click="treeOpen = true"><Expand /></button>
          <h2>{{ t("datasetManage.title") }}</h2><span class="dataset-count">{{ datasets.length }}</span>
        </div>
        <button class="primary-action" :disabled="loading || loadError || !rootExists" @click="createDialogOpen = true"><Plus />{{ t("datasetManage.create") }}</button>
      </header>
      <div class="dataset-list-toolbar">
        <label class="dataset-search"><Search /><input v-model="search" :placeholder="t('datasetManage.search')" :aria-label="t('datasetManage.search')"></label>
        <select v-model="sort" :aria-label="t('datasetManage.sort')">
          <option value="updated">{{ t("datasetManage.sortUpdated") }}</option>
          <option value="created">{{ t("datasetManage.sortCreated") }}</option>
          <option value="images">{{ t("datasetManage.sortImages") }}</option>
        </select>
        <button class="dataset-icon-button" :title="t('datasetManage.refresh')" :aria-label="t('datasetManage.refresh')" :disabled="loading || refreshing" @click="load(true)"><Refresh :class="{ 'is-loading': refreshing }" /></button>
      </div>
      <div class="dataset-location-row">
        <button :title="rootPath" @click="openRootDialog"><FolderOpened /><span>{{ rootPath || rootLabel }}</span><Setting /></button>
        <label class="dataset-manage-autorefresh"><ElSwitch v-model="autoRefresh" /><span>{{ t("datasetManage.autoRefresh") }}</span></label>
      </div>

    <section
      v-if="loading || (!datasets.length && refreshing) || loadError || !rootExists || !datasets.length"
      class="dataset-manage-empty" role="status" aria-live="polite" :aria-busy="loading || refreshing">
      <div class="dataset-manage-empty-icon" aria-hidden="true">
        <Loading v-if="loading || (!datasets.length && refreshing)" class="is-loading" />
        <Warning v-else-if="loadError || !rootExists" />
        <FolderOpened v-else />
      </div>
      <h2>{{ t(loading || (!datasets.length && refreshing) ? "datasetManage.loadingTitle" : loadError ? "datasetManage.loadErrorTitle" : !rootExists ? "datasetManage.missingTitle" : "datasetManage.emptyTitle") }}</h2>
      <template v-if="!loading && !(!datasets.length && refreshing)">
        <p>{{ t(loadError ? "datasetManage.loadErrorHint" : !rootExists ? "datasetManage.missingHint" : "datasetManage.emptyHint") }}</p>
        <button v-if="loadError" class="primary-action" :disabled="refreshing" @click="load(true)"><Refresh />{{ t("datasetManage.retry") }}</button>
        <button v-else-if="!rootExists" class="primary-action" @click="openRootDialog"><Setting />{{ t("datasetManage.rootSettings") }}</button>
        <button v-else class="primary-action" @click="createDialogOpen = true"><Plus />{{ t("datasetManage.create") }}</button>
      </template>
    </section>

    <div v-else class="dataset-table-scroll">
      <table class="dataset-table">
        <thead><tr><th>{{ t("datasetManage.name") }}</th><th>{{ t("datasetManage.files") }}</th><th>{{ t("datasetManage.captioned") }}</th><th>{{ t("datasetManage.updatedAt") }}</th><th><span class="dataset-visually-hidden">{{ t("datasetManage.actions") }}</span></th></tr></thead>
        <tbody>
          <tr v-for="entry in visibleDatasets" :key="entry.name">
            <td><button class="dataset-row-name" :disabled="entry.in_use" :title="entry.path" @click="openDirectory(entry.path)"><Folder /><span>{{ entry.name }}</span></button><span v-if="entry.in_use" class="dataset-card-in-use">{{ t("datasetManage.inUse") }}</span></td>
            <td>{{ statValue(entry, "file_count") }}</td>
            <td>{{ statValue(entry, "captioned_count") }}</td>
            <td>{{ statValue(entry, "updated_at") }}</td>
            <td><ElDropdown trigger="click" @command="entryAction($event, entry)">
              <button class="dataset-icon-button" :aria-label="t('datasetManage.actions') + ': ' + entry.name" :title="t('datasetManage.actions')"><MoreFilled /></button>
              <template #dropdown><ElDropdownMenu>
                <ElDropdownItem command="manage">{{ t("datasetManage.manage") }}</ElDropdownItem>
                <ElDropdownItem command="rename" :disabled="entry.in_use || renaming">{{ t("datasetManage.rename") }}</ElDropdownItem>
                <ElDropdownItem command="delete" :disabled="entry.in_use" divided>{{ t("datasetManage.deleteDataset") }}</ElDropdownItem>
              </ElDropdownMenu></template>
            </ElDropdown></td>
          </tr>
          <tr v-if="!visibleDatasets.length"><td colspan="5" class="dataset-no-results">{{ t("datasetManage.noResults") }}</td></tr>
        </tbody>
      </table>
    </div>
    <footer v-if="datasets.length && !loadError" class="dataset-list-count">{{ t("datasetManage.total", { n: visibleDatasets.length }) }}</footer>
    </main>

    <ElDialog v-model="rootDialogOpen" :title="t('datasetManage.rootDialogTitle')" width="480px">
      <ElInput v-model="rootInput" :placeholder="t('datasetManage.rootDialogPlaceholder')" @keyup.enter="saveRoot" />
      <p class="dataset-manage-dialog-hint">{{ t("datasetManage.rootDialogHint") }}</p>
      <template #footer>
        <button class="secondary-action" @click="rootDialogOpen = false">{{ t("datasetManage.cancel") }}</button>
        <button class="primary-action" :disabled="rootSaving || !rootInput.trim()" @click="saveRoot">{{ t("datasetManage.save") }}</button>
      </template>
    </ElDialog>

    <DatasetTrashDialog
      :model-value="trashOpen"
      @update:model-value="trashOpen = $event"
      @changed="onUploaded"
    />

    <ElDialog v-model="createDialogOpen" :title="t('datasetManage.createDialogTitle')" width="480px">
      <ElInput v-model="createName" :placeholder="t('datasetManage.createPlaceholder')" @keyup.enter="createDataset" />
      <template #footer>
        <button class="secondary-action" @click="createDialogOpen = false">{{ t("datasetManage.cancel") }}</button>
        <button class="primary-action" :disabled="creating || !createName.trim()" @click="createDataset">{{ t("datasetManage.createConfirm") }}</button>
      </template>
    </ElDialog>
  </div>
</template>
