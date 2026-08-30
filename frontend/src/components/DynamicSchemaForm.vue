<script setup lang="ts">
import { computed } from "vue"
import { useI18n } from "vue-i18n"
import type { AdaptedSchema, FormField, FormModel, FormValue } from "../schema/adapter"
import { isFieldActive } from "../schema/adapter"
import SchemaField from "./SchemaField.vue"
import PreviewSampleField from "./PreviewSampleField.vue"

const props = defineProps<{ schema: AdaptedSchema; modelValue: FormModel; errors: Record<string, string>; effectiveDefaults: FormModel }>()
const emit = defineEmits<{ "update:modelValue": [value: FormModel]; "reset-field": [key: string] }>()
const { t } = useI18n()

const selectedFields = computed(() => {
  const result = new Map<string, FormField>()
  for (const section of props.schema.sections) {
    for (const field of section.fields) {
      if (isFieldActive(field, props.modelValue)) result.set(field.key, field)
    }
  }
  return result
})

const taskField = computed(() => props.schema.sections
  .flatMap((section) => section.fields)
  .find((field) => field.role === "task-selector"))
const taskSelectorVisible = computed(() => {
  const capabilities = props.schema.capabilities
  return Boolean(taskField.value && capabilities.includes("text-to-image") && capabilities.includes("image-edit"))
})
const taskDescription = computed(() => {
  const description = taskField.value?.description?.trim()
  return description && description !== t("schemaForm.taskLabel") ? description : ""
})
const imageEditSelected = computed(() => taskSelectorVisible.value && props.modelValue[taskField.value?.key || ""] === "image-edit")

function visibleFields(fields: FormField[]) {
  return fields.filter((field) => !field.hidden && field.role !== "task-selector" && selectedFields.value.get(field.key) === field)
}

function update(key: string, value: FormModel[string]) {
  emit("update:modelValue", { ...props.modelValue, [key]: value })
}

function taskLabel(value: FormValue) {
  if (value === "text-to-image") return t("schemaForm.tasks.textToImage")
  if (value === "image-edit") return t("schemaForm.tasks.imageEdit")
  return String(value ?? "")
}

function fieldOrder(field: FormField) {
  return imageEditSelected.value && field.key === "train_data_dir" ? -1 : 0
}
</script>

<template>
  <div class="schema-form">
    <div v-if="taskSelectorVisible" class="task-selector">
      <span class="field-label">{{ t("schemaForm.taskLabel") }}</span>
      <span v-if="taskDescription" class="field-description">{{ taskDescription }}</span>
      <div class="segmented" role="group" :aria-label="t('schemaForm.taskLabel')">
        <button
          v-for="option in taskField?.options || []"
          :key="String(option)"
          type="button"
          :data-task="String(option)"
          :class="{ active: modelValue[taskField!.key] === option }"
          @click="update(taskField!.key, option)"
        >
          {{ taskLabel(option) }}
        </button>
      </div>
    </div>
    <section v-for="section in schema.sections" v-show="visibleFields(section.fields).length" :id="`sec-${section.id}`" :key="section.id" class="schema-section">
      <header><h2>{{ section.title }}</h2><span>{{ t("schemaForm.fieldCount", { n: visibleFields(section.fields).length }) }}</span></header>
      <slot :name="`tools-${section.id}`" />
      <div class="schema-fields">
        <template v-for="field in [...visibleFields(section.fields)].sort((left, right) => fieldOrder(left) - fieldOrder(right))" :key="field.key">
          <PreviewSampleField
            v-if="field.role === 'preview-sample'"
            :samples="modelValue.preview_samples as string[] | undefined"
            :legacy-prompt="modelValue[field.key] as string | undefined"
            :legacy-control-images="modelValue.sample_control_images as string[] | undefined"
            :disabled="field.disabled"
            @update:samples="update('preview_samples', $event)"
          />
          <SchemaField
            v-else
            :field="field"
            :model-value="modelValue[field.key]"
            :default-value="effectiveDefaults[field.key]"
            :error="errors[field.key]"
            :context="modelValue"
            @update:model-value="update(field.key, $event)"
            @reset="emit('reset-field', field.key)"
          />
        </template>
      </div>
    </section>
  </div>
</template>
