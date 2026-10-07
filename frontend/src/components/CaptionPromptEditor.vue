<script setup lang="ts">
import { useI18n } from "vue-i18n"
import type { LlmConfig } from "../api/llm"
defineProps<{ presets: LlmConfig["prompt_presets"]; saving: boolean }>()
const presetId = defineModel<string>("presetId", { required: true })
const name = defineModel<string>("name", { required: true })
const prompt = defineModel<string>("prompt", { required: true })
const maximum = defineModel<number | undefined>("maximum", { required: true })
const emit = defineEmits<{ select: []; save: []; restore: []; remove: [] }>()
const { t } = useI18n()
</script>

<template>
  <div class="caption-prompt-editor wide-field">
    <label>{{ t("tagger.caption.preset") }}<select v-model="presetId" class="caption-preset-select" :disabled="saving" @change="emit('select')"><option value="">{{ t("tagger.caption.customPrompt") }}</option><option v-for="preset in presets" :key="preset.id" :value="preset.id">{{ preset.name }}</option></select></label>
    <label>{{ t("tagger.caption.presetName") }}<input v-model="name" class="caption-preset-name" :disabled="saving" /></label>
    <label>{{ t("tagger.caption.maxLength") }}<input v-model.number="maximum" class="caption-max-length" type="number" min="1" max="2000" step="1" :disabled="saving" /></label>
    <label class="wide-field">{{ t("tagger.caption.prompt") }}<textarea v-model="prompt" rows="4" :disabled="saving" /></label>
    <div class="caption-preset-actions wide-field"><button type="button" :disabled="saving" @click="emit('save')">{{ t("tagger.caption.savePreset") }}</button><button type="button" :disabled="saving" @click="emit('restore')">{{ t("tagger.caption.restorePrompt") }}</button><button type="button" :disabled="saving || !presetId" @click="emit('remove')">{{ t("tagger.caption.removePreset") }}</button></div>
  </div>
</template>
