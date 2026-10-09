<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue"
import { useI18n } from "vue-i18n"
import { useRouter } from "vue-router"
import { ElMessage } from "element-plus"
import { ArrowLeft, Folder, Document, Picture, Upload, View, Hide, Refresh, Download } from "@element-plus/icons-vue"
import { datasetDownloadUrl, datasetFileUrl, datasetsApi, type DatasetContents } from "../api/datasets"
import DatasetUploadDialog from "../components/dataset/DatasetUploadDialog.vue"

const props = defineProps<{ name: string; directory?: string }>()
const { t } = useI18n()
const router = useRouter()
const content = ref<DatasetContents | null>(null)
const loading = ref(false)
const error = ref("")
const showImages = ref(false)
const uploadOpen = ref(false)
const preprocessOpen = ref(false)
const copyName = ref("")
const copying = ref(false)
const copyFlatten = ref(true)
const copyLayout = ref<"preserve" | "flatten" | "kohya">("preserve")
const copyRepeats = ref(10)
const page = ref(1)
const pageCount = computed(() => Math.max(1, Math.ceil((content.value?.entries.length ?? 0) / 48)))
const entries = computed(() => content.value?.entries.slice((page.value - 1) * 48, page.value * 48) ?? [])
let generation = 0
async function load() {
  const request = ++generation
  loading.value = true
  error.value = ""
  content.value = null
  try {
    const result = await datasetsApi.contents(props.name, props.directory || "")
    if (request === generation) { content.value = result; page.value = 1 }
  } catch (caught) {
    if (request === generation) error.value = caught instanceof Error ? caught.message : String(caught)
  } finally {
    if (request === generation) loading.value = false
  }
}
function navigateDirectory(path: string) {
  void router.push({ path: "/dataset/manage", query: { dataset: props.name, ...(path ? { directory: path } : {}) } })
}
function back() {
  if (props.directory) navigateDirectory(props.directory.split("/").slice(0, -1).join("/"))
  else void router.push("/dataset/manage")
}
function tool(name: "tagger" | "editor") {
  if (content.value && !content.value.in_use) void router.push({ path: `/dataset/${name}`, query: { path: content.value.path } })
}
function preprocess(flatten = true) {
  copyName.value = `${props.name}-${flatten ? "white" : "copy"}`
  copyFlatten.value = flatten
  copyLayout.value = "preserve"
  copyRepeats.value = 10
  preprocessOpen.value = true
}
async function createCopy() {
  if (copying.value || !copyName.value.trim()) return
  const request = generation
  copying.value = true
  try {
    const result = await datasetsApi.copy(props.name, copyName.value.trim(), { flattenTransparent: copyFlatten.value, layout: copyLayout.value, repeats: copyRepeats.value })
    if (request !== generation) return
    preprocessOpen.value = false
    ElMessage.success(t("datasetManage.msg.copied", { n: result.copied, m: result.flattened }))
    void router.push({ path: "/dataset/manage", query: { dataset: result.name } })
  } catch (caught) {
    ElMessage.error(caught instanceof Error ? caught.message : String(caught))
  } finally { copying.value = false }
}
watch(() => [props.name, props.directory], () => { showImages.value = false; void load() }, { immediate: true })
onBeforeUnmount(() => generation++)
</script>

