<script setup lang="ts">
import { computed, ref } from "vue"
import { ElMessage } from "element-plus"
import { useI18n } from "vue-i18n"
import { schemasApi, type PickerFile } from "../api/schemas"
import type { FormField, FormModel, FormValue } from "../schema/adapter"
import PathPickerDialog from "./PathPickerDialog.vue"
import { useServerPathPick } from "../composables/useServerPathPick"
import { pathBrowserApi } from "../api/pathBrowser"

const props = defineProps<{ field: FormField; modelValue: FormValue; defaultValue?: FormValue; error?: string; context?: FormModel }>()
const emit = defineEmits<{ "update:modelValue": [value: FormValue]; reset: [] }>()
const { t } = useI18n()
const files = ref<PickerFile[]>([])
const catalogOpen = ref(false)
const catalogIndex = ref<number | undefined>()
const picking = ref(false)
const pickerType = computed(() => String(props.field.extra?.type || "folder"))
const modelPathSource = computed(() => String(props.context?.model_source || "local-file"))
const modelPathPickerType = computed(() => modelPathSource.value === "local-directory" ? "folder" : "model-file")
const modelPathBrowseEnabled = computed(() => modelPathSource.value !== "hf-repo")
const internalPicker = computed(() => props.field.extra?.internal ? String(props.field.extra.internal) : "")
const selectValue = computed(() => props.field.type === "array" && props.field.options && props.modelValue === undefined ? [] : props.modelValue)
const resettable = computed(() => !(props.field.disabled || props.field.hidden || props.field.type === "const"))
const resetDisabled = computed(() => sameValue(props.modelValue, props.defaultValue))
const resetLabel = computed(() => t(resetDisabled.value ? "schemaForm.defaultRestored" : "schemaForm.restoreDefault"))
const {
  open: pathPickerOpen,
  mode: pathPickerMode,
  initialPath: pathPickerInitial,
  nameFilter: pathPickerFilter,
  pick: pickServerPath,
  onConfirm: onPathConfirm,
  onCancel: onPathCancel,
} = useServerPathPick()
const arrayText = computed({
  get: () => Array.isArray(props.modelValue) ? props.modelValue.join("\n") : "",
  set: (value: string) => emit("update:modelValue", value.split(/\r?\n/).filter(Boolean)),
})
const compact = computed(() => {
  if (props.field.type === "boolean" || props.field.type === "number") return true
  if (props.field.options) return true
  return props.field.type === "string" && !props.field.role
})
const pairedDirectoryValues = computed(() => {
  const values = Array.isArray(props.modelValue) ? props.modelValue.map(String) : []
  return values.length ? values : ["", ""]
})
const previewControlValues = computed(() => {
  const values = Array.isArray(props.modelValue) ? props.modelValue.map((value) => String(value || "")) : []
  return Array.from({ length: 3 }, (_, index) => values[index] || "")
})
const resolutionPresets = [256, 512, 768, 1024, 1280, 1328, 1536, 2048]
const resolutionValues = computed(() => normalizeResolutions(props.modelValue))

function sameValue(left: FormValue, right: FormValue) {
  if (Array.isArray(left) || Array.isArray(right)) {
    if (!Array.isArray(left) || !Array.isArray(right) || left.length !== right.length) return false
    return left.every((item, index) => item === right[index])
  }
  return left === right
}

async function pick() {
  await pickPath(typeof props.modelValue === "string" ? props.modelValue : "")
}

async function pickPath(initialPath: string, index?: number) {
  picking.value = true
  try {
    const isFile = (props.field.role === "model-path" ? modelPathPickerType.value : pickerType.value) === "model-file"
      || props.field.role === "preview-control-images"
    const path = await pickServerPath({
      mode: isFile ? "file" : "folder",
      initialPath,
      nameFilter: props.field.role === "preview-control-images"
        ? "*.png;*.jpg;*.jpeg;*.webp;*.bmp"
        : isFile ? "*.safetensors;*.ckpt;*.pt" : "",
    })
    if (path && index !== undefined) {
      const values = props.field.role === "preview-control-images"
        ? [...previewControlValues.value]
        : [...pairedDirectoryValues.value]
      values[index] = path
      emit("update:modelValue", values)
    } else if (path) {
      emit("update:modelValue", path)
    }
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t("schemaForm.pickFail"))
  } finally {
    picking.value = false
  }
}

