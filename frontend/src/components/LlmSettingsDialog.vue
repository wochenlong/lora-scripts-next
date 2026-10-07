<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { ElDialog } from "element-plus"
import { useI18n } from "vue-i18n"
import { llmApi, type LlmConfig, type LlmProfile } from "../api/llm"

const props = defineProps<{ modelValue: boolean; capability: "text" | "vision"; imagePath?: string }>()
const emit = defineEmits<{ "update:modelValue": [value: boolean]; saved: [config: LlmConfig] }>()
const { t } = useI18n()
const draft = ref<LlmConfig>({ version: 5, profiles: [], routes: {}, prompt_presets: [], cache: {} })
const committed = ref("")
const loading = ref(false)
const saving = ref(false)
const testing = ref("")
const error = ref("")
const result = ref("")
const testImage = ref("")
let generation = 0

const profiles = computed(() => [...draft.value.profiles].sort((a, b) => Number(b.source === "remote") - Number(a.source === "remote")))
const dirty = computed(() => JSON.stringify(draft.value) !== committed.value)
const textProfiles = computed(() => profiles.value.filter(profile => profile.enabled && profile.capabilities.includes("text")))
const visionProfiles = computed(() => profiles.value.filter(profile => profile.enabled && profile.capabilities.includes("vision")))

watch(() => props.modelValue, async open => {
  const revision = ++generation
  error.value = ""
  result.value = ""
  if (!open) {
    draft.value = { version: 5, profiles: [], routes: {}, prompt_presets: [], cache: {} }
    return
  }
  loading.value = true
  testImage.value = props.imagePath || ""
  try {
    const config = await llmApi.config()
    if (revision !== generation) return
    draft.value = JSON.parse(JSON.stringify(config))
    committed.value = JSON.stringify(draft.value)
  } catch (caught) {
    if (revision === generation) error.value = caught instanceof Error ? caught.message : String(caught)
  } finally {
    if (revision === generation) loading.value = false
  }
}, { immediate: true })

function close() {
  if (saving.value || testing.value) return
  generation += 1
  draft.value = { version: 5, profiles: [], routes: {}, prompt_presets: [], cache: {} }
  emit("update:modelValue", false)
}

function add() {
  draft.value.profiles.push({ id: `profile-${Date.now()}`, name: t("llm.newProfile"), endpoint: "", model: "",
    source: "remote", capabilities: props.capability === "vision" ? ["text", "vision"] : ["text"],
    languages: ["zh-CN", "en"], api_key: "", enabled: true, ready: true })
}

function setCapability(profile: LlmProfile, value: string, selected: boolean) {
  profile.capabilities = selected ? [...new Set([...profile.capabilities, value])] : profile.capabilities.filter(item => item !== value)
}

function languages(profile: LlmProfile, event: Event) {
  profile.languages = (event.target as HTMLInputElement).value.split(",").map(item => item.trim()).filter(Boolean)
}

async function save() {
  if (draft.value.profiles.some(profile => !profile.name.trim() || !profile.endpoint.trim() || !profile.model.trim() || !profile.capabilities.length || !profile.languages.length)) {
    error.value = t("llm.fieldsRequired")
    return
  }
  saving.value = true
  error.value = ""
  try {
    // Save only fields this editor owns. Concurrent preset edits stay intact.
    const config = await llmApi.saveConfig({ profiles: draft.value.profiles, routes: draft.value.routes })
    draft.value = JSON.parse(JSON.stringify(config))
    committed.value = JSON.stringify(draft.value)
    emit("saved", config)
    saving.value = false
    close()
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : String(caught)
  } finally {
    saving.value = false
  }
}

async function test(profile: LlmProfile) {
  testing.value = profile.id
  error.value = ""
  result.value = ""
  try {
    await llmApi.connectionTest({ capability: props.capability, profile_id: profile.id,
      ...(props.capability === "vision" ? { image_path: testImage.value } : {}) })
    result.value = t("llm.testPassed", { name: profile.name })
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : String(caught)
  } finally {
    testing.value = ""
  }
}
</script>

