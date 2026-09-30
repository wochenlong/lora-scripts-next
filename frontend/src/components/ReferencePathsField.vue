<script setup lang="ts">
import { computed, ref } from "vue"
import { ElButton, ElInput } from "element-plus"
import { Plus, Delete, FolderOpened, Picture } from "@element-plus/icons-vue"
import { useI18n } from "vue-i18n"
import { useServerPathPick } from "../composables/useServerPathPick"
import PathPickerDialog from "./PathPickerDialog.vue"
import { schemasApi, type PickerFile } from "../api/schemas"

const props = withDefaults(defineProps<{ modelValue: string[]; mode?: "file" | "folder"; disabled?: boolean; internalPicker?: string; compact?: boolean }>(), { mode: "folder", disabled: false, internalPicker: "", compact: false })
const emit = defineEmits<{ "update:modelValue": [value: string[]] }>()
const { t } = useI18n()
const paths = computed(() => props.modelValue.length ? props.modelValue : [""])
const catalogOpen = ref(false)
const catalogLoading = ref(false)
const uploadLoading = ref(false)
const catalog = ref<PickerFile[]>([])
const uploadInput = ref<HTMLInputElement>()
const uploadIndex = ref<number>()
const { open, mode: pickerMode, initialPath, nameFilter, pick, onConfirm, onCancel } = useServerPathPick()
function update(index: number, value: string) {
  const next = [...paths.value]
  next[index] = value
  emit("update:modelValue", next)
}
function previewUrl(path: string) {
  return `/api/training/preview-image?path=${encodeURIComponent(path)}`
}
async function openCatalog() {
  if (!props.internalPicker) return
  catalogLoading.value = true
  try {
    catalog.value = (await schemasApi.files(props.internalPicker)).files
    catalogOpen.value = true
  } finally {
    catalogLoading.value = false
  }
}
function useCatalogPath(path: string) {
  emit("update:modelValue", [...props.modelValue, path])
  catalogOpen.value = false
}
async function browse(index: number) {
  if (props.compact) {
    uploadIndex.value = index
    uploadInput.value?.click()
    return
  }
  const value = await pick({ mode: props.mode, initialPath: paths.value[index], nameFilter: props.mode === "file" ? "*.png;*.jpg;*.jpeg;*.webp;*.bmp" : "" })
  if (value) update(index, value)
}
async function uploadFile(index: number, file: File) {
  if (!file.type.startsWith("image/")) return
  uploadLoading.value = true
  try {
    const result = await schemasApi.uploadPreviewImage(file)
    update(index, result.path)
  } finally {
    uploadLoading.value = false
  }
}
async function onDrop(index: number, event: DragEvent) {
  event.preventDefault()
  event.stopPropagation()
  const file = event.dataTransfer?.files?.[0]
  if (file) await uploadFile(index, file)
}
async function onAddDrop(event: DragEvent) {
  event.preventDefault()
  event.stopPropagation()
  const file = event.dataTransfer?.files?.[0]
  if (!file?.type.startsWith("image/")) return
  uploadLoading.value = true
  try {
    const result = await schemasApi.uploadPreviewImage(file)
    emit("update:modelValue", [...props.modelValue, result.path])
  } finally {
    uploadLoading.value = false
  }
}
async function onUploadSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ""
  const index = uploadIndex.value
  uploadIndex.value = undefined
  if (file && index !== undefined) await uploadFile(index, file)
}
</script>