async function pickPreviewImage(index: number) {
  await pickPath(previewControlValues.value[index], index)
}

function updatePreviewImage(index: number, value: FormValue) {
  const values = [...previewControlValues.value]
  values[index] = typeof value === "string" ? value : ""
  emit("update:modelValue", values)
}

function clearPreviewImage(index: number) {
  updatePreviewImage(index, "")
}

function updatePairedDirectory(index: number, value: FormValue) {
  const values = [...pairedDirectoryValues.value]
  values[index] = typeof value === "string" ? value : ""
  emit("update:modelValue", values)
}

function addPairedDirectory() {
  emit("update:modelValue", [...pairedDirectoryValues.value, ""])
}

function removePairedDirectory(index: number) {
  const values = [...pairedDirectoryValues.value]
  values.splice(index, 1)
  emit("update:modelValue", values.length ? values : [""])
}

function normalizeResolutions(value: FormValue) {
  const values = Array.isArray(value)
    ? value
    : typeof value === "string" ? value.replace(/x/gi, ",").split(",") : []
  const normalized = values
    .map((item) => Number(String(item).trim()))
    .filter((item) => Number.isInteger(item) && item > 0)
  return [...new Set(normalized)]
}

function updateResolutions(value: FormValue) {
  emit("update:modelValue", normalizeResolutions(value))
}

function optionLabel(role: string | undefined, option: FormValue) {
  const value = String(option ?? "")
  if (role === "model-source-selector") return t(`schemaForm.modelSources.${value}`)
  if (role === "vae-source-selector") return t(`schemaForm.vaeSources.${value}`)
  return value || t("schemaForm.emptyOption")
}

async function openCatalog(index?: number) {
  try {
    catalogIndex.value = index
    files.value = (await schemasApi.files(internalPicker.value)).files
    catalogOpen.value = true
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t("schemaForm.catalogFail"))
  }
}

function selectCatalogPath(path: string) {
  if (catalogIndex.value === undefined) {
    emit("update:modelValue", path)
  } else {
    updatePairedDirectory(catalogIndex.value, path)
  }
  catalogOpen.value = false
  catalogIndex.value = undefined
}
</script>

