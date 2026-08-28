<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { ElMessage } from "element-plus"
import { useI18n } from "vue-i18n"
import { assetsApi, type AssetItem, type AssetSource } from "../api/assets"
import type { FormModel } from "../schema/adapter"

const props = defineProps<{ schemaName: string; model: FormModel }>()
const { t } = useI18n()

const items = ref<AssetItem[]>([])
const selectedKeys = ref(new Set<string>())
const checking = ref(false)
const dialogOpen = ref(false)
const source = ref<AssetSource>("modelscope")
const downloading = ref(false)
const logs = ref<string[]>([])
let logSource: EventSource | undefined

const trainType = computed(() => String(props.model.model_train_type || props.schemaName))
const missing = computed(() => items.value.filter((item) => !item.exists && !item.optional))
const downloadable = computed(() => items.value.filter((item) => !item.exists))
const selectedTargets = computed(() => downloadable.value.filter((item) => selectedKeys.value.has(item.key)))

function toggleSelect(key: string, checked: boolean) {
  const next = new Set(selectedKeys.value)
  if (checked) next.add(key)
  else next.delete(key)
  selectedKeys.value = next
}

function closeStream() {
  logSource?.close()
  logSource = undefined
}

async function check(silent = false) {
  checking.value = true
  try {
    const data = await assetsApi.check(trainType.value, props.model)
    items.value = data.items
    const next = new Set(selectedKeys.value)
    for (const item of data.items) {
      if (item.exists) next.delete(item.key)
      else if (!next.has(item.key) && !item.optional) next.add(item.key)
    }
    selectedKeys.value = next
    if (!silent) {
      if (missing.value.length) ElMessage.warning(t("training.assets.missingCount", { n: missing.value.length }))
      else ElMessage.success(t("training.assets.allPresent"))
    }
  } catch (error) {
    if (!silent) ElMessage.error(error instanceof Error ? error.message : t("training.assets.checkFail"))
  } finally {
    checking.value = false
  }
}

async function openDialog() {
  dialogOpen.value = true
  await check(true)
}

function followLog(streamUrl: string) {
  closeStream()
  if (typeof EventSource === "undefined") return
  logSource = new EventSource(streamUrl)
  logSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data)
      if (data.text) logs.value.push(data.text)
      if (data.done) {
        closeStream()
        downloading.value = false
        void check(true).then(() => {
          if (!missing.value.length) ElMessage.success(t("training.assets.downloadDone"))
        })
      }
    } catch { /* ignore */ }
  }
  logSource.onerror = () => { closeStream(); downloading.value = false }
}

async function download() {
  const targets = selectedTargets.value.map((item) => ({ key: item.key, path: item.path }))
  if (!targets.length || downloading.value) return
  downloading.value = true
  logs.value = []
  try {
    const data = await assetsApi.download(trainType.value, props.model, targets, source.value)
    ElMessage.success(t("training.assets.downloadStarted"))
    followLog(data.log_stream)
  } catch (error) {
    downloading.value = false
    ElMessage.error(error instanceof Error ? error.message : t("training.assets.downloadFail"))
  }
}

onMounted(() => { void check(true) })
// Variant switch (e.g. klein-4b-lora <-> klein-9b-lora) swaps the asset manifest;
// refresh silently so the list follows the form's train type.
watch(trainType, () => { void check(true) })
onBeforeUnmount(closeStream)
</script>

<template>
  <div v-if="items.length" class="model-assets-tools">
    <button :disabled="checking" @click="check()">{{ checking ? t("training.assets.checking") : t("training.assets.check") }}</button>
    <button @click="openDialog">{{ t("training.assets.download") }}</button>
    <span v-if="missing.length" class="assets-missing-hint">{{ t("training.assets.missingCount", { n: missing.length }) }}</span>
  </div>

  <el-dialog v-model="dialogOpen" :title="t('training.assets.title')" width="min(640px, 92vw)" @closed="closeStream">
    <ul class="assets-list">
      <li v-for="item in items" :key="item.key" :class="{ missing: !item.exists }">
        <input v-if="!item.exists" type="checkbox" :checked="selectedKeys.has(item.key)" :aria-label="t('training.assets.selectAria', { label: item.label })" @change="toggleSelect(item.key, ($event.target as HTMLInputElement).checked)">
        <strong>{{ item.label }}</strong>
        <code>{{ item.path }}</code>
        <span v-if="item.exists" class="asset-ok">{{ t("training.assets.exists") }}</span>
        <span v-else class="asset-miss">{{ item.optional ? t("training.assets.missingOptional") : t("training.assets.missing") }}</span>
      </li>
    </ul>
    <div class="assets-source">
      <span>{{ t("training.assets.source") }}</span>
      <label><input v-model="source" type="radio" value="modelscope">ModelScope</label>
      <label><input v-model="source" type="radio" value="huggingface">HuggingFace</label>
    </div>
    <pre v-if="logs.length" class="assets-log">{{ logs.join("\n") }}</pre>
    <div class="assets-actions">
      <button class="primary-action" :disabled="downloading || !selectedTargets.length" @click="download">
        {{ downloading ? t("training.assets.downloading") : t("training.assets.downloadSelected", { n: selectedTargets.length }) }}
      </button>
      <button class="secondary-action" @click="dialogOpen = false">{{ t("training.assets.close") }}</button>
    </div>
  </el-dialog>
</template>
