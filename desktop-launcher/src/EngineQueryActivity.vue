<script setup lang="ts">
import { computed } from 'vue'
import { t } from './i18n'
import { formatBytes } from './localized-bytes'
import { cancelEngineQuery, engineQueries, engineQueryRoot, queryStageLabel, queryStatusLabel } from './engine-query'
import type { EngineQueryEntry } from './engine-query'
import Icon from './LauncherIcon.vue'

const props = defineProps<{ root: string; releaseId?: string; engineId?: string; entryId?: number; details?: boolean }>()
const visible = computed(() => engineQueries.value.filter(entry => !entry.finished && engineQueryRoot(entry.target.root) === engineQueryRoot(props.root) && (!props.releaseId || entry.target.release_id === props.releaseId) && (!props.engineId || entry.target.engine_id === props.engineId) && (props.entryId === undefined || entry.id === props.entryId)))
const name = (id: string) => id === 'gui' ? t('主程序重装准备') : ({ kohya: 'Kohya', 'anima-fast': 'Anima Fast', 'ai-toolkit': 'AI Toolkit', diffsynth: 'DiffSynth' } as Record<string, string>)[id] ?? id
const cancelPending = (entry: EngineQueryEntry) => Boolean(entry.snapshot?.cancel_requested || entry.snapshot?.status === 'cancelling' || (entry.cancelling && !entry.cancelError))
const cancelLabel = (entry: EngineQueryEntry) => entry.cancelError ? t('重试取消') : cancelPending(entry) ? entry.taskId ? t('正在取消…') : t('等待受理后取消…') : t('取消检查')
const statusLabel = (entry: EngineQueryEntry) => entry.cancelError ? t('取消请求未确认，可重试') : cancelPending(entry) ? entry.taskId ? queryStatusLabel('cancelling') : t('等待受理后取消…') : entry.snapshot ? queryStatusLabel(entry.snapshot.status) : t('正在准备检查')
async function cancel(entry: EngineQueryEntry) {
  try { await cancelEngineQuery(entry) }
  catch { /* The shared entry retains the failure and explicit retry action. */ }
}
</script>

<template>
  <div v-if="visible.length" class="engine-query-activities" :aria-label="t('正在进行的环境检查')">
    <section v-for="entry in visible" :key="entry.id" class="engine-query-activity" :data-query-task="entry.taskId" :data-query-status="entry.cancelling ? entry.cancelError ? 'cancel-retry' : 'cancelling' : entry.snapshot?.status ?? 'accepting'" :data-query-stage="entry.snapshot?.stage ?? 'identity'" :aria-label="t('{name} 环境检查', { name: name(entry.target.engine_id) })">
      <div class="query-heading"><Icon name="refresh" class="spin" /><strong>{{ name(entry.target.engine_id) }}</strong><span>{{ statusLabel(entry) }}</span><button :disabled="cancelPending(entry)" @click="cancel(entry)">{{ cancelLabel(entry) }}</button></div>
      <div class="query-progress" role="status"><span>{{ entry.snapshot ? queryStageLabel(entry.snapshot.stage) : t('正在准备检查') }}</span><span v-if="entry.snapshot?.progress.files !== null && entry.snapshot?.progress.files !== undefined">{{ t('已核对 {count} 个文件', { count: entry.snapshot.progress.files }) }}</span><span v-if="entry.snapshot?.progress.bytes !== null && entry.snapshot?.progress.bytes !== undefined">{{ t('已读取 {bytes}', { bytes: formatBytes(entry.snapshot.progress.bytes) }) }}</span></div>
      <p class="query-hint">{{ t('切换页面后检查继续。取消会停止整个共享检查，不会修改已安装环境。') }}</p>
      <p v-if="entry.connectionError" class="query-warning" role="status">{{ t('暂时无法读取进度，正在重新连接原检查；不会重新扫描。') }}</p>
      <p v-if="entry.cancelError" class="query-warning" role="alert">{{ t('取消请求未确认，检查仍在跟踪中；可点击“重试取消”。') }} {{ entry.cancelError }}</p>
      <details v-if="details && entry.taskId" class="query-details"><summary>{{ t('检查详情') }}</summary><code>{{ entry.taskId }}</code><p>{{ entry.target.release_id }} · {{ entry.target.scope === 'plan' ? t('准备安装或修复计划') : t('完整文件检查') }}</p><p v-if="entry.snapshot?.progress.message">{{ t(entry.snapshot.progress.message) }}</p></details>
    </section>
  </div>
</template>

<style scoped>
.engine-query-activities{display:grid;gap:8px;margin:12px 0;flex-shrink:0}.engine-query-activity{padding:12px 14px;background:var(--panel-soft);border:1px solid var(--line);border-radius:6px;color:var(--fg);font-size:12px}.query-heading{display:flex;align-items:center;gap:9px;min-width:0}.query-heading>svg{width:14px;height:14px;flex-shrink:0}.query-heading>strong{font-size:13px;font-weight:550;white-space:nowrap}.query-heading>span{color:var(--fg-secondary);min-width:0;overflow-wrap:anywhere}.query-heading>button{margin-left:auto;flex-shrink:0;font-size:12px;padding:5px 10px}.query-progress{display:flex;flex-wrap:wrap;gap:6px 16px;margin-top:8px;color:var(--fg-secondary);font-variant-numeric:tabular-nums}.query-hint,.query-warning{font-size:12px;line-height:1.6;margin:7px 0 0;color:var(--fg-muted)}.query-warning{color:var(--warning)}.query-details{margin-top:7px;color:var(--fg-muted);font-size:12px}.query-details summary{cursor:pointer}.query-details code{display:block;margin-top:5px;overflow-wrap:anywhere}.query-details p{margin:5px 0 0;overflow-wrap:anywhere}@media(prefers-reduced-motion:reduce){.spin{animation:none}}
</style>