<template>
  <label class="schema-field" :class="{ 'has-error': error, 'schema-field--compact': compact }">
    <span class="field-text">
      <span class="field-label"><code>{{ field.key }}</code><b v-if="field.required">{{ t("schemaForm.required") }}</b></span>
      <span v-if="field.description" class="field-description" :title="field.description">{{ field.description }}</span>
    </span>
    <span class="field-control-wrap">
      <span class="field-control">
        <span v-if="field.role === 'paired-directories'" class="paired-directories-control">
          <span v-for="(directory, index) in pairedDirectoryValues" :key="index" class="paired-directory-row">
            <span class="paired-directory-label"><code>{{ field.key }} {{ index + 1 }}</code></span>
            <span class="filepicker-control">
              <el-input :model-value="directory" :placeholder="`${field.key} ${index + 1}`" :disabled="field.disabled" @update:model-value="updatePairedDirectory(index, $event)" />
              <el-button :loading="picking" :disabled="field.disabled" @click.prevent="pickPath(directory, index)">{{ t("schemaForm.browse") }}</el-button>
            </span>
            <button v-if="index > 0" type="button" data-action="remove-directory" :disabled="field.disabled" :title="t('schemaForm.removeDirectory')" :aria-label="t('schemaForm.removeDirectory')" @click.prevent="removePairedDirectory(index)">−</button>
          </span>
          <button type="button" data-action="add-directory" :disabled="field.disabled" @click.prevent="addPairedDirectory">+ {{ t("schemaForm.addDirectory") }}</button>
        </span>
        <span v-else-if="field.role === 'preview-control-images'" class="preview-control-images">
          <span v-for="(imagePath, index) in previewControlValues" :key="index" class="preview-control-image-row">
            <span class="preview-control-image-label"><code>{{ field.key }} {{ index + 1 }}</code></span>
            <span v-if="imagePath" class="preview-control-image-thumb-wrap">
              <img class="preview-control-image-thumb" :src="pathBrowserApi.imageUrl(imagePath)" :alt="`${field.key} ${index + 1}`" />
            </span>
            <span v-else class="preview-control-image-thumb-wrap preview-control-image-thumb--empty">+</span>
            <span class="preview-control-image-path filepicker-control">
              <el-input :model-value="imagePath" :placeholder="`${field.key} ${index + 1}`" :disabled="field.disabled" @update:model-value="updatePreviewImage(index, $event)" />
              <el-button :loading="picking" :disabled="field.disabled" @click.prevent="pickPreviewImage(index)">{{ t("schemaForm.browse") }}</el-button>
              <button v-if="imagePath" type="button" data-action="clear-preview-image" :disabled="field.disabled" :title="t('schemaForm.clearPreviewImage')" :aria-label="t('schemaForm.clearPreviewImage')" @click.prevent="clearPreviewImage(index)">×</button>
            </span>
          </span>
        </span>
        <el-select
          v-else-if="field.role === 'resolution-selector'"
          :model-value="resolutionValues"
          multiple
          filterable
          allow-create
          default-first-option
          collapse-tags
          :disabled="field.disabled"
          @update:model-value="updateResolutions"
        >
          <el-option v-for="option in resolutionPresets" :key="option" :label="String(option)" :value="option" />
        </el-select>
        <span v-else-if="field.role === 'model-path'" class="model-path-control">
          <span v-if="modelPathBrowseEnabled" class="filepicker-control">
            <el-input :model-value="modelValue as string | undefined" :disabled="field.disabled" @update:model-value="emit('update:modelValue', $event)" />
            <el-button :loading="picking" :disabled="field.disabled" @click.prevent="pick">{{ t("schemaForm.browse") }}</el-button>
          </span>
          <el-input v-else :model-value="modelValue as string | undefined" :disabled="field.disabled" :placeholder="t('schemaForm.modelRepoPlaceholder')" @update:model-value="emit('update:modelValue', $event)" />
        </span>
        <el-switch v-else-if="field.type === 'boolean'" :model-value="Boolean(modelValue)" :disabled="field.disabled" @update:model-value="emit('update:modelValue', $event)" />
        <el-select v-else-if="field.options" :model-value="selectValue" :disabled="field.disabled" :multiple="field.type === 'array'" clearable @update:model-value="emit('update:modelValue', $event)">
          <el-option v-for="option in field.options" :key="String(option)" :label="optionLabel(field.role, option)" :value="option ?? ''" />
        </el-select>
        <el-input-number v-else-if="field.type === 'number'" :model-value="modelValue as number | undefined" :disabled="field.disabled" :min="field.min" :max="field.max" :step="field.step || 1" controls-position="right" @update:model-value="emit('update:modelValue', $event ?? undefined)" />
        <el-input v-else-if="field.type === 'array' || field.role === 'table'" v-model="arrayText" type="textarea" :rows="4" :disabled="field.disabled" :placeholder="t('schemaForm.arrayPlaceholder')" />
        <el-input v-else-if="field.role === 'textarea'" :model-value="modelValue as string | undefined" type="textarea" :rows="5" :disabled="field.disabled" @update:model-value="emit('update:modelValue', $event)" />
        <span v-else-if="field.role === 'filepicker'" class="filepicker-control">
          <el-input :model-value="modelValue as string | undefined" :disabled="field.disabled" @update:model-value="emit('update:modelValue', $event)" />
          <el-button :loading="picking" :disabled="field.disabled" @click.prevent="pick">{{ t("schemaForm.browse") }}</el-button>
          <el-button v-if="internalPicker" class="common-paths" :disabled="field.disabled" @click.prevent="openCatalog">{{ t("schemaForm.commonPaths") }}</el-button>
        </span>
        <el-input v-else :model-value="modelValue as string | undefined" :disabled="field.disabled || field.type === 'const'" @update:model-value="emit('update:modelValue', $event)" />
      </span>
      <el-tooltip v-if="resettable" :content="resetLabel">
        <button type="button" class="field-reset" :disabled="resetDisabled" :title="resetLabel" :aria-label="resetLabel" @click.prevent="emit('reset')">↺</button>
      </el-tooltip>
    </span>
    <span v-if="error" class="field-error">{{ error }}</span>
  </label>

  <el-dialog v-model="catalogOpen" :title="t('schemaForm.catalogTitle')" width="min(680px, 92vw)">
    <div class="picker-list">
      <button v-for="file in files" :key="file.path" @click="selectCatalogPath(file.path)">
        <strong>{{ file.name }}</strong><span>{{ file.path }}</span><small v-if="file.size">{{ file.size }}</small>
      </button>
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