<template>
  <main class="dataset-detail">
    <header class="dataset-detail-heading">
      <button class="dataset-icon-button" :aria-label="t('datasetManage.back')" :title="t('datasetManage.back')" @click="back"><ArrowLeft /></button>
      <div><h2>{{ name }}</h2><span>{{ t("datasetManage.preview") }}</span></div>
      <div class="dataset-detail-actions">
        <button class="secondary-action" :disabled="!content || content.in_use" @click="preprocess()">{{ t("datasetManage.preprocess") }}</button>
        <button class="secondary-action" data-action="copy" :disabled="!content || content.in_use" @click="preprocess(false)">{{ t("datasetManage.copy") }}</button>
        <a v-if="content" class="secondary-action" data-action="download" :href="datasetDownloadUrl(name)"><Download />{{ t("datasetManage.downloadZip") }}</a>
        <button class="secondary-action" :disabled="!content || content.in_use" data-action="tagger" @click="tool('tagger')">{{ t("datasetManage.openTagger") }}</button>
        <button class="secondary-action" :disabled="!content || content.in_use" data-action="editor" @click="tool('editor')">{{ t("datasetManage.openEditor") }}</button>
        <button class="primary-action" :disabled="!content || content.in_use" @click="uploadOpen = true"><Upload />{{ t("datasetManage.upload") }}</button>
      </div>
    </header>
    <div class="dataset-detail-location">
      <code>{{ content?.path || directory || name }}</code>
      <button class="dataset-icon-button" :title="t('datasetManage.refresh')" :aria-label="t('datasetManage.refresh')" :disabled="loading" @click="load"><Refresh /></button>
      <button class="secondary-action" data-action="previews" :disabled="!content" @click="showImages = !showImages"><Hide v-if="showImages" /><View v-else />{{ t(showImages ? "datasetManage.hideImages" : "datasetManage.showImages") }}</button>
    </div>
    <p v-if="content?.in_use" role="status">{{ t("datasetManage.inUse") }}</p>
    <div v-if="loading" class="dataset-detail-empty" role="status">{{ t("datasetManage.loadingTitle") }}</div>
    <div v-else-if="error" class="dataset-detail-empty" role="alert">{{ error }}<button class="secondary-action" @click="load">{{ t("datasetManage.retry") }}</button></div>
    <div v-else-if="!entries.length" class="dataset-detail-empty"><Folder /><p>{{ t("datasetManage.emptyFolder") }}</p></div>
    <div v-else class="dataset-detail-grid">
      <article v-for="entry in entries" :key="entry.path" class="dataset-detail-file">
        <button v-if="entry.kind === 'directory'" class="dataset-detail-folder" @click="navigateDirectory(entry.path)"><Folder /><span>{{ entry.name }}</span></button>
        <template v-else>
          <img v-if="entry.kind === 'image' && showImages" :src="datasetFileUrl(name, entry.path)" :alt="entry.name" loading="lazy">
          <Picture v-else-if="entry.kind === 'image'" class="dataset-detail-placeholder" />
          <Document v-else class="dataset-detail-placeholder" />
          <span :title="entry.name">{{ entry.name }}</span>
        </template>
      </article>
    </div>
    <footer v-if="pageCount > 1" class="dataset-pager">
      <button :disabled="page === 1" @click="page--">{{ t("datasetEditor.pager.prev") }}</button>
      <span>{{ page }} / {{ pageCount }}</span>
      <button :disabled="page === pageCount" @click="page++">{{ t("datasetEditor.pager.next") }}</button>
    </footer>
    <DatasetUploadDialog v-model="uploadOpen" :dataset-name="name" :target-directory="directory || ''" @uploaded="load" />
    <ElDialog v-model="preprocessOpen" :title="t('datasetManage.preprocessTitle')" width="min(480px, 94vw)" :close-on-click-modal="!copying" :close-on-press-escape="!copying" :show-close="!copying">
      <ElInput v-model="copyName" :disabled="copying" :placeholder="t('datasetManage.createPlaceholder')" @keyup.enter="createCopy" />
      <div class="dataset-copy-option">
        <span class="dataset-copy-label">{{ t("datasetManage.layoutLabel") }}</span>
        <ElSelect v-model="copyLayout" :disabled="copying">
          <ElOption value="preserve" :label="t('datasetManage.layoutPreserve')" />
          <ElOption value="flatten" :label="t('datasetManage.layoutFlatten')" />
          <ElOption value="kohya" :label="t('datasetManage.layoutKohya')" />
        </ElSelect>
      </div>
      <div v-if="copyLayout === 'kohya'" class="dataset-copy-option">
        <span class="dataset-copy-label">{{ t("datasetManage.repeatsLabel") }}</span>
        <ElInputNumber v-model="copyRepeats" :disabled="copying" :min="1" :max="999" controls-position="right" />
      </div>
      <p v-if="copyLayout === 'kohya'" class="dataset-manage-dialog-hint">{{ t("datasetManage.layoutKohyaHint") }}</p>
      <label class="dataset-copy-option"><ElCheckbox v-model="copyFlatten" :disabled="copying" /><span>{{ t("datasetManage.flattenOption") }}</span></label>
      <p class="dataset-manage-dialog-hint">{{ t("datasetManage.flattenHint") }}</p>
      <template #footer>
        <button class="secondary-action" :disabled="copying" @click="preprocessOpen = false">{{ t("datasetManage.cancel") }}</button>
        <button class="primary-action" :disabled="copying || !copyName.trim()" @click="createCopy">{{ t("datasetManage.preprocessConfirm") }}</button>
      </template>
    </ElDialog>
  </main>
</template>
