<script setup lang="ts">
import { computed } from "vue"
import { useI18n } from "vue-i18n"
import type { AdaptedSchema, FormField, FormModel } from "../schema/adapter"
import { isFieldActive } from "../schema/adapter"
import SchemaField from "./SchemaField.vue"

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

function visibleFields(fields: FormField[]) {
  return fields.filter((field) => !field.hidden && selectedFields.value.get(field.key) === field)
}

function update(key: string, value: FormModel[string]) {
  emit("update:modelValue", { ...props.modelValue, [key]: value })
}
</script>

<template>
  <div class="schema-form">
    <section v-for="section in schema.sections" v-show="visibleFields(section.fields).length" :id="`sec-${section.id}`" :key="section.id" class="schema-section">
      <header><h2>{{ section.title }}</h2><span>{{ t("schemaForm.fieldCount", { n: visibleFields(section.fields).length }) }}</span></header>
      <slot :name="`tools-${section.id}`" />
      <div class="schema-fields">
        <SchemaField
          v-for="field in visibleFields(section.fields)"
          :key="field.key"
          :field="field"
          :model-value="modelValue[field.key]"
          :default-value="effectiveDefaults[field.key]"
          :error="errors[field.key]"
          @update:model-value="update(field.key, $event)"
          @reset="emit('reset-field', field.key)"
        />
      </div>
    </section>
  </div>
</template>
