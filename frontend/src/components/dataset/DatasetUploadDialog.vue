<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { ElMessage } from "element-plus"
import { useI18n } from "vue-i18n"
import { datasetsApi, type UploadFailure, type UploadFileItem, type UploadResult } from "../../api/datasets"
import { collectUploadItems, itemsFromFileList, UPLOAD_ACCEPT } from "../../dataset/uploadSources"

const props = defineProps<{ modelValue: boolean; datasetName: string; targetDirectory?: string }>()
const emit = defineEmits<{ "update:modelValue": [boolean]; uploaded: [] }>()
const { t } = useI18n()

const ACCEPT = UPLOAD_ACCEPT

const staged = ref<UploadFileItem[]>([])
const conflicts = ref<string[]>([])
const invalid = ref<UploadFailure[]>([])
const result = ref<UploadResult | null>(null)
const failedItems = ref<UploadFileItem[]>([])
const checking = ref(false)
const uploading = ref(false)
const progress = ref(0)
const dragOver = ref(false)
const fileInput = ref<HTMLInputElement>()
const folderInput = ref<HTMLInputElement>()

const busy = computed(() => checking.value || uploading.value)

watch(
  () => props.modelValue,
  (open) => {
    if (open) reset()
  },
)

function reset() {
  staged.value = []
  conflicts.value = []
  invalid.value = []
  result.value = null
  failedItems.value = []
  progress.value = 0
}

function close() {
  if (busy.value) return
  emit("update:modelValue", false)
}

function onDialogUpdate(open: boolean) {
  if (!open && busy.value) return
  emit("update:modelValue", open)
}

function addFiles(list: Iterable<{ file: File; path: string }>) {
  const existing = new Set(staged.value.map((item) => item.path))
  for (const item of list) {
    const path = props.targetDirectory ? `${props.targetDirectory}/${item.path}` : item.path
    if (existing.has(path)) continue
    existing.add(path)
    staged.value.push({ ...item, path })
  }
  conflicts.value = []
  invalid.value = []
  result.value = null
}

function onPickFiles(event: Event) {
  const input = event.target as HTMLInputElement
  addFiles(itemsFromFileList(input.files ?? []))
  input.value = ""
}

function onPickFolder(event: Event) {
  const input = event.target as HTMLInputElement
  addFiles(itemsFromFileList(input.files ?? [], true))
  input.value = ""
}

async function onDrop(event: DragEvent) {
  dragOver.value = false
  addFiles(await collectUploadItems(event.dataTransfer))
}

function removeStaged(index: number) {
  staged.value.splice(index, 1)
}

async function submit() {
  if (!staged.value.length || busy.value) return
  checking.value = true
  try {
    const check = await datasetsApi.checkUpload(props.datasetName, staged.value.map((item) => item.path))
    invalid.value = check.invalid
    if (check.conflicts.length) {
      conflicts.value = check.conflicts
      return
    }
    await doUpload("skip")
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : t("datasetUpload.msg.checkFail"))
  } finally {
    checking.value = false
  }
}

async function resolveConflicts(mode: "skip" | "overwrite") {
  conflicts.value = []
  await doUpload(mode)
}

async function doUpload(conflict: "skip" | "overwrite") {
  const invalidPaths = new Set(invalid.value.map((item) => item.path))
  const targets = staged.value.filter((item) => !invalidPaths.has(item.path))
  if (!targets.length) return
  uploading.value = true
  progress.value = 0
  try {
    const data = await datasetsApi.upload(props.datasetName, targets, conflict, (percent) => {
      progress.value = percent
    })
    result.value = data
    const failedPaths = new Set(data.failed.map((item) => item.path))
    failedItems.value = targets.filter((item) => failedPaths.has(item.path))
    if (data.succeeded.length) emit("uploaded")
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : t("datasetUpload.msg.uploadFail"))
  } finally {
    uploading.value = false
  }
}

