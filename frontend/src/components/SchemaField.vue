<script setup lang="ts">
import { computed, ref } from "vue"
import { ElMessage } from "element-plus"
import { useI18n } from "vue-i18n"
import { schemasApi, type PickerFile } from "../api/schemas"
import type { FormField, FormValue } from "../schema/adapter"

const props = defineProps<{ field: FormField; modelValue: FormValue; error?: string }>()
const emit = defineEmits<{ "update:modelValue": [value: FormValue] }>()
const { t } = useI18n()
const files = ref<PickerFile[]>([])
const catalogOpen = ref(false)
const picking = ref(false)
const pickerType = computed(() => String(props.field.extra?.type || "folder"))
const internalPicker = computed(() => props.field.extra?.internal ? String(props.field.extra.internal) : "")
const arrayText = computed({
  get: () => Array.isArray(props.modelValue) ? props.modelValue.join("\n") : "",
  set: (value: string) => emit("update:modelValue", value.split(/\r?\n/).filter(Boolean)),
})
const compact = computed(() => {
  if (props.field.type === "boolean" || props.field.type === "number") return true
  if (props.field.options) return true
  return props.field.type === "string" && !props.field.role
})

async function pick() {
  picking.value = true
  try {
    const data = await schemasApi.pickFile(pickerType.value)
    emit("update:modelValue", data.path.replaceAll("\\", "/"))
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t("schemaForm.pickFail"))
  } finally {
    picking.value = false
  }
}

async function openCatalog() {
  try {
    files.value = (await schemasApi.files(internalPicker.value)).files
    catalogOpen.value = true
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t("schemaForm.catalogFail"))
  }
}
</script>

<template>
  <label class="schema-field" :class="{ 'has-error': error, 'schema-field--compact': compact }">
    <span class="field-text">
      <span class="field-label"><code>{{ field.key }}</code><b v-if="field.required">{{ t("schemaForm.required") }}</b></span>
      <span v-if="field.description" class="field-description">{{ field.description }}</span>
    </span>
    <span class="field-control">
      <el-switch v-if="field.type === 'boolean'" :model-value="Boolean(modelValue)" :disabled="field.disabled" @update:model-value="emit('update:modelValue', $event)" />
      <el-select v-else-if="field.options" :model-value="modelValue" :disabled="field.disabled" :multiple="field.type === 'array'" clearable @update:model-value="emit('update:modelValue', $event)">
        <el-option v-for="option in field.options" :key="String(option)" :label="String(option) || t('schemaForm.emptyOption')" :value="option ?? ''" />
      </el-select>
      <el-input-number v-else-if="field.type === 'number'" :model-value="modelValue as number | undefined" :disabled="field.disabled" :min="field.min" :max="field.max" :step="field.step || 1" controls-position="right" @update:model-value="emit('update:modelValue', $event ?? undefined)" />
      <el-input v-else-if="field.type === 'array' || field.role === 'table'" v-model="arrayText" type="textarea" :rows="4" :disabled="field.disabled" :placeholder="t('schemaForm.arrayPlaceholder')" />
      <el-input v-else-if="field.role === 'textarea'" :model-value="modelValue as string | undefined" type="textarea" :rows="5" :disabled="field.disabled" @update:model-value="emit('update:modelValue', $event)" />
      <span v-else-if="field.role === 'filepicker'" class="filepicker-control">
        <el-input :model-value="modelValue as string | undefined" :disabled="field.disabled" @update:model-value="emit('update:modelValue', $event)" />
        <el-button :loading="picking" :disabled="field.disabled" @click.prevent="pick">{{ t("schemaForm.browse") }}</el-button>
        <el-button v-if="internalPicker" :disabled="field.disabled" @click.prevent="openCatalog">{{ t("schemaForm.commonPaths") }}</el-button>
      </span>
      <el-input v-else :model-value="modelValue as string | undefined" :disabled="field.disabled || field.type === 'const'" @update:model-value="emit('update:modelValue', $event)" />
    </span>
    <span v-if="error" class="field-error">{{ error }}</span>
  </label>

  <el-dialog v-model="catalogOpen" :title="t('schemaForm.catalogTitle')" width="min(680px, 92vw)">
    <div class="picker-list">
      <button v-for="file in files" :key="file.path" @click="emit('update:modelValue', file.path); catalogOpen = false">
        <strong>{{ file.name }}</strong><span>{{ file.path }}</span><small v-if="file.size">{{ file.size }}</small>
      </button>
    </div>
  </el-dialog>
</template>
