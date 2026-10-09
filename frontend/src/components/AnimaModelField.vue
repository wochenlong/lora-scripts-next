<script setup lang="ts">
import { ref, useId, watch } from "vue"
import { useI18n } from "vue-i18n"
import type { FormField, FormValue } from "../schema/adapter"
import SchemaField from "./SchemaField.vue"

const props = defineProps<{ field: FormField; modelValue: FormValue; error?: string }>()
const emit = defineEmits<{ "update:modelValue": [value: string] }>()
const { t } = useI18n()
const groupName = useId()
type Spec = "2b" | "2.9b"
const defaults: Record<Spec, string> = {
  "2b": "./sd-models/anima/anima-base-v1.0.safetensors",
  "2.9b": "./sd-models/anima/split_files/diffusion_models/Anima-2.9B-preview-v1.safetensors",
}
const storageKey = "anima-model-paths"
const paths = { ...defaults }
try {
  const saved = JSON.parse(localStorage.getItem(storageKey) || "{}")
  for (const spec of ["2b", "2.9b"] as const) {
    if (typeof saved?.[spec] === "string" && saved[spec]) paths[spec] = saved[spec]
  }
} catch { /* Storage is optional; training must remain usable without it. */ }
const selected = ref<Spec>()
let pendingPath: string | undefined
function persist() {
  try { localStorage.setItem(storageKey, JSON.stringify(paths)) } catch { /* Optional preference. */ }
}
watch(() => props.modelValue, (value) => {
  const path = typeof value === "string" ? value : ""
  const isLocalUpdate = path === pendingPath
  pendingPath = undefined
  if (isLocalUpdate) return
  const filename = path.replaceAll("\\", "/").split("/").pop()?.toLowerCase()
  selected.value = path === paths["2.9b"] || filename === "anima-2.9b-preview-v1.safetensors"
    ? "2.9b"
    : path === paths["2b"] || filename === "anima-base-v1.0.safetensors" ? "2b" : undefined
}, { immediate: true })
function update(value: FormValue) {
  const path = typeof value === "string" ? value : ""
  if (selected.value) { paths[selected.value] = path; persist() }
  pendingPath = path === props.modelValue ? undefined : path
  emit("update:modelValue", path)
}
function select(spec: Spec) {
  if (selected.value && typeof props.modelValue === "string" && props.modelValue
    && props.modelValue !== defaults[selected.value]) {
    paths[selected.value] = props.modelValue
  }
  // Confirmation of an unknown imported model must not replace that model.
  if (!selected.value && typeof props.modelValue === "string" && props.modelValue) {
    paths[spec] = props.modelValue
  }
  selected.value = spec
  update(paths[spec])
}
</script>

<template>
  <div class="anima-model-field">
    <SchemaField
      :field="field" :model-value="modelValue" :default-value="selected ? defaults[selected] : modelValue" :error="error"
      @update:model-value="update" @reset="selected && update(defaults[selected])">
      <template #before-control>
    <div class="anima-model-spec">
      <span>{{ t("animaModel.spec") }}</span>
      <div class="anima-model-options" role="radiogroup" :aria-label="t('animaModel.spec')">
        <label v-for="spec in (['2b', '2.9b'] as const)" :key="spec">
          <input type="radio" :name="groupName" :data-spec="spec" :checked="selected === spec" :value="spec" :aria-label="spec === '2b' ? 'Anima 2B' : 'Anima 2.9B'" @change="select(spec)">
          {{ spec === "2b" ? "Anima 2B" : "Anima 2.9B" }}
        </label>
      </div>
      <span v-if="!selected" class="anima-model-unconfirmed">{{ t("animaModel.confirm") }}</span>
    </div>
      </template>
    </SchemaField>
  </div>
</template>
