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
  writeDownloadSources,
} from "../engines/downloadSources"

defineProps<{ compact?: boolean }>()
const emit = defineEmits<{ saved: [] }>()

const { t } = useI18n()
const draft = reactive<DownloadSourcesPrefs>(readDownloadSources())
const advancedOpen = ref(false)
const channelsOpen = ref(draft.preset === "custom")

const pipOptions: PipChoice[] = ["official", "tsinghua", "aliyun", "douban", "custom"]
const pytorchOptions: PytorchChoice[] = ["official", "aliyun", "tsinghua", "bfsu", "custom"]
const hfOptions: HfChoice[] = ["official", "hf-mirror", "modelscope", "custom"]
const githubOptions: GithubChoice[] = ["official", "ghfast", "ghproxy", "custom"]
const presets = ["official", "china"] as const

const resolved = computed(() => ({
  pip: resolvePipIndexUrl(draft),
  pytorch: resolvePytorchIndexUrl(draft),
  huggingface: resolveHfEndpoint(draft),
  github: resolveGithubPrefix(draft) || t("settings.engines.downloadSources.choices.github.official"),
}))

const choiceLabels = computed(() => ({
  pip: t(`settings.engines.downloadSources.choices.pip.${draft.pip.choice}`),
  pytorch: t(`settings.engines.downloadSources.choices.pytorch.${draft.pytorch.choice}`),
  huggingface: t(`settings.engines.downloadSources.choices.huggingface.${draft.huggingface.choice}`),
  github: t(`settings.engines.downloadSources.choices.github.${draft.github.choice}`),
}))

const isCustom = computed(() => draft.preset === "custom")
const presetNote = computed(() => (
  isCustom.value
    ? t("settings.engines.downloadSources.presets.custom.hint")
    : t(`settings.engines.downloadSources.presets.${draft.preset}.hint`)
))

function persist() {
  writeDownloadSources({
    ...draft,
    pip: { ...draft.pip },
    pytorch: { ...draft.pytorch },
    huggingface: { ...draft.huggingface },
    github: { ...draft.github },
  })
  emit("saved")
}

function onPresetSelect(preset: "official" | "china") {
  Object.assign(draft, applyPreset(preset, draft))
  channelsOpen.value = false
  persist()
  ElMessage.success(t("settings.engines.downloadSources.saved"))
}

function onChannelChange() {
  draft.preset = "custom"
}

function save() {
  persist()
  ElMessage.success(t("settings.engines.downloadSources.saved"))
}

function saveAdvanced() {
  save()
  advancedOpen.value = false
}

function reset() {
  Object.assign(draft, defaultDownloadSources())
  channelsOpen.value = false
  writeDownloadSources(defaultDownloadSources())
  emit("saved")
  ElMessage.success(t("settings.engines.downloadSources.resetDone"))
}

function openAdvanced() {
  Object.assign(draft, readDownloadSources())
  advancedOpen.value = true
}

function onCompactPreset(value: string) {
  if (value === "official" || value === "china") onPresetSelect(value)
}

defineExpose({ openAdvanced, reload: () => Object.assign(draft, readDownloadSources()) })
</script>

