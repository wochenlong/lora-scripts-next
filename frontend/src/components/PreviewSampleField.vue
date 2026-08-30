<script setup lang="ts">
import { computed, ref } from "vue"
import { ElMessage } from "element-plus"
import { Picture } from "@element-plus/icons-vue"
import { useI18n } from "vue-i18n"
import { pathBrowserApi } from "../api/pathBrowser"
import { useServerPathPick } from "../composables/useServerPathPick"

interface PreviewSample {
  prompt: string
  controlImages: string[]
  width: number
  height: number
  seed: number
  guidance_scale: number
  sample_steps: number
  network_multiplier: number
  sampler: string
  neg: string
}

const DEFAULT_SAMPLE_SETTINGS = {
  width: 1024,
  height: 1024,
  seed: 42,
  guidance_scale: 4,
  sample_steps: 20,
  network_multiplier: 1,
  sampler: "flowmatch",
  neg: "",
}

const props = defineProps<{
  samples?: string[]
  legacyPrompt?: string
  legacyControlImages?: string[]
  disabled?: boolean
}>()

const emit = defineEmits<{
  "update:samples": [value: string[]]
}>()

const { t } = useI18n()
const picking = ref(false)
const pickingSampleIndex = ref<number | undefined>()
const pickingImageIndex = ref<number | undefined>()
const {
  open: pathPickerOpen,
  mode: pathPickerMode,
  initialPath: pathPickerInitial,
  nameFilter: pathPickerFilter,
  pick: pickServerPath,
  onConfirm: onPathConfirm,
  onCancel: onPathCancel,
} = useServerPathPick()

function parseSample(value: string): PreviewSample | undefined {
  try {
    const parsed = JSON.parse(value) as Partial<PreviewSample>
    if (typeof parsed.prompt !== "string") return undefined
    return {
      prompt: parsed.prompt,
      controlImages: Array.isArray(parsed.controlImages)
        ? parsed.controlImages.filter((item): item is string => typeof item === "string").slice(0, 3)
        : [],
      width: typeof parsed.width === "number" ? parsed.width : DEFAULT_SAMPLE_SETTINGS.width,
      height: typeof parsed.height === "number" ? parsed.height : DEFAULT_SAMPLE_SETTINGS.height,
      seed: typeof parsed.seed === "number" ? parsed.seed : DEFAULT_SAMPLE_SETTINGS.seed,
      guidance_scale: typeof parsed.guidance_scale === "number" ? parsed.guidance_scale : DEFAULT_SAMPLE_SETTINGS.guidance_scale,
      sample_steps: typeof parsed.sample_steps === "number" ? parsed.sample_steps : DEFAULT_SAMPLE_SETTINGS.sample_steps,
      network_multiplier: typeof parsed.network_multiplier === "number" ? parsed.network_multiplier : DEFAULT_SAMPLE_SETTINGS.network_multiplier,
      sampler: typeof parsed.sampler === "string" ? parsed.sampler : DEFAULT_SAMPLE_SETTINGS.sampler,
      neg: typeof parsed.neg === "string" ? parsed.neg : DEFAULT_SAMPLE_SETTINGS.neg,
    }
  } catch {
    return undefined
  }
}

const sampleValues = computed(() => {
  const parsed = (props.samples || []).map(parseSample).filter((item): item is PreviewSample => Boolean(item))
  if (parsed.length) return parsed
  return [{
    prompt: props.legacyPrompt || "",
    controlImages: (props.legacyControlImages || []).slice(0, 3),
    ...DEFAULT_SAMPLE_SETTINGS,
  }]
})

function emitSamples(samples: PreviewSample[]) {
  emit("update:samples", samples.map((sample) => JSON.stringify(sample)))
}

function cloneSamples() {
  return sampleValues.value.map((sample) => ({ ...sample, controlImages: [...sample.controlImages] }))
}

function updatePrompt(sampleIndex: number, prompt: string) {
  const samples = cloneSamples()
  samples[sampleIndex].prompt = prompt
  emitSamples(samples)
}