async function retryFailed() {
  if (!failedItems.value.length || busy.value) return
  uploading.value = true
  progress.value = 0
  try {
    const data = await datasetsApi.upload(props.datasetName, failedItems.value, "skip", (percent) => {
      progress.value = percent
    })
    if (result.value) {
      result.value = {
        dataset: data.dataset,
        succeeded: [...result.value.succeeded, ...data.succeeded],
        skipped: [...result.value.skipped, ...data.skipped],
        failed: data.failed,
      }
    } else {
      result.value = data
    }
    const failedPaths = new Set(data.failed.map((item) => item.path))
    failedItems.value = failedItems.value.filter((item) => failedPaths.has(item.path))
    if (data.succeeded.length) emit("uploaded")
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : t("datasetUpload.msg.uploadFail"))
  } finally {
    uploading.value = false
  }
}
</script>

<template>
  <ElDialog
    :model-value="modelValue"
    :title="t('datasetUpload.title', { name: datasetName })"
    width="560px"
    :close-on-click-modal="!busy"
    :close-on-press-escape="!busy"
    :show-close="!busy"
    @update:model-value="onDialogUpdate"
    @closed="reset"
  >
    <div class="upload-dialog">
      <div
        class="upload-dropzone"
        :class="{ over: dragOver }"
        @dragover.prevent="dragOver = true"
        @dragleave.prevent="dragOver = false"
        @drop.prevent="onDrop"
      >
        <p>{{ t("datasetUpload.dropHint") }}</p>
        <div class="upload-dropzone-actions">
          <button class="secondary-action" :disabled="busy" @click="fileInput?.click()">{{ t("datasetUpload.pickFiles") }}</button>
          <button class="secondary-action" :disabled="busy" @click="folderInput?.click()">{{ t("datasetUpload.pickFolder") }}</button>
        </div>
        <input ref="fileInput" type="file" multiple :accept="ACCEPT" hidden @change="onPickFiles" />
        <input ref="folderInput" type="file" multiple webkitdirectory hidden @change="onPickFolder" />
      </div>

      <ul v-if="staged.length" class="upload-file-list">
        <li v-for="(item, index) in staged" :key="item.path">
          <span class="upload-file-path">{{ item.path }}</span>
          <button class="upload-file-remove" :disabled="busy" @click="removeStaged(index)">×</button>
        </li>
      </ul>

      <div v-if="invalid.length" class="upload-conflicts">
        <h3>{{ t("datasetUpload.invalidTitle") }}</h3>
        <ul>
          <li v-for="item in invalid" :key="item.path">{{ item.path }} — {{ item.reason }}</li>
        </ul>
      </div>

      <div v-if="conflicts.length" class="upload-conflicts">
        <h3>{{ t("datasetUpload.conflictTitle", { count: conflicts.length }) }}</h3>
        <ul>
          <li v-for="path in conflicts" :key="path">{{ path }}</li>
        </ul>
        <div class="upload-conflict-actions">
          <button class="secondary-action" :disabled="busy" @click="resolveConflicts('skip')">{{ t("datasetUpload.skipAll") }}</button>
          <button class="danger-action" :disabled="busy" @click="resolveConflicts('overwrite')">{{ t("datasetUpload.overwriteAll") }}</button>
        </div>
      </div>

      <div v-if="uploading" class="upload-progress">
        <div class="meter"><div><i :style="{ width: `${progress}%` }" /></div></div>
        <span>{{ progress }}%</span>
      </div>

      <div v-if="result" class="upload-result">
        <p>{{ t("datasetUpload.resultSummary", { ok: result.succeeded.length, skipped: result.skipped.length, failed: result.failed.length }) }}</p>
        <ul v-if="result.failed.length">
          <li v-for="item in result.failed" :key="item.path">{{ item.path }} — {{ item.reason }}</li>
        </ul>
        <button v-if="failedItems.length" class="secondary-action" :disabled="busy" @click="retryFailed">{{ t("datasetUpload.retryFailed") }}</button>
      </div>
    </div>

    <template #footer>
      <button class="secondary-action" :disabled="busy" @click="close">{{ t("datasetUpload.close") }}</button>
      <button v-if="!result" class="primary-action" :disabled="busy || !staged.length" @click="submit">
        {{ uploading ? t("datasetUpload.uploading") : t("datasetUpload.submit", { count: staged.length }) }}
      </button>
    </template>
  </ElDialog>
</template>
