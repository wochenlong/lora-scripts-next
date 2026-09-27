<script setup lang="ts">
import { computed } from "vue"
import { ElButton, ElInput, ElInputNumber } from "element-plus"
import { Plus, Delete } from "@element-plus/icons-vue"
import { useI18n } from "vue-i18n"
import { createSample, decodeSamples, encodeSamples, type PreviewSample } from "../training/sampleContract"
import ReferencePathsField from "./ReferencePathsField.vue"

const props = withDefaults(defineProps<{ samples?: string[]; editing?: boolean; disabled?: boolean; dimensionStep?: number; minGuidance?: number }>(), { samples: () => [], editing: false, disabled: false, dimensionStep: 1, minGuidance: 0 })
const emit = defineEmits<{ "update:samples": [value: string[]] }>()
const { t } = useI18n()
const decoded = computed(() => {
  try { return { samples: props.samples.length ? decodeSamples(props.samples) : [createSample()], error: "" } }
  catch (error) { return { samples: [] as PreviewSample[], error: error instanceof Error ? error.message : String(error) } }
})
const settings = ["width", "height", "seed", "guidance_scale", "sample_steps"] as const
function update(index: number, patch: Partial<PreviewSample>) {
  emit("update:samples", encodeSamples(decoded.value.samples.map((sample, i) => i === index ? { ...sample, ...patch } : sample)))
}
</script>

<template>
  <div class="preview-samples">
    <p v-if="decoded.error" role="alert">{{ decoded.error }}</p>
    <div v-for="(sample, index) in decoded.samples" :key="index" class="preview-sample-item">
      <header>
        <strong>Sample {{ index + 1 }}</strong>
        <el-button :icon="Delete" :disabled="disabled || decoded.samples.length === 1" :title="t('sampleInputs.remove')" :aria-label="t('sampleInputs.remove')" @click="emit('update:samples', encodeSamples(decoded.samples.filter((_, i) => i !== index)))" />
      </header>
      <el-input :model-value="sample.prompt" type="textarea" :rows="2" :disabled="disabled" aria-label="Prompt" @update:model-value="update(index, { prompt: $event })" />
      <div class="sample-settings">
        <label v-for="key in settings" :key="key">
          <span>{{ t(`sampleInputs.${key}`) }}</span>
          <el-input-number :model-value="sample[key]" :min="key === 'seed' ? 0 : key === 'guidance_scale' ? minGuidance : key === 'width' || key === 'height' ? dimensionStep : 1" :step="key === 'guidance_scale' ? 0.1 : key === 'width' || key === 'height' ? dimensionStep : 1" :disabled="disabled" @update:model-value="update(index, { [key]: $event ?? sample[key] })" />
        </label>
      </div>
      <ReferencePathsField v-if="editing" :model-value="sample.controlImages" mode="file" :disabled="disabled" @update:model-value="update(index, { controlImages: $event })" />
    </div>
    <el-button class="preview-sample-add" :icon="Plus" :disabled="disabled || !!decoded.error" :title="t('sampleInputs.addSample')" :aria-label="t('sampleInputs.addSample')" @click="emit('update:samples', encodeSamples([...decoded.samples, createSample()]))" />
  </div>
</template>

<style scoped>
.preview-samples { display: grid; gap: 12px; min-width: 0; }
.preview-sample-item { display: grid; gap: 10px; border-bottom: 1px solid var(--el-border-color); padding-bottom: 12px; min-width: 0; }
header { display: flex; align-items: center; justify-content: space-between; }
.sample-settings { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 8px; }
.sample-settings label { display: grid; gap: 4px; min-width: 0; }
.sample-settings .el-input-number { width: 100%; }
.preview-sample-add { justify-self: start; }
</style>