function updateImage(sampleIndex: number, imageIndex: number, path: string) {
  const samples = cloneSamples()
  while (samples[sampleIndex].controlImages.length <= imageIndex) samples[sampleIndex].controlImages.push("")
  samples[sampleIndex].controlImages[imageIndex] = path
  emitSamples(samples)
}

function updateSetting(sampleIndex: number, key: keyof typeof DEFAULT_SAMPLE_SETTINGS, value: string | number) {
  const samples = cloneSamples()
  samples[sampleIndex][key] = value as never
  emitSamples(samples)
}

function addSample() {
  emitSamples([...sampleValues.value, { prompt: "", controlImages: [], ...DEFAULT_SAMPLE_SETTINGS }])
}

function removeSample(index: number) {
  if (sampleValues.value.length <= 1) return
  emitSamples(sampleValues.value.filter((_, sampleIndex) => sampleIndex !== index))
}

async function pickImage(sampleIndex: number, imageIndex: number) {
  picking.value = true
  pickingSampleIndex.value = sampleIndex
  pickingImageIndex.value = imageIndex
  try {
    await pickServerPath({
      mode: "file",
      initialPath: sampleValues.value[sampleIndex].controlImages[imageIndex] || "",
      nameFilter: "*.png;*.jpg;*.jpeg;*.webp;*.bmp",
    })
  } catch (error) {
    ElMessage.error(error instanceof Error ? error.message : t("schemaForm.pickFail"))
  } finally {
    picking.value = false
  }
}

function confirmImage(path: string) {
  if (pickingSampleIndex.value === undefined || pickingImageIndex.value === undefined) return
  updateImage(pickingSampleIndex.value, pickingImageIndex.value, path)
  pickingSampleIndex.value = undefined
  pickingImageIndex.value = undefined
  onPathConfirm(path)
}

function cancelImage() {
  pickingSampleIndex.value = undefined
  pickingImageIndex.value = undefined
  onPathCancel()
}

function clearImage(sampleIndex: number, imageIndex: number) {
  updateImage(sampleIndex, imageIndex, "")
}
</script>