<template>
  <div v-if="compact" class="ds-compact">
    <select
      :value="isCustom ? 'custom' : draft.preset"
      :aria-label="t('settings.engines.downloadSources.title')"
      data-testid="download-sources-compact-preset"
      @change="onCompactPreset(($event.target as HTMLSelectElement).value)"
    >
      <option value="official">{{ t("settings.engines.downloadSources.presets.official.title") }}</option>
      <option value="china">{{ t("settings.engines.downloadSources.presets.china.short") }}</option>
      <option v-if="isCustom" value="custom" disabled>{{ t("settings.engines.downloadSources.presets.custom.title") }}</option>
    </select>
    <button type="button" class="ds-link-btn" @click="openAdvanced">
      {{ t("settings.engines.downloadSources.advancedShort") }}
    </button>
  </div>

  <section
    v-else
    class="settings-card download-sources-card"
    data-testid="download-sources-card"
  >
    <h2>{{ t("settings.engines.downloadSources.title") }}</h2>
    <small>{{ t("settings.engines.downloadSources.lead") }}</small>

    <div class="ds-field">
      <span class="ds-field-label">{{ t("settings.engines.downloadSources.presetAria") }}</span>
      <div class="ds-segments" role="radiogroup" :aria-label="t('settings.engines.downloadSources.presetAria')">
        <button
          v-for="preset in presets"
          :key="preset"
          type="button"
          role="radio"
          :aria-checked="draft.preset === preset"
          class="ds-segment"
          :class="{ selected: draft.preset === preset }"
          :data-testid="`download-sources-preset-${preset}`"
          @click="onPresetSelect(preset)"
        >
          {{ t(`settings.engines.downloadSources.presets.${preset}.title`) }}
        </button>
      </div>
      <p class="ds-preset-note" :data-custom="isCustom" data-testid="download-sources-preset-note">{{ presetNote }}</p>
    </div>

    <ul class="ds-summary" :aria-label="t('settings.engines.downloadSources.summaryAria')" data-testid="download-sources-summary">
      <li>
        <span>{{ t("settings.engines.downloadSources.channels.pip") }}</span>
        <strong>{{ choiceLabels.pip }}</strong>
        <small>{{ resolved.pip }}</small>
      </li>
      <li>
        <span>{{ t("settings.engines.downloadSources.channels.pytorch") }}</span>
        <strong>{{ choiceLabels.pytorch }}</strong>
        <small>{{ resolved.pytorch }}</small>
      </li>
      <li>
        <span>{{ t("settings.engines.downloadSources.channels.huggingface") }}</span>
        <strong>{{ choiceLabels.huggingface }}</strong>
        <small>{{ resolved.huggingface }}</small>
      </li>
      <li>
        <span>{{ t("settings.engines.downloadSources.channels.github") }}</span>
        <strong>{{ choiceLabels.github }}</strong>
        <small>{{ resolved.github }}</small>
      </li>
    </ul>

    <details class="ds-channels-panel" :open="channelsOpen" @toggle="channelsOpen = ($event.target as HTMLDetailsElement).open">
      <summary data-testid="download-sources-channels-toggle">
        {{ t("settings.engines.downloadSources.advanced") }}
      </summary>

      <form class="ds-channels-form" @submit.prevent="save">
        <label class="ds-channel-field">
          <span>{{ t("settings.engines.downloadSources.channels.pip") }}</span>
          <small>{{ t("settings.engines.downloadSources.channelHints.pip") }}</small>
          <select v-model="draft.pip.choice" data-testid="download-sources-pip" @change="onChannelChange">
            <option v-for="opt in pipOptions" :key="opt" :value="opt">{{ t(`settings.engines.downloadSources.choices.pip.${opt}`) }}</option>
          </select>
          <input
            v-if="draft.pip.choice === 'custom'"
            v-model="draft.pip.customUrl"
            type="url"
            :placeholder="t('settings.engines.downloadSources.placeholders.pip')"
            @input="onChannelChange"
          >
        </label>

        <label class="ds-channel-field">
          <span>{{ t("settings.engines.downloadSources.channels.pytorch") }}</span>
          <small>{{ t("settings.engines.downloadSources.channelHints.pytorch") }}</small>
          <select v-model="draft.pytorch.choice" data-testid="download-sources-pytorch" @change="onChannelChange">
            <option v-for="opt in pytorchOptions" :key="opt" :value="opt">{{ t(`settings.engines.downloadSources.choices.pytorch.${opt}`) }}</option>
          </select>
          <input
            v-if="draft.pytorch.choice === 'custom'"
            v-model="draft.pytorch.customUrl"
            type="url"
            :placeholder="t('settings.engines.downloadSources.placeholders.pytorch')"
            @input="onChannelChange"
          >
        </label>

        <label class="ds-channel-field">
          <span>{{ t("settings.engines.downloadSources.channels.huggingface") }}</span>
          <small>{{ t("settings.engines.downloadSources.channelHints.huggingface") }}</small>
          <select v-model="draft.huggingface.choice" data-testid="download-sources-hf" @change="onChannelChange">
            <option v-for="opt in hfOptions" :key="opt" :value="opt">{{ t(`settings.engines.downloadSources.choices.huggingface.${opt}`) }}</option>
          </select>
          <input
            v-if="draft.huggingface.choice === 'custom'"
            v-model="draft.huggingface.customUrl"
            type="url"
            :placeholder="t('settings.engines.downloadSources.placeholders.huggingface')"
            @input="onChannelChange"
          >
        </label>

        <label class="ds-channel-field">
          <span>{{ t("settings.engines.downloadSources.channels.github") }}</span>
          <small>{{ t("settings.engines.downloadSources.channelHints.github") }}</small>
          <select v-model="draft.github.choice" data-testid="download-sources-github" @change="onChannelChange">
            <option v-for="opt in githubOptions" :key="opt" :value="opt">{{ t(`settings.engines.downloadSources.choices.github.${opt}`) }}</option>
          </select>
          <input
            v-if="draft.github.choice === 'custom'"
            v-model="draft.github.customUrl"
            type="url"
            :placeholder="t('settings.engines.downloadSources.placeholders.github')"
            @input="onChannelChange"
          >
        </label>

        <p class="ds-footnote">{{ t("settings.engines.downloadSources.advancedNote") }}</p>

        <div class="ds-card-actions">
          <button type="button" class="ghost-button" data-testid="download-sources-reset" @click="reset">
            {{ t("settings.engines.downloadSources.reset") }}
          </button>
          <button type="submit" class="primary-action" data-testid="download-sources-save">
            {{ t("settings.engines.downloadSources.save") }}
          </button>
        </div>
      </form>
    </details>
  </section>

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
