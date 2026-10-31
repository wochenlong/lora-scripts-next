<script setup lang="ts">
import { t, locale } from './i18n'
import AcrylicSelect from './AcrylicSelect.vue'
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import Icon from './LauncherIcon.vue'
import type { LogEntry, LogLevel, LogSource } from './log-model'
import { sourceLabels, normalizeLogRoot, fromLogRecord, mergeLogEntries } from './log-model'
import { readLogs } from './bridge'
import type { LogPage } from './bridge'
const props = defineProps<{ entries: LogEntry[]; active: boolean; root: string; focusRequest: { id: string; request: number } | null; fontSize: number; currentSessionId: string }>()
const source = ref<LogSource | 'all'>('all'), level = ref<LogLevel | 'all'>('all'), search = ref(''), follow = ref(true)
const mode = ref<'current' | 'history'>('current'), sessionFilter = ref(''), contextFilter = ref('')
const selected = ref<string | null>(null), notice = ref(''), scrollTop = ref(0), viewport = ref<HTMLElement>(), viewportHeight = ref(400)
const diskEntries = ref<LogEntry[]>([]), currentRecovered = ref<LogEntry[]>([]), diskSessionId = ref('')
const sessions = ref<LogPage['sessions']>([]), loading = ref(false), readError = ref(''), partial = ref(false), hasMore = ref(false), nextCursor = ref<number | null>(null), frozenHistory = ref(false)
let initialized = false, readEpoch = 0
let consumedFocusRequest = 0, locating = false
const rowHeight = 29, overscan = 8
let observer: ResizeObserver | undefined
const sameWorkspace = (entry: LogEntry) => normalizeLogRoot(entry.root) === normalizeLogRoot(props.root) || !entry.root
const currentSession = computed(() => props.currentSessionId || diskSessionId.value)
const currentEntries = computed(() => mergeLogEntries(currentRecovered.value, props.entries.filter(entry => sameWorkspace(entry) && (!entry.persisted || entry.sessionId === currentSession.value))))
const archiveEntries = computed(() => {
  const live = frozenHistory.value ? [] : props.entries.filter(entry => entry.persisted && sameWorkspace(entry) && (!sessionFilter.value || entry.sessionId === sessionFilter.value))
  return mergeLogEntries(diskEntries.value, live, frozenHistory.value ? 'oldest' : 'latest')
})
const entries = computed(() => (mode.value === 'current' ? currentEntries.value : archiveEntries.value).filter(entry => sameWorkspace(entry) && (!sessionFilter.value || mode.value === 'current' || entry.sessionId === sessionFilter.value)))
const contexts = computed(() => [...new Set(entries.value.map(entry => entry.context).filter((value): value is string => Boolean(value)))])
const filtered = computed(() => entries.value.filter(entry => (!contextFilter.value || (contextFilter.value === '__none' ? !entry.context : entry.context === contextFilter.value)) && (source.value === 'all' || source.value === entry.source) && (level.value === 'all' || level.value === entry.level) && entry.message.toLocaleLowerCase().includes(search.value.toLocaleLowerCase())))
const first = computed(() => Math.max(0, Math.floor(scrollTop.value / rowHeight) - overscan))
const visible = computed(() => filtered.value.slice(first.value, first.value + Math.ceil(viewportHeight.value / rowHeight) + overscan * 2))
const selectedEntry = computed(() => entries.value.find(entry => entry.id === selected.value))
const time = (value: number) => new Date(value).toLocaleTimeString(locale.value, { hour12: false })
const date = (value: number) => new Date(value).toLocaleString(locale.value, { hour12: false })
const historyTime = (value: number) => new Date(value).toLocaleString(locale.value, { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
const sessionLabel = (id: string) => { const session = sessions.value.find(item => item.session_id === id); return session ? `${date(session.started_at)} · ${id.slice(-8)}` : id }
const asText = (entry: LogEntry) => `${date(entry.receivedAt)}\t${entry.level === 'UNKNOWN' ? t("未分类") : entry.level}\t${t(sourceLabels[entry.source])}\t${entry.root || t("未提供工作区")}\t${entry.sessionId ?? t("界面记录，未写入历史")}\t${entry.context ?? t("未关联运行")}\t${entry.message}`
async function loadArchive(earlier = false) {
  const root = props.root.trim()
  if (!root) { readError.value = t("请先检查安装目录，再读取此工作区的历史记录。"); return }
  if (earlier && (!hasMore.value || nextCursor.value === null || loading.value)) return
  const epoch = ++readEpoch, selectedMode = mode.value, selectedSession = sessionFilter.value
  loading.value = true; readError.value = ''; notice.value = ''
  const sessionId = selectedMode === 'current' ? currentSession.value || null : selectedSession || null
  try {
    const page = await readLogs(root, earlier ? nextCursor.value : null, sessionId)
    if (epoch !== readEpoch || normalizeLogRoot(root) !== normalizeLogRoot(props.root) || selectedMode !== mode.value || selectedSession !== sessionFilter.value) return
    diskSessionId.value = page.current_session_id; sessions.value = page.sessions
    const records = page.records.map(fromLogRecord)
    if (selectedMode === 'current') currentRecovered.value = mergeLogEntries(currentRecovered.value, records.filter(entry => entry.sessionId === page.current_session_id))
    else {
      diskEntries.value = earlier ? mergeLogEntries(diskEntries.value, records, 'oldest') : mergeLogEntries([], records)
      frozenHistory.value = earlier
      if (earlier) { follow.value = false; scrollTop.value = 0; if (viewport.value) viewport.value.scrollTop = 0 }
    }
    hasMore.value = page.has_more; nextCursor.value = page.next_before_seq
    partial.value = page.partial; readError.value = page.io_error ?? ''; initialized = true
    if (!earlier && follow.value) await scrollBottom()
  } catch (reason) { if (epoch === readEpoch) readError.value = t('历史读取失败，已保留当前显示：{reason}', { reason: String(reason) }) }
  finally { if (epoch === readEpoch) loading.value = false }
}
async function scrollBottom() { await nextTick(); if (viewport.value) viewport.value.scrollTop = viewport.value.scrollHeight }
function onScroll() {
  if (!viewport.value) return
  scrollTop.value = viewport.value.scrollTop
  const bottom = viewport.value.scrollHeight - viewport.value.scrollTop - viewport.value.clientHeight < rowHeight * 2
  if (!bottom && follow.value) follow.value = false
}
async function toggleFollow() { follow.value = !follow.value; if (follow.value) await scrollBottom() }
async function locate(id: string) {
  mode.value = 'current'
  await nextTick()
  source.value = 'all'; level.value = 'all'; search.value = ''; contextFilter.value = ''; selected.value = id; follow.value = false
  await nextTick()
  const index = filtered.value.findIndex(entry => entry.id === id)
  if (viewport.value && index >= 0) viewport.value.scrollTop = Math.max(0, index * rowHeight - viewport.value.clientHeight / 2)
}
function consumeFocusRequest() {
  const request = props.focusRequest
  if (!props.active || !request || request.request === consumedFocusRequest) return false
  consumedFocusRequest = request.request
  locating = true
  void locate(request.id).finally(() => { locating = false })
  return true
}
async function copy(selection = false) {
  try { await navigator.clipboard.writeText(selection && selectedEntry.value ? asText(selectedEntry.value) : filtered.value.map(asText).join('\n')); notice.value = '已复制脱敏日志' }
  catch { notice.value = '未能访问剪贴板，请在日志详情中选择文字复制。' }
}
function exportLogs() {
  const header = `${t('Next Trainer 启动器日志')}\n${t('导出时间：{time}', { time: date(Date.now()) })}\n${t('工作区：{root}', { root: props.root })}\n${t('范围：{scope}', { scope: mode.value === 'current' ? t('本次会话') : t('已加载的历史记录') })}\n${t('时间列为当时启动器接收时间；未提供来源或级别的原始日志保留为未分类。')}\n\n`
  const url = URL.createObjectURL(new Blob([header, filtered.value.map(asText).join('\n')], { type: 'text/plain;charset=utf-8' }))
  const link = document.createElement('a'); link.href = url; link.download = `next-trainer-logs-${new Date().toISOString().replace(/[:.]/g, '-')}.txt`; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000); notice.value = '已导出当前已加载并筛选后的脱敏日志'
}
watch(() => props.entries.at(-1)?.id, () => { if (follow.value && props.active && (mode.value === 'current' || !frozenHistory.value)) void scrollBottom() })
watch([source, level, search, contextFilter], () => { scrollTop.value = 0; if (viewport.value) viewport.value.scrollTop = 0 })
watch([mode, sessionFilter], () => { selected.value = null; contextFilter.value = ''; follow.value = mode.value === 'current'; frozenHistory.value = false; if (props.active) void loadArchive(); else initialized = false })
watch(() => props.root, () => { readEpoch++; loading.value = false; initialized = false; diskEntries.value = []; currentRecovered.value = []; sessions.value = []; selected.value = null; contextFilter.value = ''; sessionFilter.value = ''; readError.value = ''; partial.value = false; hasMore.value = false; nextCursor.value = null; if (props.active) void loadArchive() })
watch(() => props.focusRequest?.request, () => { consumeFocusRequest() })
watch(() => props.active, async value => {
  if (!value) return
  await nextTick()
  if (viewport.value) { observer?.disconnect(); observer = new ResizeObserver(([entry]) => { if (entry) viewportHeight.value = entry.contentRect.height }); observer.observe(viewport.value) }
  if (!initialized) void loadArchive()
  if (!consumeFocusRequest() && !locating && follow.value) await scrollBottom()
}, { immediate: true })
onBeforeUnmount(() => { readEpoch++; observer?.disconnect() })
</script>
<template>
  <section class="logs-page" :data-log-scope="mode" :data-loaded-count="entries.length" :data-current-session="currentSession" :class="{ 'history-mode': mode === 'history' }" :style="{ '--log-font-size': `${fontSize}px` }" :aria-label="t('集中日志')">
    <header class="page-title"><h1>{{ t("日志") }}</h1><p>{{ t("集中查看启动器、服务和环境操作的记录。") }}</p></header>
    <slot name="operation"></slot>
    <div class="log-scope-controls"><div class="scope-tabs" role="group" :aria-label="t('日志范围')"><button :class="{ selected: mode === 'current' }" @click="mode = 'current'">{{ t("本次会话") }}</button><button :class="{ selected: mode === 'history' }" @click="mode = 'history'">{{ t("历史记录") }}</button></div><AcrylicSelect v-if="mode === 'history'" v-model="sessionFilter" :aria-label="t('历史会话')" :options="[{ value: '', label: t('全部已保存会话') }, ...sessions.map(session => ({ value: session.session_id, label: `${sessionLabel(session.session_id)}${session.session_id === currentSession ? t(' · 本次') : ''} · ${t('{count} 行', { count: session.retained_records })}` }))]" /><AcrylicSelect v-model="contextFilter" :aria-label="t('运行或操作分组')" :options="[{ value: '', label: t('所有运行与操作') }, { value: '__none', label: t('未关联运行') }, ...contexts.map(context => ({ value: context, label: context }))]" /><button :disabled="loading" :title="t('重新读取最近保存的日志')" @click="frozenHistory = false; loadArchive()"><Icon name="refresh" />{{ loading ? t('读取中…') : t('刷新最新') }}</button></div>
    <div v-if="readError || partial" class="log-read-warning" role="status"><Icon name="info" /><span>{{ readError || t('部分日志无法读取，当前只显示已成功读取的记录。') }}</span><button :disabled="loading" @click="loadArchive()">{{ t("重试读取") }}</button></div>
    <div class="logs-toolbar"><div class="source-filters" role="group" :aria-label="t('日志来源')"><button v-for="item in (['all', 'launcher', 'service', 'environment', 'unknown'] as const)" :key="item" :class="{ selected: source === item }" @click="source = item">{{ item === 'all' ? t('全部') : t(sourceLabels[item]) }}</button></div><div class="logs-tools"><button class="icon-button" :title="t('复制可见日志')" :aria-label="t('复制可见日志')" @click="copy()"><Icon name="copy" /></button><button @click="exportLogs"><Icon name="down" />{{ t("导出") }}</button></div></div>
    <div class="log-controls"><label class="search-box"><Icon name="search" /><input v-model="search" :aria-label="t('搜索日志')" :placeholder="t('搜索当前已加载的日志…')" /></label><AcrylicSelect v-model="level" :aria-label="t('日志级别')" :options="[{ value: 'all', label: t('全部级别') }, { value: 'INFO', label: t('信息') }, { value: 'WARN', label: t('警告') }, { value: 'ERROR', label: t('错误') }, { value: 'UNKNOWN', label: t('未分类') }]" /><button v-if="mode === 'history'" class="load-earlier" :disabled="loading || !hasMore" @click="loadArchive(true)">{{ loading ? t('读取中…') : hasMore ? t('加载较早（最多 500 行）') : t('已到保留记录起点') }}</button><button v-else class="follow-button" :class="{ paused: !follow }" @click="toggleFollow"><span class="check-square">{{ follow ? '✓' : '' }}</span>{{ t("自动跟随") }}</button></div>
    <div class="terminal-columns" aria-hidden="true"><span>{{ t("接收时间") }}</span><span>{{ t("级别") }}</span><span>{{ t("来源") }}</span><span>{{ t("消息") }}</span></div>
    <div ref="viewport" class="terminal" role="region" tabindex="0" :aria-label="t('运行日志；上下滚动查看，选择一行查看完整内容')" @scroll="onScroll">
      <div v-if="!filtered.length" class="terminal-empty">{{ entries.length ? t('没有匹配的日志') : loading ? t('正在读取日志…') : mode === 'history' ? t('没有可显示的已保存记录。旧版未保存或已轮转移出的日志无法补回。') : t('等待操作，日志将在这里实时显示。') }}</div>
      <div v-else class="log-virtual-space" :style="{ height: `${filtered.length * rowHeight}px` }"><div class="log-visible-rows" :style="{ transform: `translateY(${first * rowHeight}px)` }"><button v-for="entry in visible" :key="entry.id" class="log-line" :class="{ highlight: entry.id === selected }" :data-level="entry.level" :data-log-id="entry.id" :data-log-persisted="entry.persisted" :title="`${date(entry.receivedAt)} · ${entry.context ?? t('未关联运行')}\n${entry.message}`" @click="selected = entry.id"><span class="log-time">{{ mode === 'history' ? historyTime(entry.receivedAt) : time(entry.receivedAt) }}</span><span class="log-level">{{ entry.level === 'UNKNOWN' ? '—' : entry.level }}</span><span class="log-source">{{ t(sourceLabels[entry.source]) }}</span><span class="log-message">{{ entry.message }}</span></button></div></div>
    </div>
    <div v-if="selectedEntry" class="log-detail"><div><span>{{ t(sourceLabels[selectedEntry.source]) }} · {{ date(selectedEntry.receivedAt) }} · {{ selectedEntry.persisted ? t('已保存 #{seq}', { seq: selectedEntry.seq ?? '' }) : t('界面记录，未写入历史') }}</span><button class="text-button" @click="copy(true)">{{ t("复制此行") }}</button><button class="icon-button" :aria-label="t('关闭日志详情')" @click="selected = null"><Icon name="close" /></button></div><span class="log-entry-context">{{ selectedEntry.root || t('未提供工作区') }} · {{ selectedEntry.context ?? t('未关联运行') }}</span><pre tabindex="0">{{ selectedEntry.message }}</pre></div>
    <footer class="log-footer"><span><i class="good-dot"></i>{{ mode === 'history' ? frozenHistory ? t('历史分页，保留较早显示窗口') : t('已保存记录') : follow ? t('实时跟随') : t('已暂停跟随，继续接收记录') }}</span><span>{{ t('{visible} / {total} 行', { visible: filtered.length, total: entries.length }) }}</span><span v-if="notice" role="status">{{ t(notice) }}</span><span v-else class="log-caption">{{ t("显示最多 2,000 行 · 时间为当时接收时间") }}</span><button v-if="mode === 'current' && !follow" class="text-button" @click="follow = true; scrollBottom()">{{ t("回到最新") }}</button></footer>
  </section>
</template>
<style scoped>
.log-scope-controls{display:flex;gap:10px;align-items:center;margin-top:18px;min-height:33px}.scope-tabs{display:flex;gap:0;flex-shrink:0;border-radius:5px;background:var(--control-bg);padding:2px}.scope-tabs button{background:none;border:0;border-radius:3px;padding:6px 11px;font-size:12px;color:var(--text-muted)}.scope-tabs button.selected{color:var(--text-strong);background:var(--control-selected)}.log-scope-controls>.acrylic-select{min-width:0;max-width:250px;font-size:12px;height:32px;flex:1}.log-scope-controls>button:not(.acrylic-select){margin-left:auto;font-size:12px;flex-shrink:0}.log-scope-controls>button:not(.acrylic-select) svg{width:14px;height:14px}.logs-toolbar{margin-top:12px}.log-read-warning{display:flex;align-items:center;gap:8px;background:var(--warning-bg);border:1px solid var(--warning-line);border-radius:4px;padding:7px 10px;margin-top:8px;font-size:12px;color:var(--warning);flex-shrink:0}.log-read-warning>span{flex:1;line-height:1.5;overflow-wrap:anywhere}.log-read-warning svg{width:15px;height:15px}.log-read-warning button{font-size:12px;padding:3px 7px;flex-shrink:0}.load-earlier{margin-left:auto;font-size:12px;padding:6px 10px}.log-entry-context{font-size:12px;color:var(--text-muted);margin:4px 0;overflow-wrap:anywhere}.history-mode .terminal-columns,.history-mode .log-line{grid-template-columns:130px 58px 90px minmax(0,1fr)}.history-mode .log-time{font-size:12px}.log-footer{flex-shrink:0}.log-caption{overflow:hidden;text-overflow:ellipsis;min-width:0}@media(max-width:1080px){.log-scope-controls{gap:7px}.log-scope-controls>.acrylic-select{max-width:235px}.scope-tabs button{font-size:12px;padding:6px 8px}.log-scope-controls>button:not(.acrylic-select){padding:6px 8px}.log-footer{gap:10px}}@media(max-height:680px){.log-scope-controls{margin-top:11px}.logs-toolbar{margin-top:8px;margin-bottom:9px}.log-controls{margin-bottom:9px}.log-detail{max-height:120px}.log-read-warning{max-height:85px;overflow:auto}}
</style>
