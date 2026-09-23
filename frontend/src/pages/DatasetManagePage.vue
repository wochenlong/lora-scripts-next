<script setup lang="ts">
import { onActivated, onBeforeUnmount, onDeactivated, ref, watch } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { useI18n } from "vue-i18n"
import { useRouter } from "vue-router"
import { datasetDownloadUrl, datasetsApi, type DatasetEntry, type DatasetOverview } from "../api/datasets"
import DatasetTrashDialog from "../components/dataset/DatasetTrashDialog.vue"
import DatasetUploadDialog from "../components/dataset/DatasetUploadDialog.vue"

const POLL_INTERVAL_MS = 1500
const READY_REFRESH_MS = 15000
const AUTO_REFRESH_KEY = "dataset-manage-auto-refresh"

const { t } = useI18n()
const router = useRouter()

const rootPath = ref("")
const rootExists = ref(true)
const datasets = ref<DatasetEntry[]>([])
const loading = ref(false)
const refreshing = ref(false)
const rootDialogOpen = ref(false)
const rootInput = ref("")
const rootSaving = ref(false)
const createDialogOpen = ref(false)
const createName = ref("")
const creating = ref(false)
const uploadTarget = ref("")
const trashOpen = ref(false)
const autoRefresh = ref(localStorage.getItem(AUTO_REFRESH_KEY) === "1")
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

function statValue(entry: DatasetEntry, field: "file_count" | "captioned_count" | "paired_count" | "total_bytes" | "updated_at") {
  const overview = overviewOf(entry)
  if (!overview || overview.state !== "ready") return overview?.state === "error" ? "!" : "…"
  if (field === "total_bytes") return formatBytes(overview.total_bytes)
  if (field === "updated_at") return formatTime(overview.updated_at)
  return overview[field] ?? "-"
}

function isEditDataset(entry: DatasetEntry) {
  const overview = overviewOf(entry)
  return overview?.state === "ready" && overview.type === "image_edit" && !!overview.targets
}

function typeBadge(entry: DatasetEntry) {
  const overview = overviewOf(entry)
  if (!overview || overview.state !== "ready" || !overview.type) return null
  if (overview.type === "image_edit" && (overview.type_confidence === "detected" || overview.type_confidence === "override"))
    return { label: t("datasetManage.typeImageEdit"), kind: "edit", title: "" }
  if (overview.type === "image_edit")
    return { label: t("datasetManage.typeImageEdit"), kind: "uncertain", title: overview.error || t("datasetManage.typeUncertain") }
  if (overview.type_confidence === "candidate")
    return { label: t("datasetManage.typeUncertain"), kind: "uncertain", title: t("datasetManage.typeUncertain") }
  return { label: t("datasetManage.typeImage"), kind: "image", title: "" }
}

