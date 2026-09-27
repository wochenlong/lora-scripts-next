<script setup lang="ts">
import { computed, ref, watch } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { useI18n } from "vue-i18n"
import { datasetsApi, type TrashBatch } from "../../api/datasets"

const props = defineProps<{ modelValue: boolean; datasetName?: string }>()
const emit = defineEmits<{ "update:modelValue": [boolean]; changed: [] }>()
const { t } = useI18n()

const isGlobal = computed(() => !props.datasetName)
const title = computed(() => (props.datasetName ? t("datasetTrash.title", { name: props.datasetName }) : t("datasetTrash.titleGlobal")))

const batches = ref<TrashBatch[]>([])
const loading = ref(false)
const busyId = ref("")

watch(
  () => props.modelValue,
  (open) => {
    if (open) void load()
  },
)

async function load() {
  loading.value = true
  try {
    const data = props.datasetName ? await datasetsApi.trash(props.datasetName) : await datasetsApi.trashAll()
    batches.value = data.batches
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : t("datasetTrash.msg.loadFail"))
  } finally {
    loading.value = false
  }
}

function formatTime(iso: string | null) {
  if (!iso) return "-"
  const date = new Date(iso)
  return Number.isNaN(date.getTime()) ? "-" : date.toLocaleString()
}

async function restore(batch: TrashBatch) {
  if (busyId.value) return
  busyId.value = batch.id
  try {
    const data = props.datasetName
      ? await datasetsApi.restoreTrash(props.datasetName, batch.id)
      : await datasetsApi.restoreTrashAny(batch.id)
    if (data.restored.length) {
      ElMessage.success(t("datasetTrash.msg.restored", { n: data.restored.length }))
      emit("changed")
    }
    if (data.conflicts.length) ElMessage.warning(t("datasetTrash.msg.conflicts", { n: data.conflicts.length }))
    await load()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : t("datasetTrash.msg.fail"))
  } finally {
    busyId.value = ""
  }
}

async function emptyBatch(batch: TrashBatch) {
  if (busyId.value) return
  try {
    await ElMessageBox.confirm(t("datasetTrash.confirmDeleteBatch", { count: batch.count }), { type: "warning" })
  } catch {
    return
  }
  busyId.value = batch.id
  try {
    if (props.datasetName) await datasetsApi.emptyTrash(props.datasetName, batch.id)
    else await datasetsApi.emptyTrashAny(batch.id)
    ElMessage.success(t("datasetTrash.msg.emptied"))
    await load()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : t("datasetTrash.msg.fail"))
  } finally {
    busyId.value = ""
  }
}

async function emptyAll() {
  if (busyId.value || !batches.value.length) return
  try {
    await ElMessageBox.confirm(t("datasetTrash.confirmEmptyAll"), { type: "warning" })
  } catch {
    return
  }
  busyId.value = "*"
  try {
    if (props.datasetName) await datasetsApi.emptyTrash(props.datasetName)
    else await datasetsApi.emptyTrashAny()
    ElMessage.success(t("datasetTrash.msg.emptyDone"))
    await load()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : t("datasetTrash.msg.fail"))
  } finally {
    busyId.value = ""
  }
}
</script>

<template>
  <ElDialog
    :model-value="modelValue"
    :title="title"
    width="560px"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div v-loading="loading" class="trash-dialog">
      <p v-if="!batches.length && !loading" class="trash-empty">{{ t("datasetTrash.empty") }}</p>
      <article v-for="batch in batches" :key="batch.id" class="trash-batch">
        <header class="trash-batch-header">
          <span>
            <strong v-if="isGlobal" class="trash-batch-dataset">{{ batch.dataset }}</strong>
            {{ t("datasetTrash.batchInfo", { count: batch.count, time: formatTime(batch.deleted_at) }) }}
          </span>
          <span class="trash-batch-actions">
            <button class="secondary-action" :disabled="!!busyId" @click="restore(batch)">{{ t("datasetTrash.restore") }}</button>
            <button class="danger-action" :disabled="!!busyId" @click="emptyBatch(batch)">{{ t("datasetTrash.deleteBatch") }}</button>
          </span>
        </header>
        <ul class="trash-batch-paths">
          <li v-for="path in batch.paths" :key="path">{{ path }}</li>
        </ul>
      </article>
    </div>
    <template #footer>
      <button class="secondary-action" :disabled="!!busyId" @click="emit('update:modelValue', false)">{{ t("datasetTrash.close") }}</button>
      <button class="danger-action" :disabled="!!busyId || !batches.length" @click="emptyAll">{{ t("datasetTrash.emptyAll") }}</button>
    </template>
  </ElDialog>
</template>
