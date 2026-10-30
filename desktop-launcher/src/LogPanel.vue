<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import Icon from './LauncherIcon.vue'
import type { LogEntry, LogLevel, LogSource } from './log-model'
import { sourceLabels, normalizeLogRoot } from './log-model'
const props = defineProps<{ entries: LogEntry[]; active: boolean; root: string; focusId: number | null; fontSize: number }>()
const source = ref<LogSource | 'all'>('all'), level = ref<LogLevel | 'all'>('all'), search = ref(''), follow = ref(true)
const selected = ref<number | null>(null), notice = ref(''), scrollTop = ref(0), viewport = ref<HTMLElement>(), viewportHeight = ref(400)
const rowHeight = 29, overscan = 8
let observer: ResizeObserver | undefined
const entries = computed(() => props.entries.filter(entry => normalizeLogRoot(entry.root) === normalizeLogRoot(props.root) || !entry.root))
const filtered = computed(() => entries.value.filter(entry => (source.value === 'all' || source.value === entry.source) && (level.value === 'all' || level.value === entry.level) && entry.message.toLocaleLowerCase().includes(search.value.toLocaleLowerCase())))
const first = computed(() => Math.max(0, Math.floor(scrollTop.value / rowHeight) - overscan))
const visible = computed(() => filtered.value.slice(first.value, first.value + Math.ceil(viewportHeight.value / rowHeight) + overscan * 2))
const selectedEntry = computed(() => props.entries.find(entry => entry.id === selected.value))
const time = (value: number) => new Date(value).toLocaleTimeString('zh-CN', { hour12: false })
const asText = (entry: LogEntry) => `${time(entry.receivedAt)}\t${entry.level === 'UNKNOWN' ? '未分类' : entry.level}\t${sourceLabels[entry.source]}\t${entry.context ?? '本次会话'}\t${entry.message}`
async function scrollBottom() {
  await nextTick()
  if (viewport.value) viewport.value.scrollTop = viewport.value.scrollHeight
}
function onScroll() {
  if (!viewport.value) return
  scrollTop.value = viewport.value.scrollTop
  const bottom = viewport.value.scrollHeight - viewport.value.scrollTop - viewport.value.clientHeight < rowHeight * 2
  if (!bottom && follow.value) follow.value = false
}
async function toggleFollow() { follow.value = !follow.value; if (follow.value) await scrollBottom() }
function locate(id: number) {
  source.value = 'all'; level.value = 'all'; search.value = ''; selected.value = id; follow.value = false
  void nextTick(() => {
    const index = filtered.value.findIndex(entry => entry.id === id)
    if (viewport.value && index >= 0) viewport.value.scrollTop = Math.max(0, index * rowHeight - viewport.value.clientHeight / 2)
  })
}
async function copy(selection = false) {
  try { await navigator.clipboard.writeText(selection && selectedEntry.value ? asText(selectedEntry.value) : filtered.value.map(asText).join('\n')); notice.value = '已复制脱敏日志' }
  catch { notice.value = '未能访问剪贴板，请在日志详情中选择文字复制。' }
}
function exportLogs() {
  const header = `Next Trainer 启动器日志\n导出时间：${new Date().toLocaleString('zh-CN')}\n工作区：${props.root}\n时间列为本次会话接收时间；未提供来源或级别的原始日志保留为未分类。\n\n`
  const url = URL.createObjectURL(new Blob([header, filtered.value.map(asText).join('\n')], { type: 'text/plain;charset=utf-8' }))
  const link = document.createElement('a'); link.href = url; link.download = `next-trainer-logs-${new Date().toISOString().replace(/[:.]/g, '-')}.txt`; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000); notice.value = '已导出当前筛选后的脱敏日志'
}
watch(() => props.entries.length, () => { if (follow.value && props.active) void scrollBottom() })
watch([source, level, search], () => { scrollTop.value = 0; if (viewport.value) viewport.value.scrollTop = 0 })
watch(() => props.focusId, value => { if (value !== null) locate(value) })
watch(() => props.active, async value => {
  if (!value) return
  await nextTick()
  if (viewport.value) {
    observer?.disconnect(); observer = new ResizeObserver(([entry]) => { if (entry) viewportHeight.value = entry.contentRect.height }); observer.observe(viewport.value)
  }
  if (props.focusId !== null) locate(props.focusId)
  else if (follow.value) await scrollBottom()
}, { immediate: true })
onBeforeUnmount(() => observer?.disconnect())
</script>
<template>
  <section class="logs-page" :style="{ '--log-font-size': `${fontSize}px` }" aria-label="集中日志">
    <header class="page-title"><h1>日志</h1><p>集中查看启动器、服务和环境操作的记录。</p></header>
    <div class="logs-toolbar"><div class="source-filters" role="group" aria-label="日志来源"><button v-for="item in (['all', 'launcher', 'service', 'environment', 'unknown'] as const)" :key="item" :class="{ selected: source === item }" @click="source = item">{{ item === 'all' ? '全部' : sourceLabels[item] }}</button></div><div class="logs-tools"><button class="icon-button" title="复制可见日志" aria-label="复制可见日志" @click="copy()"><Icon name="copy" /></button><button @click="exportLogs"><Icon name="down" />导出</button></div></div>
    <div class="log-controls"><label class="search-box"><Icon name="search" /><input v-model="search" aria-label="搜索日志" placeholder="搜索日志…" /></label><select v-model="level" aria-label="日志级别"><option value="all">全部级别</option><option value="INFO">信息</option><option value="WARN">警告</option><option value="ERROR">错误</option><option value="UNKNOWN">未分类</option></select><button class="follow-button" :class="{ paused: !follow }" @click="toggleFollow"><span class="check-square">{{ follow ? '✓' : '' }}</span>自动跟随</button></div>
    <div class="terminal-columns" aria-hidden="true"><span>接收时间</span><span>级别</span><span>来源</span><span>消息</span></div>
    <div ref="viewport" class="terminal" role="region" tabindex="0" aria-label="运行日志；上下滚动查看，选择一行查看完整内容" @scroll="onScroll">
      <div v-if="!filtered.length" class="terminal-empty">{{ entries.length ? '没有匹配的日志' : '等待操作，日志将在这里实时显示。' }}</div>
      <div v-else class="log-virtual-space" :style="{ height: `${filtered.length * rowHeight}px` }"><div class="log-visible-rows" :style="{ transform: `translateY(${first * rowHeight}px)` }"><button v-for="entry in visible" :key="entry.id" class="log-line" :class="{ highlight: entry.id === selected }" :data-level="entry.level" :data-log-id="entry.id" :title="entry.message" @click="selected = entry.id"><span class="log-time">{{ time(entry.receivedAt) }}</span><span class="log-level">{{ entry.level === 'UNKNOWN' ? '—' : entry.level }}</span><span class="log-source">{{ sourceLabels[entry.source] }}</span><span class="log-message">{{ entry.message }}</span></button></div></div>
    </div>
    <div v-if="selectedEntry" class="log-detail"><div><span>{{ sourceLabels[selectedEntry.source] }} · {{ selectedEntry.context ?? '本次会话' }}</span><button class="text-button" @click="copy(true)">复制此行</button><button class="icon-button" aria-label="关闭日志详情" @click="selected = null"><Icon name="close" /></button></div><pre tabindex="0">{{ selectedEntry.message }}</pre></div>
    <footer class="log-footer"><span><i class="good-dot"></i>{{ follow ? '实时跟随' : '已暂停跟随，继续接收记录' }}</span><span>{{ filtered.length }} / {{ entries.length }} 行</span><span v-if="notice" role="status">{{ notice }}</span><span v-else class="log-caption">本次会话缓冲最近 2,000 行 · 时间为接收时间</span><button v-if="!follow" class="text-button" @click="follow = true; scrollBottom()">回到最新</button></footer>
  </section>
</template>