function pairingWarning(entry: DatasetEntry) {
  const overview = overviewOf(entry)
  if (!isEditDataset(entry) || !overview) return ""
  const parts: string[] = []
  if ((overview.unpaired_count ?? 0) > 0) parts.push(t("datasetManage.unpaired", { n: overview.unpaired_count }))
  if ((overview.orphan_ref_count ?? 0) > 0) parts.push(t("datasetManage.orphanRefs", { n: overview.orphan_ref_count }))
  return parts.join(" / ")
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

async function pollOverviews() {
  const pending = datasets.value.filter(needsPoll)
  if (!pending.length) return
  await Promise.all(
    pending.map(async (entry) => {
      try {
        const data = await datasetsApi.overview(entry.name)
        entry.overview = data.overview
      } catch {
        entry.overview = { state: "error", file_count: null, captioned_count: null, total_bytes: null, updated_at: null, error: "request failed" }
      }
    }),
  )
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
  if (silent) refreshing.value = true
  else loading.value = true
  try {
    const data = await datasetsApi.list()
    rootPath.value = data.root
    rootExists.value = data.exists
    datasets.value = data.datasets
    void pollOverviews()
    if (autoRefresh.value || hasUnsettled()) ensurePolling()
  } catch (e) {
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

function openTool(tool: "tagger" | "editor", entry: DatasetEntry) {
  void router.push({ path: `/dataset/${tool}`, query: { path: entry.path } })
}

function openUpload(entry: DatasetEntry) {
  uploadTarget.value = entry.name
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
  <div class="dataset-manage">
    <section class="dataset-manage-toolbar">
      <div class="dataset-manage-root">
        <span class="eyebrow">{{ t("datasetManage.rootLabel") }}</span>
        <code>{{ rootPath || "-" }}</code>
        <span v-if="!rootExists" class="dataset-manage-root-missing">{{ t("datasetManage.rootMissing") }}</span>
      </div>
      <div class="dataset-manage-actions">
        <label class="dataset-manage-autorefresh">
          <ElSwitch v-model="autoRefresh" />
          <span>{{ t("datasetManage.autoRefresh") }}</span>
        </label>
        <button class="secondary-action" :disabled="loading || refreshing" @click="load(true)">{{ t("datasetManage.refresh") }}</button>
        <button class="secondary-action" @click="openRootDialog">{{ t("datasetManage.rootSettings") }}</button>
        <button class="secondary-action" @click="trashOpen = true">{{ t("datasetManage.trash") }}</button>
        <button class="primary-action" @click="createDialogOpen = true">{{ t("datasetManage.create") }}</button>
      </div>
    </section>

    <p v-if="!loading && !datasets.length" class="dataset-manage-empty">{{ t("datasetManage.empty") }}</p>

    <section v-else class="dataset-manage-grid">
      <article v-for="entry in datasets" :key="entry.name" class="dataset-card">
        <header class="dataset-card-header">
          <div class="dataset-card-title">
            <h2>{{ entry.name }}</h2>
            <span
              v-if="typeBadge(entry)"
              class="dataset-type-badge"
              :class="`dataset-type-badge-${typeBadge(entry)!.kind}`"
              :title="typeBadge(entry)!.title || undefined"
            >{{ typeBadge(entry)!.label }}</span>
            <button
              class="danger-action dataset-card-delete"
              :title="t('datasetManage.deleteDataset')"
              @click="deleteDataset(entry)"
            >{{ t("datasetManage.deleteDataset") }}</button>
          </div>
          <span class="dataset-card-path" :title="entry.path">{{ entry.path }}</span>
        </header>
        <dl class="dataset-card-stats">
          <div><dt>{{ isEditDataset(entry) ? t("datasetManage.targets") : t("datasetManage.files") }}</dt><dd>{{ statValue(entry, "file_count") }}</dd></div>
          <div><dt>{{ t("datasetManage.captioned") }}</dt><dd>{{ statValue(entry, "captioned_count") }}</dd></div>
          <div v-if="isEditDataset(entry)"><dt>{{ t("datasetManage.paired") }}</dt><dd>{{ statValue(entry, "paired_count") }}</dd></div>
          <div><dt>{{ t("datasetManage.size") }}</dt><dd>{{ statValue(entry, "total_bytes") }}</dd></div>
          <div><dt>{{ t("datasetManage.updatedAt") }}</dt><dd>{{ statValue(entry, "updated_at") }}</dd></div>
        </dl>
        <p v-if="pairingWarning(entry)" class="dataset-card-warning">{{ pairingWarning(entry) }}</p>
        <footer class="dataset-card-actions">
          <div class="dataset-card-actions-row">
            <button class="primary-action" @click="openUpload(entry)">{{ t("datasetManage.upload") }}</button>
            <a class="secondary-action" :href="datasetDownloadUrl(entry.name)" download>{{ t("datasetManage.downloadZip") }}</a>
          </div>
          <div class="dataset-card-actions-row">
            <button class="secondary-action" @click="openTool('tagger', entry)">{{ t("datasetManage.openTagger") }}</button>
            <button class="secondary-action" @click="openTool('editor', entry)">{{ t("datasetManage.openEditor") }}</button>
          </div>
        </footer>
      </article>
    </section>

    <ElDialog v-model="rootDialogOpen" :title="t('datasetManage.rootDialogTitle')" width="480px">
      <ElInput v-model="rootInput" :placeholder="t('datasetManage.rootDialogPlaceholder')" @keyup.enter="saveRoot" />
      <p class="dataset-manage-dialog-hint">{{ t("datasetManage.rootDialogHint") }}</p>
      <template #footer>
        <button class="secondary-action" @click="rootDialogOpen = false">{{ t("datasetManage.cancel") }}</button>
        <button class="primary-action" :disabled="rootSaving || !rootInput.trim()" @click="saveRoot">{{ t("datasetManage.save") }}</button>
      </template>
    </ElDialog>

    <DatasetUploadDialog
      :model-value="!!uploadTarget"
      :dataset-name="uploadTarget"
      @update:model-value="uploadTarget = ''"
      @uploaded="onUploaded"
    />

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
