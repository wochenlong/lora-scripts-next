<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { ElMessage } from "element-plus"
import { useI18n } from "vue-i18n"
import { systemApi, type UpdateCheckData } from "../api/system"
import { useTasksStore } from "../stores/tasks"

const { t } = useI18n()
const tasksStore = useTasksStore()
const loading = ref(false)
const data = ref<UpdateCheckData | null>(null)
const error = ref("")

const trainingBusy = computed(() =>
  tasksStore.tasks.some((task) => ["RUNNING", "QUEUED"].includes(task.status) && task.lane !== "maintenance"),
)

const statusKind = computed(() => {
  if (!data.value) return "idle"
  if (data.value.error) return "error"
  if (data.value.has_update) return "update"
  return "ok"
})

async function refresh(force = false) {
  loading.value = true
  error.value = ""
  try {
    data.value = await systemApi.checkUpdate(force)
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : t("settings.update.checkFail")
    ElMessage.error(error.value)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void tasksStore.refresh().catch(() => undefined)
  void refresh(false)
})
</script>

<template>
  <section class="settings-card update-center">
    <h2>{{ t("settings.update.title") }}</h2>
    <p class="update-lead">{{ t("settings.update.lead") }}</p>

    <div class="update-status" :data-kind="statusKind">
      <div class="update-row">
        <span class="update-label">{{ t("settings.update.current") }}</span>
        <strong>{{ data?.current ? `v${data.current}` : "—" }}</strong>
        <span v-if="data?.current_is_prerelease" class="update-chip">{{ t("settings.update.previewChip") }}</span>
      </div>
      <div class="update-row">
        <span class="update-label">{{ t("settings.update.latestStable") }}</span>
        <strong>{{ data?.latest ? `v${data.latest}` : "—" }}</strong>
        <span class="update-chip muted">{{ t("settings.update.stableOnly") }}</span>
      </div>
      <p v-if="statusKind === 'update'" class="update-banner">{{ t("settings.update.available", { version: data?.latest }) }}</p>
      <p v-else-if="statusKind === 'ok'" class="update-banner ok">{{ t("settings.update.uptoDate") }}</p>
      <p v-else-if="statusKind === 'error'" class="update-banner err">{{ t("settings.update.checkFailDetail", { error: data?.error || error }) }}</p>
    </div>

    <div class="form-actions">
      <button class="primary-action" :disabled="loading" @click="refresh(true)">
        {{ loading ? t("settings.update.checking") : t("settings.update.check") }}
      </button>
      <a
        class="secondary-action"
        :href="data?.release_url || 'https://github.com/wochenlong/lora-scripts-next/releases'"
        target="_blank"
        rel="noopener noreferrer"
      >{{ t("settings.update.openGithub") }}</a>
      <a
        class="secondary-action"
        :href="data?.modelscope_url || 'https://www.modelscope.cn/datasets/next-lab/release'"
        target="_blank"
        rel="noopener noreferrer"
      >{{ t("settings.update.openModelscope") }}</a>
    </div>

    <p v-if="trainingBusy" class="update-warn">{{ t("settings.update.trainingBusy") }}</p>

    <section v-if="data?.release_notes" class="update-notes">
      <h3>{{ t("settings.update.notes") }}</h3>
      <pre>{{ data.release_notes }}</pre>
    </section>

    <section class="update-howto">
      <h3>{{ t("settings.update.howtoTitle") }}</h3>
      <ol>
        <li>{{ t("settings.update.howto.1") }}</li>
        <li>{{ t("settings.update.howto.2") }}</li>
        <li>{{ t("settings.update.howto.3") }}</li>
      </ol>
      <p class="update-footnote">{{ t("settings.update.howtoFoot") }}</p>
    </section>
  </section>
</template>

<style scoped>
.update-lead {
  margin: 0 0 18px;
  color: var(--muted);
  line-height: 1.55;
}
.update-status {
  display: grid;
  gap: 10px;
  margin-bottom: 16px;
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: color-mix(in srgb, var(--surface) 92%, var(--bg));
}
.update-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.update-label {
  min-width: 7.5rem;
  color: var(--muted);
  font-size: 13px;
}
.update-chip {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  background: color-mix(in srgb, #5d4ce8 18%, transparent);
  color: #5d4ce8;
  font-size: 11px;
  font-weight: 700;
}
.update-chip.muted {
  background: color-mix(in srgb, var(--muted) 16%, transparent);
  color: var(--muted);
}
.update-banner {
  margin: 4px 0 0;
  color: #5d4ce8;
  font-weight: 650;
}
.update-banner.ok { color: #15803d; }
.update-banner.err { color: #b91c1c; font-weight: 500; }
.update-warn {
  margin: 12px 0 0;
  padding: 10px 12px;
  border-radius: 10px;
  background: color-mix(in srgb, #f59e0b 16%, transparent);
  color: #92400e;
  line-height: 1.45;
}
.update-notes,
.update-howto {
  margin-top: 20px;
}
.update-notes h3,
.update-howto h3 {
  margin: 0 0 8px;
  font-size: 15px;
}
.update-notes pre {
  margin: 0;
  padding: 12px;
  max-height: 180px;
  overflow: auto;
  border-radius: 10px;
  background: color-mix(in srgb, var(--bg) 80%, var(--surface));
  white-space: pre-wrap;
  font-size: 12px;
  line-height: 1.45;
}
.update-howto ol {
  margin: 0;
  padding-left: 1.2rem;
  color: var(--text);
  line-height: 1.55;
}
.update-footnote {
  margin: 10px 0 0;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.45;
}
.form-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
a.secondary-action {
  display: inline-flex;
  align-items: center;
  text-decoration: none;
}
</style>
