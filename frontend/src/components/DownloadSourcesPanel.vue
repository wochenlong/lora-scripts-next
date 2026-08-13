<script setup lang="ts">
import { computed, reactive, ref } from "vue"
import { ElMessage } from "element-plus"
import { useI18n } from "vue-i18n"
import {
  applyPreset,
  defaultDownloadSources,
  readDownloadSources,
  resolveGithubPrefix,
  resolveHfEndpoint,
  resolvePipIndexUrl,
  resolvePytorchIndexUrl,
  type DownloadSourcesPrefs,
  type GithubChoice,
  type HfChoice,
  type PipChoice,
  type PytorchChoice,
  type SourcePreset,
  writeDownloadSources,
} from "../engines/downloadSources"

defineProps<{ compact?: boolean }>()
const emit = defineEmits<{ saved: [] }>()

const { t } = useI18n()
const draft = reactive<DownloadSourcesPrefs>(readDownloadSources())
const advancedOpen = ref(false)

const pipOptions: PipChoice[] = ["official", "tsinghua", "aliyun", "douban", "custom"]
const pytorchOptions: PytorchChoice[] = ["official", "aliyun", "tsinghua", "bfsu", "custom"]
const hfOptions: HfChoice[] = ["official", "hf-mirror", "modelscope", "custom"]
const githubOptions: GithubChoice[] = ["official", "ghfast", "ghproxy", "custom"]

const resolved = computed(() => ({
  pip: resolvePipIndexUrl(draft),
  pytorch: resolvePytorchIndexUrl(draft),
  huggingface: resolveHfEndpoint(draft),
  github: resolveGithubPrefix(draft) || t("settings.engines.downloadSources.choices.github.official"),
}))

function onPresetSelect(preset: SourcePreset) {
  Object.assign(draft, applyPreset(preset, draft))
  writeDownloadSources({ ...draft })
  emit("saved")
  ElMessage.success(t("settings.engines.downloadSources.saved"))
}

function onChannelChange() {
  draft.preset = "custom"
}

function saveAdvanced() {
  writeDownloadSources({
    ...draft,
    pip: { ...draft.pip },
    pytorch: { ...draft.pytorch },
    huggingface: { ...draft.huggingface },
    github: { ...draft.github },
  })
  advancedOpen.value = false
  emit("saved")
  ElMessage.success(t("settings.engines.downloadSources.saved"))
}

function reset() {
  Object.assign(draft, defaultDownloadSources())
  writeDownloadSources(defaultDownloadSources())
  emit("saved")
  ElMessage.success(t("settings.engines.downloadSources.resetDone"))
}

function openAdvanced() {
  Object.assign(draft, readDownloadSources())
  advancedOpen.value = true
}

defineExpose({ openAdvanced, reload: () => Object.assign(draft, readDownloadSources()) })
</script>