<template>
  <div class="preview-sample-control">
    <div class="preview-sample-heading">
      <strong>{{ t("schemaForm.previewSample") }}</strong>
      <span>{{ t("schemaForm.previewSampleHint") }}</span>
    </div>
    <div v-for="(sample, sampleIndex) in sampleValues" :key="sampleIndex" class="preview-sample-item">
      <div class="preview-sample-item-heading">
        <span><code>samples[{{ sampleIndex }}]</code></span>
        <button v-if="sampleValues.length > 1" type="button" class="preview-sample-remove" :disabled="disabled" @click="removeSample(sampleIndex)">
          {{ t("schemaForm.removeSample") }}
        </button>
      </div>
      <div class="preview-sample-prompt">
        <span class="preview-sample-label"><code>prompt</code></span>
        <el-input
          :model-value="sample.prompt"
          type="textarea"
          :rows="2"
          :disabled="disabled"
          :placeholder="t('schemaForm.prompt')"
          @update:model-value="updatePrompt(sampleIndex, $event)"
        />
      </div>
      <div class="preview-sample-settings">
        <label class="preview-sample-setting">
          <span class="preview-sample-label"><code>width</code></span>
          <el-input-number :model-value="sample.width" :min="64" :step="64" :disabled="disabled" @update:model-value="updateSetting(sampleIndex, 'width', $event)" />
        </label>
        <label class="preview-sample-setting">
          <span class="preview-sample-label"><code>height</code></span>
          <el-input-number :model-value="sample.height" :min="64" :step="64" :disabled="disabled" @update:model-value="updateSetting(sampleIndex, 'height', $event)" />
        </label>
        <label class="preview-sample-setting">
          <span class="preview-sample-label"><code>seed</code></span>
          <el-input-number :model-value="sample.seed" :min="0" :step="1" :disabled="disabled" @update:model-value="updateSetting(sampleIndex, 'seed', $event)" />
        </label>
        <label class="preview-sample-setting">
          <span class="preview-sample-label"><code>guidance_scale</code></span>
          <el-input-number :model-value="sample.guidance_scale" :min="1" :max="30" :step="0.1" :precision="1" :disabled="disabled" @update:model-value="updateSetting(sampleIndex, 'guidance_scale', $event)" />
        </label>
        <label class="preview-sample-setting">
          <span class="preview-sample-label"><code>sample_steps</code></span>
          <el-input-number :model-value="sample.sample_steps" :min="1" :max="300" :step="1" :disabled="disabled" @update:model-value="updateSetting(sampleIndex, 'sample_steps', $event)" />
        </label>
        <label class="preview-sample-setting">
          <span class="preview-sample-label"><code>network_multiplier</code></span>
          <el-input-number :model-value="sample.network_multiplier" :min="0" :max="2" :step="0.05" :precision="2" :disabled="disabled" @update:model-value="updateSetting(sampleIndex, 'network_multiplier', $event)" />
        </label>
        <label class="preview-sample-setting">
          <span class="preview-sample-label"><code>sampler</code></span>
          <el-select :model-value="sample.sampler" :disabled="disabled" @update:model-value="updateSetting(sampleIndex, 'sampler', $event)">
            <el-option label="flowmatch" value="flowmatch" />
          </el-select>
        </label>
      </div>
      <label class="preview-sample-prompt">
        <span class="preview-sample-label"><code>neg</code></span>
        <el-input :model-value="sample.neg" :disabled="disabled" :placeholder="t('schemaForm.optionalNegativePrompt')" @update:model-value="updateSetting(sampleIndex, 'neg', $event)" />
      </label>
      <div class="preview-sample-images">
        <div class="preview-sample-label-row">
          <span class="preview-sample-label"><code>ctrl_img_1/2/3</code></span>
          <span class="preview-sample-label-hint">{{ t("schemaForm.controlImages") }}</span>
        </div>
        <div class="preview-sample-image-list">
          <div v-for="imageIndex in 3" :key="imageIndex" class="preview-sample-image-slot">
            <span class="preview-sample-image-key"><code>ctrl_img_{{ imageIndex }}</code></span>
            <span v-if="sample.controlImages[imageIndex - 1]" class="preview-sample-image-thumb-wrap">
              <img class="preview-sample-image-thumb" :src="pathBrowserApi.imageUrl(sample.controlImages[imageIndex - 1])" :alt="t('schemaForm.controlImage', { n: imageIndex })" />
            </span>
            <span v-else class="preview-sample-image-thumb-wrap preview-sample-image-thumb--empty"><Picture /></span>
            <el-input
              :model-value="sample.controlImages[imageIndex - 1] || ''"
              :disabled="disabled"
              :placeholder="t('schemaForm.optionalControlImage')"
              :aria-label="`ctrl_img_${imageIndex}`"
              @update:model-value="updateImage(sampleIndex, imageIndex - 1, $event)"
            />
            <button type="button" class="preview-sample-image-browse" :disabled="disabled" :title="t('schemaForm.chooseControlImage')" :aria-label="t('schemaForm.chooseControlImage')" @click="pickImage(sampleIndex, imageIndex - 1)">
              {{ t("schemaForm.browse") }}
            </button>
            <button v-if="sample.controlImages[imageIndex - 1]" type="button" class="preview-sample-image-clear" :disabled="disabled" :title="t('schemaForm.clearPreviewImage')" :aria-label="t('schemaForm.clearPreviewImage')" @click="clearImage(sampleIndex, imageIndex - 1)">×</button>
            <span v-if="picking && pickingSampleIndex === sampleIndex && pickingImageIndex === imageIndex - 1" class="preview-sample-upload-loading">{{ t("schemaForm.loading") }}</span>
          </div>
        </div>
      </div>
    </div>
    <button type="button" class="preview-sample-add" :disabled="disabled" @click="addSample">
      + {{ t("schemaForm.addSample") }}
    </button>
  </div>

  <PathPickerDialog
    v-model="pathPickerOpen"
    :mode="pathPickerMode"
    :initial-path="pathPickerInitial"
    :name-filter="pathPickerFilter"
    @confirm="confirmImage"
    @cancel="cancelImage"
  />
</template>
