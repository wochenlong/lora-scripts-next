<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue"
import { Folder, ArrowLeft } from "@element-plus/icons-vue"
import { ElDialog } from "element-plus"
import { useI18n } from "vue-i18n"
import { datasetsApi, type DatasetContents, type DatasetEntry } from "../../api/datasets"
import PathPickerDialog from "../PathPickerDialog.vue"
import { useServerPathPick } from "../../composables/useServerPathPick"

const props = withDefaults(
  defineProps<{ disabled?: boolean; initialPath?: string; loaded?: boolean; hideButton?: boolean; open?: boolean }>(),
  // Explicit undefined keeps "not controlled" distinguishable from a passed false.
  { disabled: undefined, initialPath: undefined, loaded: undefined, hideButton: undefined, open: undefined },
)
const emit = defineEmits<{ select: [path: string]; "update:open": [boolean] }>()
const { t } = useI18n()
const innerOpen = ref(false)
/** Controlled by the host page when it passes `open`, standalone otherwise. */
const open = computed({
  get: () => props.open ?? innerOpen.value,
  set: (value: boolean) => {
    innerOpen.value = value
    emit("update:open", value)
  },
})
const loading = ref(false)
const error = ref("")
const datasets = ref<DatasetEntry[]>([])
const content = ref<DatasetContents | null>(null)
const source = ref<"managed" | "server">("managed")
const serverPath = ref("")
const picking = ref(false)
const { open: serverBrowserOpen, initialPath: browserInitialPath, pick, onConfirm, onCancel } = useServerPathPick()
let generation = 0
const folders = computed(() => content.value?.entries.filter(entry => entry.kind === "directory") ?? [])

async function browse(name?: string, path = "") {
  const request = ++generation
  loading.value = true
  error.value = ""
  try {
    if (name) {
      const result = await datasetsApi.contents(name, path)
      if (request === generation) content.value = result
    } else {
      const result = await datasetsApi.list()
      if (request === generation) { datasets.value = result.datasets; content.value = null }
    }
  } catch (caught) {
    if (request === generation) error.value = caught instanceof Error ? caught.message : String(caught)
  } finally {
    if (request === generation) loading.value = false
  }
}
function close() { open.value = false; generation++; loading.value = false; onCancel() }
async function browseFolder() {
  if (picking.value) return
  const request = generation
  picking.value = true
  try {
    const selected = await pick({ mode: "folder", initialPath: serverPath.value })
    if (selected && open.value && request === generation) serverPath.value = selected
  } finally {
    picking.value = false
  }
}
function toggle() {
  if (open.value) close()
  else { open.value = true; source.value = "managed"; serverPath.value = props.initialPath || ""; void browse() }
}
function back() {
  if (!content.value?.relative_path) void browse()
  else void browse(content.value.name, content.value.relative_path.split("/").slice(0, -1).join("/"))
}
function select() {
  if (source.value === "server") {
    if (!serverPath.value.trim()) return
    emit("select", serverPath.value.trim())
    close()
    return
  }
  if (!content.value || loading.value || error.value || content.value.in_use) return
  emit("select", content.value.path)
  close()
}
onBeforeUnmount(close)
</script>

<template>
  <span class="managed-picker">
    <button v-if="!hideButton" type="button" class="dataset-tool-entry dataset-load-entry" :class="{ 'is-primary': !loaded }" :disabled="disabled" :aria-expanded="open" @click.prevent="toggle"><Folder />{{ loaded ? t("datasetManage.changeDataset") : t("datasetManage.loadDataset") }}</button>
    <ElDialog :model-value="open" :title="t('datasetManage.loadDataset')" width="560px" class="dataset-source-dialog" append-to-body :close-on-click-modal="false" @update:model-value="!$event && close()">
      <div class="dataset-source-tabs" role="tablist" :aria-label="t('datasetManage.loadDataset')">
        <button type="button" role="tab" :aria-selected="source === 'managed'" data-source="managed" @click="source = 'managed'">{{ t("datasetManage.registeredDatasets") }}</button>
        <button type="button" role="tab" :aria-selected="source === 'server'" data-source="server" @click="source = 'server'">{{ t("datasetManage.serverFolder") }}</button>
      </div>
      <div v-if="source === 'server'" class="dataset-source-path">
        <label for="dataset-server-path">{{ t("datasetEditor.pathLabel") }}</label>
        <div><input id="dataset-server-path" v-model="serverPath" :placeholder="t('datasetEditor.toolbar.pathPlaceholder')" @keyup.enter="select" /><button type="button" class="dataset-tool-entry" :disabled="picking" @click="browseFolder">{{ t("schemaForm.browse") }}</button></div>
      </div>
      <div v-else class="dataset-source-managed">
      <span class="managed-picker-heading">
        <button v-if="content" type="button" class="dataset-icon-button" :aria-label="t('datasetManage.back')" @click="back"><ArrowLeft /></button>
        <strong>{{ content ? content.name : t("datasetManage.selectDataset") }}</strong>
      </span>
      <span v-if="content" class="managed-picker-path">{{ content.relative_path || "/" }}</span>
      <span v-if="loading" role="status">{{ t("datasetManage.loadingTitle") }}</span>
      <span v-else-if="error" role="alert">{{ error }}<button type="button" @click="browse()">{{ t("datasetManage.retry") }}</button></span>
      <span v-else class="managed-picker-folders">
        <template v-if="!content">
          <button v-for="entry in datasets" :key="entry.name" type="button" class="managed-picker-folder" :disabled="entry.in_use" @click="browse(entry.name)"><Folder />{{ entry.name }}</button>
          <span v-if="!datasets.length">{{ t("datasetManage.emptyTitle") }}</span>
        </template>
        <template v-else>
          <button v-for="entry in folders" :key="entry.path" type="button" class="managed-picker-folder" @click="browse(content.name, entry.path)"><Folder />{{ entry.name }}</button>
          <span v-if="!folders.length">{{ t("datasetManage.noSubfolders") }}</span>
        </template>
      </span>
      </div>
      <template #footer>
        <button type="button" class="dataset-tool-entry" @click="close">{{ t("datasetManage.cancel") }}</button>
        <button type="button" class="primary-action managed-picker-confirm" :disabled="source === 'server' ? !serverPath.trim() : loading || !!error || !content || content.in_use" @click="select">{{ t("datasetManage.loadDataset") }}</button>
      </template>
    </ElDialog>
    <PathPickerDialog v-model="serverBrowserOpen" append-to-body mode="folder" :initial-path="browserInitialPath" @confirm="onConfirm" @cancel="onCancel" />
  </span>
</template>