<template>
  <div v-if="compact" class="ds-compact">
    <select
      :value="draft.preset"
      :aria-label="t('settings.engines.downloadSources.title')"
      @change="onPresetSelect(($event.target as HTMLSelectElement).value as SourcePreset)"
    >
      <option value="official">{{ t("settings.engines.downloadSources.presets.official.title") }}</option>
      <option value="china">{{ t("settings.engines.downloadSources.presets.china.short") }}</option>
      <option value="custom">{{ t("settings.engines.downloadSources.presets.custom.title") }}</option>
    </select>
    <button type="button" class="ds-link-btn" @click="openAdvanced">
      {{ t("settings.engines.downloadSources.advancedShort") }}
    </button>
  </div>

  <Teleport to="body">
    <div v-if="advancedOpen" class="ds-modal-backdrop" @click.self="advancedOpen = false">
      <section class="ds-sheet" role="dialog" :aria-label="t('settings.engines.downloadSources.advanced')">
        <header class="ds-sheet-head">
          <div>
            <p class="ds-kicker">{{ t("settings.engines.downloadSources.title") }}</p>
            <h3>{{ t("settings.engines.downloadSources.advanced") }}</h3>
            <p class="ds-sheet-lead">{{ t("settings.engines.downloadSources.leadShort") }}</p>
          </div>
          <button type="button" class="ds-close" :aria-label="t('settings.engines.downloadSources.close')" @click="advancedOpen = false">×</button>
        </header>

        <div class="ds-channels">
          <div class="ds-channel">
            <div class="ds-channel-mark" data-ch="pip">Py</div>
            <div class="ds-channel-body">
              <div class="ds-channel-top">
                <strong>{{ t("settings.engines.downloadSources.channels.pip") }}</strong>
                <select v-model="draft.pip.choice" @change="onChannelChange">
                  <option v-for="opt in pipOptions" :key="opt" :value="opt">{{ t(`settings.engines.downloadSources.choices.pip.${opt}`) }}</option>
                </select>
              </div>
              <code>{{ resolved.pip }}</code>
              <input
                v-if="draft.pip.choice === 'custom'"
                v-model="draft.pip.customUrl"
                type="url"
                :placeholder="t('settings.engines.downloadSources.placeholders.pip')"
                @input="onChannelChange"
              >
            </div>
          </div>

          <div class="ds-channel">
            <div class="ds-channel-mark" data-ch="pytorch">PT</div>
            <div class="ds-channel-body">
              <div class="ds-channel-top">
                <strong>{{ t("settings.engines.downloadSources.channels.pytorch") }}</strong>
                <select v-model="draft.pytorch.choice" @change="onChannelChange">
                  <option v-for="opt in pytorchOptions" :key="opt" :value="opt">{{ t(`settings.engines.downloadSources.choices.pytorch.${opt}`) }}</option>
                </select>
              </div>
              <code>{{ resolved.pytorch }}</code>
              <input
                v-if="draft.pytorch.choice === 'custom'"
                v-model="draft.pytorch.customUrl"
                type="url"
                :placeholder="t('settings.engines.downloadSources.placeholders.pytorch')"
                @input="onChannelChange"
              >
            </div>
          </div>

          <div class="ds-channel">
            <div class="ds-channel-mark" data-ch="hf">HF</div>
            <div class="ds-channel-body">
              <div class="ds-channel-top">
                <strong>{{ t("settings.engines.downloadSources.channels.huggingface") }}</strong>
                <select v-model="draft.huggingface.choice" @change="onChannelChange">
                  <option v-for="opt in hfOptions" :key="opt" :value="opt">{{ t(`settings.engines.downloadSources.choices.huggingface.${opt}`) }}</option>
                </select>
              </div>
              <code>{{ resolved.huggingface }}</code>
              <input
                v-if="draft.huggingface.choice === 'custom'"
                v-model="draft.huggingface.customUrl"
                type="url"
                :placeholder="t('settings.engines.downloadSources.placeholders.huggingface')"
                @input="onChannelChange"
              >
            </div>
          </div>

          <div class="ds-channel">
            <div class="ds-channel-mark" data-ch="gh">GH</div>
            <div class="ds-channel-body">
              <div class="ds-channel-top">
                <strong>{{ t("settings.engines.downloadSources.channels.github") }}</strong>
                <select v-model="draft.github.choice" @change="onChannelChange">
                  <option v-for="opt in githubOptions" :key="opt" :value="opt">{{ t(`settings.engines.downloadSources.choices.github.${opt}`) }}</option>
                </select>
              </div>
              <code>{{ resolved.github }}</code>
              <input
                v-if="draft.github.choice === 'custom'"
                v-model="draft.github.customUrl"
                type="url"
                :placeholder="t('settings.engines.downloadSources.placeholders.github')"
                @input="onChannelChange"
              >
            </div>
          </div>
        </div>

        <p class="ds-footnote">{{ t("settings.engines.downloadSources.advancedNote") }}</p>

        <footer class="ds-sheet-foot">
          <button type="button" class="ghost-button" @click="reset">{{ t("settings.engines.downloadSources.reset") }}</button>
          <div class="ds-sheet-foot-right">
            <button type="button" class="secondary-action" @click="advancedOpen = false">{{ t("settings.engines.downloadSources.close") }}</button>
            <button type="button" class="primary-action" @click="saveAdvanced">{{ t("settings.engines.downloadSources.save") }}</button>
          </div>
        </footer>
      </section>
    </div>
  </Teleport>
</template>
