<script setup lang="ts">
import { computed, onMounted, reactive } from "vue"
import { ElMessage } from "element-plus"
import { useI18n } from "vue-i18n"
import {
  chinaDownloadSources,
  defaultDownloadSources,
  resolveGithubPrefix,
  resolveHfEndpoint,
  resolvePipIndexUrl,
  resolvePytorchIndexUrl,
  resolvedDownloadSourcesPayload,
  type DownloadSourcesPrefs,
  type GithubChoice,
  type HfChoice,
  type PipChoice,
  type PytorchChoice,
} from "../engines/downloadSources"
import type { SourceCheckChannel } from "../api/downloadSources"
import { useDownloadSourcesStore } from "../stores/downloadSources"

const emit = defineEmits<{ saved: [] }>()

const { t } = useI18n()
const dsStore = useDownloadSourcesStore()
const draft = reactive<DownloadSourcesPrefs>(defaultDownloadSources())

function clonePrefs(prefs: DownloadSourcesPrefs): DownloadSourcesPrefs {
  return {
    ...prefs,
    pip: { ...prefs.pip },
    pytorch: { ...prefs.pytorch },
    huggingface: { ...prefs.huggingface },
    github: { ...prefs.github },
    proxy: { ...prefs.proxy },
  }
}

function syncDraft() {
  Object.assign(draft, clonePrefs(dsStore.prefs))
}

onMounted(async () => {
  await dsStore.ensureLoaded()
  syncDraft()
})

const pipOptions: PipChoice[] = ["auto", "official", "tsinghua", "aliyun", "douban", "custom"]
const pytorchOptions: PytorchChoice[] = ["auto", "official", "aliyun", "tsinghua", "bfsu", "custom"]
const hfOptions: HfChoice[] = ["auto", "official", "hf-mirror", "modelscope", "custom"]
const githubOptions: GithubChoice[] = ["auto", "official", "ghfast", "ghproxy", "custom"]

const resolved = computed(() => ({
  pip: resolvePipIndexUrl(draft) || t("settings.engines.downloadSources.engineDefault"),
  pytorch: resolvePytorchIndexUrl(draft) || t("settings.engines.downloadSources.engineDefault"),
  huggingface: resolveHfEndpoint(draft) || t("settings.engines.downloadSources.engineDefault"),
  github: draft.github.choice === "auto"
    ? t("settings.engines.downloadSources.engineDefault")
    : resolveGithubPrefix(draft) || t("settings.engines.downloadSources.choices.github.official"),
}))

function onChannelChange() {
  draft.preset = "custom"
  dsStore.clearResults()
}

async function saveAdvanced() {
  await dsStore.savePrefs(clonePrefs(draft))
  void dsStore.checkAll()
  emit("saved")
  ElMessage.success(t("settings.engines.downloadSources.saved"))
}

async function reset() {
  await dsStore.savePrefs(defaultDownloadSources())
  syncDraft()
  void dsStore.checkAll()
  emit("saved")
  ElMessage.success(t("settings.engines.downloadSources.resetDone"))
}

function applyChinaPreset() {
  Object.assign(draft, chinaDownloadSources(), { proxy: draft.proxy })
  dsStore.clearResults()
}

async function checkDraft() {
  await dsStore.checkAll(resolvedDownloadSourcesPayload(draft))
}

function channelStatus(key: SourceCheckChannel) {
  return dsStore.statusFor(key)
}

function channelCheckText(key: SourceCheckChannel) {
  const result = dsStore.resultFor(key)
  if (!result) {
    return dsStore.statusFor(key) === "checking" || dsStore.presumedFail(key)
      ? t("settings.engines.downloadSources.status.checking")
      : ""
  }
  if (!result.ok) return result.error || `HTTP ${result.status ?? "?"}`
  return `${result.latency_ms ?? "?"} ms`
}

defineExpose({ reload: async () => { await dsStore.ensureLoaded(); syncDraft() } })
</script>

<template>
  <section class="ds-sheet ds-inline" :aria-label="t('settings.engines.downloadSources.advanced')">
        <header class="ds-sheet-head">
          <div>
            <p class="ds-kicker">{{ t("settings.engines.downloadSources.title") }}</p>
            <h3>{{ t("settings.engines.downloadSources.advanced") }}</h3>
            <p class="ds-sheet-lead">{{ t("settings.engines.downloadSources.leadShort") }}</p>
          </div>
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
              <span v-if="channelCheckText('pip')" class="ds-check" :data-status="channelStatus('pip')">{{ channelCheckText("pip") }}</span>
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
              <span v-if="channelCheckText('pytorch')" class="ds-check" :data-status="channelStatus('pytorch')">{{ channelCheckText("pytorch") }}</span>
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
              <span v-if="channelCheckText('huggingface')" class="ds-check" :data-status="channelStatus('huggingface')">{{ channelCheckText("huggingface") }}</span>
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
              <span v-if="channelCheckText('github')" class="ds-check" :data-status="channelStatus('github')">{{ channelCheckText("github") }}</span>
              <input
                v-if="draft.github.choice === 'custom'"
                v-model="draft.github.customUrl"
                type="url"
                :placeholder="t('settings.engines.downloadSources.placeholders.github')"
                @input="onChannelChange"
              >
            </div>
          </div>

          <div class="ds-channel">
            <div class="ds-channel-mark" data-ch="proxy">PX</div>
            <div class="ds-channel-body">
              <div class="ds-channel-top">
                <strong>{{ t("settings.engines.downloadSources.proxy.label") }}</strong>
              </div>
              <div class="ds-proxy-row">
                <input
                  v-model="draft.proxy.url"
                  type="url"
                  :placeholder="t('settings.engines.downloadSources.proxy.placeholder')"
                >
              </div>
              <p class="ds-proxy-hint">{{ t("settings.engines.downloadSources.proxy.hint") }}</p>
            </div>
          </div>
        </div>

        <p class="ds-footnote">{{ t("settings.engines.downloadSources.advancedNote") }}</p>

        <footer class="ds-sheet-foot">
          <button type="button" class="secondary-action" @click="applyChinaPreset">{{ t("settings.engines.downloadSources.applyChina") }}</button>
          <button type="button" class="ghost-button" @click="reset">{{ t("settings.engines.downloadSources.reset") }}</button>
          <div class="ds-sheet-foot-right">
            <button type="button" class="secondary-action" :disabled="dsStore.checking" @click="checkDraft">
              {{ dsStore.checking ? t("settings.engines.downloadSources.checking") : t("settings.engines.downloadSources.checkAll") }}
            </button>
            <button type="button" class="primary-action" @click="saveAdvanced">{{ t("settings.engines.downloadSources.save") }}</button>
          </div>
        </footer>
  </section>
</template>
