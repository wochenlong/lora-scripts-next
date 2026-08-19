<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { ElMessage } from "element-plus"
import { useI18n } from "vue-i18n"
import {
  pathBrowserApi,
  type PathBrowserEntry,
  type PathBrowserList,
  type PathBrowserMode,
  type PathBrowserRoot,
} from "../api/pathBrowser"

const props = defineProps<{
  modelValue: boolean
  mode?: PathBrowserMode
  initialPath?: string
  nameFilter?: string
}>()

const emit = defineEmits<{
  "update:modelValue": [value: boolean]
  confirm: [path: string]
  cancel: []
}>()

const { t } = useI18n()
const loading = ref(false)
const listing = ref<PathBrowserList | null>(null)
const selectedFile = ref<string>("")
const confirmed = ref(false)

const open = computed({
  get: () => props.modelValue,
  set: (value: boolean) => {
    emit("update:modelValue", value)
    if (!value && !confirmed.value) emit("cancel")
    if (!value) confirmed.value = false
  },
})

const mode = computed<PathBrowserMode>(() => props.mode || "folder")
const currentPath = computed(() => listing.value?.path || "")
const roots = computed<PathBrowserRoot[]>(() => listing.value?.roots || [])
const entries = computed<PathBrowserEntry[]>(() => listing.value?.entries || [])

async function load(path = props.initialPath || "") {
  loading.value = true
  selectedFile.value = ""
  try {
    listing.value = await pathBrowserApi.list(path, mode.value, props.nameFilter || "")
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t("pathPicker.loadFail"))
  } finally {
    loading.value = false
  }
}

function enterDir(path: string) {
  void load(path)
}

function onRowClick(entry: PathBrowserEntry) {
  if (entry.type === "dir") {
    enterDir(entry.path)
    return
  }
  selectedFile.value = entry.path
}

function onRowDblClick(entry: PathBrowserEntry) {
  if (entry.type === "dir") {
    enterDir(entry.path)
    return
  }
  selectedFile.value = entry.path
  confirm()
}

function goParent() {
  if (listing.value?.parent) enterDir(listing.value.parent)
}

function confirm() {
  if (mode.value === "folder") {
    if (!currentPath.value) return
    confirmed.value = true
    emit("confirm", currentPath.value.replaceAll("\\", "/"))
    open.value = false
    return
  }
  if (!selectedFile.value) {
    ElMessage.warning(t("pathPicker.pickFileFirst"))
    return
  }
  confirmed.value = true
  emit("confirm", selectedFile.value.replaceAll("\\", "/"))
  open.value = false
}

function formatSize(bytes?: number) {
  if (bytes == null) return ""
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`
}

watch(
  () => props.modelValue,
  (value) => {
    if (value) {
      confirmed.value = false
      void load(props.initialPath || "")
    }
  },
)
</script>

<template>
  <el-dialog
    v-model="open"
    class="path-picker-dialog"
    :title="mode === 'folder' ? t('pathPicker.titleFolder') : t('pathPicker.titleFile')"
    width="min(820px, 94vw)"
    destroy-on-close
  >
    <div class="path-picker">
      <aside class="path-picker-roots" aria-label="roots">
        <button
          v-for="root in roots"
          :key="root.id + root.path"
          type="button"
          class="path-picker-root"
          :class="{ active: currentPath === root.path }"
          @click="enterDir(root.path)"
        >
          <strong>{{ root.label }}</strong>
          <span>{{ root.path }}</span>
        </button>
      </aside>

      <section class="path-picker-main">
        <div class="path-picker-toolbar">
          <el-button :disabled="!listing?.parent || loading" @click="goParent">{{ t("pathPicker.up") }}</el-button>
          <code class="path-picker-current" :title="currentPath">{{ currentPath || "…" }}</code>
          <el-button :loading="loading" @click="load(currentPath)">{{ t("pathPicker.refresh") }}</el-button>
        </div>

        <div v-loading="loading" class="path-picker-list">
          <button
            v-for="entry in entries"
            :key="entry.type + entry.path"
            type="button"
            class="path-picker-row"
            :class="{ selected: selectedFile === entry.path, dir: entry.type === 'dir' }"
            @click="onRowClick(entry)"
            @dblclick.prevent="onRowDblClick(entry)"
          >
            <span class="kind">{{ entry.type === "dir" ? t("pathPicker.dir") : t("pathPicker.file") }}</span>
            <strong>{{ entry.name }}</strong>
            <small v-if="entry.type === 'file'">{{ formatSize(entry.size_bytes) }}</small>
          </button>
          <p v-if="!loading && entries.length === 0" class="path-picker-empty">{{ t("pathPicker.empty") }}</p>
        </div>

        <p class="path-picker-hint">
          {{ mode === "folder" ? t("pathPicker.hintFolder") : t("pathPicker.hintFile") }}
        </p>
      </section>
    </div>

    <template #footer>
      <el-button @click="open = false">{{ t("pathPicker.cancel") }}</el-button>
      <el-button type="primary" :disabled="mode === 'file' ? !selectedFile : !currentPath" @click="confirm">
        {{ t("pathPicker.confirm") }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.path-picker {
  display: grid;
  grid-template-columns: minmax(140px, 200px) 1fr;
  gap: 12px;
  min-height: 420px;
}
.path-picker-roots {
  display: flex;
  flex-direction: column;
  gap: 6px;
  overflow: auto;
  max-height: 460px;
  padding-right: 4px;
}
.path-picker-root {
  text-align: left;
  border: 1px solid var(--el-border-color);
  background: var(--el-fill-color-blank);
  border-radius: 8px;
  padding: 8px 10px;
  cursor: pointer;
}
.path-picker-root strong {
  display: block;
  font-size: 13px;
}
.path-picker-root span {
  display: block;
  font-size: 11px;
  color: var(--el-text-color-secondary);
  word-break: break-all;
}
.path-picker-root.active,
.path-picker-root:hover {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.path-picker-main {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}
.path-picker-toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
}
.path-picker-current {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  padding: 6px 8px;
  background: var(--el-fill-color-light);
  border-radius: 6px;
}
.path-picker-list {
  flex: 1;
  min-height: 300px;
  max-height: 360px;
  overflow: auto;
  border: 1px solid var(--el-border-color);
  border-radius: 8px;
}
.path-picker-row {
  width: 100%;
  display: grid;
  grid-template-columns: 52px 1fr auto;
  gap: 8px;
  align-items: center;
  text-align: left;
  border: 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: transparent;
  padding: 8px 10px;
  cursor: pointer;
}
.path-picker-row:hover,
.path-picker-row.selected {
  background: var(--el-color-primary-light-9);
}
.path-picker-row .kind {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
.path-picker-row.dir strong {
  color: var(--el-color-primary);
}
.path-picker-empty,
.path-picker-hint {
  margin: 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.path-picker-empty {
  padding: 24px;
  text-align: center;
}
@media (max-width: 720px) {
  .path-picker {
    grid-template-columns: 1fr;
  }
  .path-picker-roots {
    flex-direction: row;
    flex-wrap: wrap;
    max-height: none;
  }
}
</style>