<template>
  <div v-if="compact" class="control-images">
    <input ref="uploadInput" class="visually-hidden" type="file" accept=".png,.jpg,.jpeg,.webp,.bmp,image/png,image/jpeg,image/webp,image/bmp" @change="onUploadSelected" />
    <div class="control-images-title">{{ t("sampleInputs.controlImages") }}</div>
    <div class="control-images-grid">
      <button v-for="(path, index) in modelValue" :key="index" type="button" class="control-image-card" :class="{ filled: !!path }" :title="path || `${t('sampleInputs.addControlImage')} ${index + 1}`" :disabled="disabled || uploadLoading" @click="browse(index)" @dragover.prevent @drop="onDrop(index, $event)">
        <img v-if="path" :src="previewUrl(path)" :alt="`${t('sampleInputs.controlImage')} ${index + 1}`" />
        <el-icon v-else><Picture /></el-icon>
        <strong v-if="!path">{{ `${t("sampleInputs.addControlImage")} ${index + 1}` }}</strong>
        <small v-if="!path">{{ t("sampleInputs.clickOrDrop") }}</small>
      </button>
      <button v-if="!disabled" type="button" class="control-image-card control-image-add" :disabled="uploadLoading" @click="emit('update:modelValue', [...modelValue, ''])" @dragover.prevent @drop="onAddDrop">
        <el-icon><Plus /></el-icon>
        <strong>{{ t("sampleInputs.addControlImage") }} {{ modelValue.length + 1 }}</strong>
        <small>{{ t("sampleInputs.clickOrDrop") }}</small>
      </button>
    </div>
    <el-button v-if="internalPicker" :loading="catalogLoading" :disabled="disabled" @click="openCatalog">{{ t("schemaForm.commonPaths") }}</el-button>
  </div>
  <div class="reference-paths">
    <template v-if="!compact">
      <div v-for="(path, index) in paths" :key="index" class="reference-path">
        <span>{{ index + 1 }}</span>
        <el-input :model-value="path" :disabled="disabled" :aria-label="`${t('sampleInputs.reference')} ${index + 1}`" @update:model-value="update(index, $event)" />
        <el-button :icon="FolderOpened" :disabled="disabled" :title="t('schemaForm.browse')" :aria-label="t('schemaForm.browse')" @click="browse(index)" />
        <el-button :icon="Delete" :disabled="disabled" :title="t('sampleInputs.remove')" :aria-label="t('sampleInputs.remove')" @click="emit('update:modelValue', paths.filter((_, i) => i !== index))" />
      </div>
    </template>
    <el-button v-if="!compact" :icon="Plus" :disabled="disabled" :title="t('sampleInputs.addReference')" :aria-label="t('sampleInputs.addReference')" @click="emit('update:modelValue', [...paths, ''])" />
    <el-button v-if="!compact && internalPicker" :loading="catalogLoading" :disabled="disabled" @click="openCatalog">{{ t("schemaForm.commonPaths") }}</el-button>
    <PathPickerDialog v-model="open" :mode="pickerMode" :initial-path="initialPath" :name-filter="nameFilter" @confirm="onConfirm" @cancel="onCancel" />
    <el-dialog v-model="catalogOpen" :title="t('schemaForm.catalogTitle')" width="min(680px, 92vw)">
      <div class="picker-list">
        <button v-for="file in catalog" :key="file.path" type="button" @click="useCatalogPath(file.path)">
          <strong>{{ file.name }}</strong><span>{{ file.path }}</span><small v-if="file.size">{{ file.size }}</small>
        </button>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.reference-paths { display: grid; gap: 8px; min-width: 0; }
.reference-path { display: flex; gap: 6px; align-items: center; min-width: 0; }
.reference-path .el-input { min-width: 0; flex: 1; }
.reference-paths .el-button { margin-left: 0; }
.reference-paths > .el-button { justify-self: start; }
.control-images { display: grid; gap: 8px; min-width: 0; }
.control-images-title { color: var(--el-text-color-regular); font-size: 12px; font-weight: 600; }
.control-images-grid { display: grid; grid-template-columns: repeat(auto-fill, 112px); gap: 8px; }
.control-image-card { width: 112px; aspect-ratio: 1; padding: 8px; border: 1px solid var(--el-border-color); border-radius: 6px; background: var(--el-fill-color-light); color: var(--el-text-color-primary); display: grid; place-items: center; gap: 4px; cursor: pointer; overflow: hidden; }
.control-image-card:hover:not(:disabled) { border-color: var(--el-color-primary); }
.control-image-card.filled { padding: 4px; background: var(--el-bg-color); }
.control-image-card img { width: 100%; height: 100%; object-fit: contain; border-radius: 4px; }
.control-image-card strong, .control-image-card small { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.control-image-card strong { font-size: 11px; }
.control-image-card small { color: var(--el-text-color-secondary); font-size: 10px; }
.control-image-add { border-style: dashed; }
.control-image-card:disabled { cursor: wait; opacity: .7; }
.visually-hidden { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
</style>
