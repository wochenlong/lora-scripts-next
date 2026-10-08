<script setup lang="ts">
import { useI18n } from "vue-i18n"
import type { CaptionPromptPreset } from "../api/llm"
defineProps<{ presets: CaptionPromptPreset[]; builtins: CaptionPromptPreset[]; saving: boolean; legacyCount: number }>()
const presetId = defineModel<string>("presetId", { required: true })
const name = defineModel<string>("name", { required: true })
const prompt = defineModel<string>("prompt", { required: true })
const systemPrompt = defineModel<string>("systemPrompt", { required: true })
const maximum = defineModel<number | undefined>("maximum", { required: true })
const emit = defineEmits<{ select: [identifier: string]; save: []; saveAs: []; restore: []; restoreDefault: []; remove: []; importLegacy: []; refresh: [] }>()
const { t } = useI18n()

function requestPreset(event: Event) {
  const select = event.target as HTMLSelectElement
  const identifier = select.value
  // The parent commits selection only after handling unsaved changes.
  select.value = presetId.value
  emit("select", identifier)
}
</script>

<template>
  <div class="caption-prompt-editor wide-field">
    <label>{{ t("tagger.caption.preset") }}<select :value="presetId" class="caption-preset-select" :disabled="saving" @change="requestPreset"><option value="">{{ t("tagger.caption.customPrompt") }}</option><optgroup :label="t('tagger.caption.builtins')"><option v-for="preset in builtins" :key="preset.id" :value="preset.id">{{ preset.name }}</option></optgroup><optgroup :label="t('tagger.caption.userPresets')"><option v-for="preset in presets" :key="preset.id" :value="preset.id">{{ preset.name }}</option></optgroup></select></label>
    <label>{{ t("tagger.caption.presetName") }}<input v-model="name" class="caption-preset-name" :disabled="saving" /></label>
    <label>{{ t("tagger.caption.maxLength") }}<input v-model.number="maximum" class="caption-max-length" type="number" min="1" max="2000" step="1" :disabled="saving" /></label>
    <label class="wide-field">{{ t("tagger.caption.prompt") }}<textarea v-model="prompt" rows="4" :disabled="saving" /></label>
    <details class="wide-field"><summary>{{ t('tagger.caption.systemPrompt') }}</summary><label>{{ t('tagger.caption.systemPrompt') }}<textarea v-model="systemPrompt" class="caption-system-prompt" rows="3" :disabled="saving" /></label></details>
    <div class="caption-preset-actions wide-field"><button type="button" :disabled="saving" @click="emit('save')">{{ t("tagger.caption.savePreset") }}</button><button type="button" :disabled="saving" @click="emit('restore')">{{ t("tagger.caption.restorePrompt") }}</button><button type="button" :disabled="saving || !presets.some(preset => preset.id === presetId)" @click="emit('remove')">{{ t("tagger.caption.removePreset") }}</button><button type="button" :disabled="saving" @click="emit('saveAs')">{{ t("tagger.caption.saveAs") }}</button><button type="button" :disabled="saving" @click="emit('restoreDefault')">{{ t("tagger.caption.restoreDefault") }}</button></div>
    <div v-if="legacyCount" class="caption-legacy-import wide-field"><p>{{ t('tagger.caption.legacyAvailable', { count: legacyCount }) }}</p><button type="button" :disabled="saving" @click="emit('importLegacy')">{{ t('tagger.caption.importLegacy') }}</button></div>
    <button type="button" class="caption-refresh-presets" :disabled="saving" @click="emit('refresh')">{{ t('tagger.caption.refreshPresets') }}</button>
  </div>
</template>
