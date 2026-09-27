<script setup lang="ts">
import { computed } from "vue"
import { ElButton, ElInput } from "element-plus"
import { Plus, Delete, FolderOpened } from "@element-plus/icons-vue"
import { useI18n } from "vue-i18n"
import { useServerPathPick } from "../composables/useServerPathPick"
import PathPickerDialog from "./PathPickerDialog.vue"

const props = withDefaults(defineProps<{ modelValue: string[]; mode?: "file" | "folder"; disabled?: boolean }>(), { mode: "folder", disabled: false })
const emit = defineEmits<{ "update:modelValue": [value: string[]] }>()
const { t } = useI18n()
const paths = computed(() => props.modelValue.length ? props.modelValue : [""])
const { open, mode: pickerMode, initialPath, nameFilter, pick, onConfirm, onCancel } = useServerPathPick()
function update(index: number, value: string) {
  const next = [...paths.value]
  next[index] = value
  emit("update:modelValue", next)
}
async function browse(index: number) {
  const value = await pick({ mode: props.mode, initialPath: paths.value[index], nameFilter: props.mode === "file" ? "*.png;*.jpg;*.jpeg;*.webp;*.bmp" : "" })
  if (value) update(index, value)
}
</script>

<template>
  <div class="reference-paths">
    <div v-for="(path, index) in paths" :key="index" class="reference-path">
      <span>{{ index + 1 }}</span>
      <el-input :model-value="path" :disabled="disabled" :aria-label="`${t('sampleInputs.reference')} ${index + 1}`" @update:model-value="update(index, $event)" />
      <el-button :icon="FolderOpened" :disabled="disabled" :title="t('schemaForm.browse')" :aria-label="t('schemaForm.browse')" @click="browse(index)" />
      <el-button :icon="Delete" :disabled="disabled" :title="t('sampleInputs.remove')" :aria-label="t('sampleInputs.remove')" @click="emit('update:modelValue', paths.filter((_, i) => i !== index))" />
    </div>
    <el-button :icon="Plus" :disabled="disabled" :title="t('sampleInputs.addReference')" :aria-label="t('sampleInputs.addReference')" @click="emit('update:modelValue', [...paths, ''])" />
    <PathPickerDialog v-model="open" :mode="pickerMode" :initial-path="initialPath" :name-filter="nameFilter" @confirm="onConfirm" @cancel="onCancel" />
  </div>
</template>

<style scoped>
.reference-paths { display: grid; gap: 8px; min-width: 0; }
.reference-path { display: flex; gap: 6px; align-items: center; min-width: 0; }
.reference-path .el-input { min-width: 0; flex: 1; }
.reference-paths .el-button { margin-left: 0; }
.reference-paths > .el-button { justify-self: start; }
</style>
