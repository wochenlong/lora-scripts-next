<script setup lang="ts">
import { computed } from "vue"
import { useI18n } from "vue-i18n"
import type { AdaptedSchema, FormField, FormModel } from "../schema/adapter"
import { isAnimaFastTorchCompileBlocked, isFieldActive } from "../schema/adapter"
import SchemaField from "./SchemaField.vue"

const props = defineProps<{ schema: AdaptedSchema; modelValue: FormModel; errors: Record<string, string> }>()
const emit = defineEmits<{ "update:modelValue": [value: FormModel] }>()
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

function presentedField(field: FormField): FormField {
  if (field.key !== "torch_compile") return field
  return {
    ...field,
    disabled: field.disabled || isAnimaFastTorchCompileBlocked(props.modelValue),
    description: `${field.description || ""} attn_mode=torch 时会因 #336 禁用 torch_compile；请关闭该选项或改用受支持的 attention 模式。`.trim(),
  }
}

function update(key: string, value: FormModel[string]) {
  const next = { ...props.modelValue, [key]: value }
  if (key === "attn_mode" && value === "torch") next.torch_compile = false
  emit("update:modelValue", next)
}
</script>

<template>
  <div class="schema-form">
    <section v-for="section in schema.sections" v-show="visibleFields(section.fields).length" :id="`sec-${section.id}`" :key="section.id" class="schema-section">
      <header><h2>{{ section.title }}</h2><span>{{ t("schemaForm.fieldCount", { n: visibleFields(section.fields).length }) }}</span></header>
      <slot :name="`tools-${section.id}`" />
      <div class="schema-fields">
        <SchemaField v-for="field in visibleFields(section.fields)" :key="field.key" :field="presentedField(field)" :model-value="modelValue[field.key]" :error="errors[field.key]" @update:model-value="update(field.key, $event)" />
      </div>
    </section>
  </div>
</template>
