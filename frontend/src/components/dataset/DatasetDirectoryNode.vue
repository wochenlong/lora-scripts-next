<script setup lang="ts">
import { ref } from "vue"
import { ArrowRight, Folder, Loading } from "@element-plus/icons-vue"
import { useI18n } from "vue-i18n"
import { pathBrowserApi, type PathBrowserEntry } from "../../api/pathBrowser"

const props = defineProps<{ name: string; path: string; locked?: boolean }>()
const emit = defineEmits<{ select: [path: string] }>()
const { t } = useI18n()
const expanded = ref(false)
const busy = ref(false)
const failed = ref(false)
const children = ref<PathBrowserEntry[]>([])

async function toggle() {
  expanded.value = !expanded.value
  if (!expanded.value) return
  busy.value = true
  failed.value = false
  try {
    children.value = (await pathBrowserApi.list(props.path, "folder")).entries.filter(item => item.type === "dir")
  } catch {
    failed.value = true
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <li class="dataset-directory-node">
    <div class="dataset-directory-line">
      <button class="dataset-icon-button" :aria-label="name" :aria-expanded="expanded" @click="toggle">
        <Loading v-if="busy" class="is-loading" /><ArrowRight v-else :class="{ expanded }" />
      </button>
      <button class="dataset-directory-name" :title="path" :disabled="locked" @click="emit('select', path)">
        <Folder /><span>{{ name }}</span>
      </button>
    </div>
    <ul v-if="expanded">
      <li v-if="failed" class="dataset-tree-hint">{{ t("datasetManage.loadErrorTitle") }}</li>
      <li v-else-if="!busy && !children.length" class="dataset-tree-hint">{{ t("datasetManage.noSubfolders") }}</li>
      <DatasetDirectoryNode v-for="child in children" :key="child.path" :name="child.name" :path="child.path" :locked="locked" @select="emit('select', $event)" />
    </ul>
  </li>
</template>