<template>
  <ElDialog :model-value="modelValue" :title="t('llm.title')" width="min(800px, 96vw)" :close-on-click-modal="false" :before-close="close" @update:model-value="value => { if (!value) close() }">
    <div class="llm-settings">
      <p>{{ t("llm.sharedHint") }}</p>
      <p>{{ t("llm.keyHint") }}</p>
      <p v-if="loading" role="status">{{ t("llm.loading") }}</p>
      <p v-if="error" role="alert" class="llm-error">{{ error }}</p>
      <p v-if="result" role="status">{{ result }}</p>
      <fieldset :disabled="loading || saving || Boolean(testing)">
        <label>{{ t("llm.translationRoute") }}<select v-model="draft.routes.translation"><option value="">{{ t("llm.auto") }}</option><option v-for="profile in textProfiles" :key="profile.id" :value="profile.id">{{ profile.name }}</option></select></label>
        <label>{{ t("llm.captionRoute") }}<select v-model="draft.routes.caption"><option value="">{{ t("llm.auto") }}</option><option v-for="profile in visionProfiles" :key="profile.id" :value="profile.id">{{ profile.name }}</option></select></label>
        <label v-if="capability === 'vision'">{{ t("llm.testImage") }}<input v-model="testImage" class="llm-test-image" /></label>
        <p v-if="dirty">{{ t("llm.saveBeforeTest") }}</p>
        <article v-for="profile in profiles" :key="profile.id" class="llm-profile-card" :data-profile-id="profile.id">
          <header><strong>{{ profile.name || profile.id }}</strong><span>{{ profile.source === 'remote' ? t("llm.remote") : t("llm.local") }}</span></header>
          <div class="llm-profile-fields">
            <label>{{ t("llm.name") }}<input v-model="profile.name" class="llm-profile-name" /></label>
            <label>{{ t("llm.source") }}<select v-model="profile.source" :disabled="profile.source === 'managed-local'"><option value="remote">{{ t("llm.remote") }}</option><option value="local-endpoint">{{ t("llm.local") }}</option><option v-if="profile.source === 'managed-local'" value="managed-local">{{ t("llm.managed") }}</option></select></label>
            <label>{{ t("llm.endpoint") }}<input v-model="profile.endpoint" :disabled="profile.source === 'managed-local'" placeholder="https://…/chat/completions" /></label>
            <label>{{ t("llm.model") }}<input v-model="profile.model" :disabled="profile.source === 'managed-local'" /></label>
            <label>{{ t("llm.key") }}<input v-model="profile.api_key" type="password" autocomplete="new-password" :disabled="profile.source === 'managed-local'" /></label>
            <label>{{ t("llm.languages") }}<input :value="profile.languages.join(',')" @input="languages(profile, $event)" /></label>
          </div>
          <div class="llm-capabilities">
            <label><input type="checkbox" :checked="profile.capabilities.includes('text')" :disabled="profile.source === 'managed-local'" @change="setCapability(profile, 'text', ($event.target as HTMLInputElement).checked)" />{{ t("llm.text") }}</label>
            <label><input type="checkbox" :checked="profile.capabilities.includes('vision')" :disabled="profile.source === 'managed-local'" @change="setCapability(profile, 'vision', ($event.target as HTMLInputElement).checked)" />{{ t("llm.vision") }}</label>
            <label><input v-model="profile.enabled" type="checkbox" />{{ t("llm.enabled") }}</label>
          </div>
          <div class="llm-profile-actions">
            <button type="button" :disabled="dirty || !profile.enabled || !profile.ready || !profile.capabilities.includes(capability) || (capability === 'vision' && !testImage)" @click="test(profile)">{{ t("llm.test") }}</button>
            <button type="button" :disabled="profile.source === 'managed-local'" @click="draft.profiles = draft.profiles.filter(item => item.id !== profile.id)">{{ t("llm.remove") }}</button>
          </div>
        </article>
        <button type="button" class="llm-add-profile" @click="add">{{ t("llm.add") }}</button>
      </fieldset>
    </div>
    <template #footer><button type="button" class="llm-cancel" :disabled="saving || Boolean(testing)" @click="close">{{ t("llm.cancel") }}</button><button type="button" class="primary-action llm-save" :disabled="loading || saving || Boolean(testing)" @click="save">{{ t("llm.save") }}</button></template>
  </ElDialog>
</template>
