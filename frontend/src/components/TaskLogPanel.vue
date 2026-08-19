<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue"
import { ElMessage } from "element-plus"
import { useI18n } from "vue-i18n"
import { tasksApi, trainLogStreamUrl, type TaskStatus } from "../api/tasks"
import { copyText } from "../utils/clipboard"

const props = defineProps<{ taskId: string; status: TaskStatus }>()
const { t } = useI18n()

const ERROR_RE = /\berror\b|\btraceback\b|out of memory|\boom\b/i
const PROBE_INTERVAL = 4000
const TAIL_INTERVAL = 2000

const open = ref(false)
const lines = ref<string[]>([])
const detectedError = ref(false)
const unavailable = ref(false)
const follow = ref(true)
const logBody = ref<HTMLElement>()
let eventSource: EventSource | undefined
let probeTimer: number | undefined
let tailTimer: number | undefined

const hasError = computed(() => props.status === "FAILED" || detectedError.value)
const logText = computed(() => lines.value.join("\n"))
const lastErrorIndex = computed(() => {
  for (let index = lines.value.length - 1; index >= 0; index--) {
    if (ERROR_RE.test(lines.value[index])) return index
  }
  return -1
})

function clearTimers() {
  if (probeTimer !== undefined) { window.clearInterval(probeTimer); probeTimer = undefined }
  if (tailTimer !== undefined) { window.clearInterval(tailTimer); tailTimer = undefined }
}

function closeStream() {
  eventSource?.close()
  eventSource = undefined
}

async function probe() {
  try {
    const data = await tasksApi.logTail(props.taskId, 240)
    unavailable.value = false
    if (data.lines.some((line) => ERROR_RE.test(line))) detectedError.value = true
    if (data.done && probeTimer !== undefined) { window.clearInterval(probeTimer); probeTimer = undefined }
  } catch {
    unavailable.value = true
    if (probeTimer !== undefined) { window.clearInterval(probeTimer); probeTimer = undefined }
  }
}

function startProbe() {
  clearTimers()
  closeStream()
  void probe()
  probeTimer = window.setInterval(probe, PROBE_INTERVAL)
}

function scrollToBottom() {
  if (!follow.value || !open.value) return
  void nextTick(() => {
    if (logBody.value) logBody.value.scrollTop = logBody.value.scrollHeight
  })
}

async function tailOnce() {
  try {
    const data = await tasksApi.logTail(props.taskId, 1000)
    unavailable.value = false
    lines.value = data.lines
    if (data.lines.some((line) => ERROR_RE.test(line))) detectedError.value = true
    scrollToBottom()
    if (data.done && tailTimer !== undefined) { window.clearInterval(tailTimer); tailTimer = undefined }
  } catch {
    unavailable.value = true
    if (tailTimer !== undefined) { window.clearInterval(tailTimer); tailTimer = undefined }
  }
}

function startTailPoll() {
  clearTimers()
  void tailOnce()
  tailTimer = window.setInterval(tailOnce, TAIL_INTERVAL)
}

function startStream() {
  clearTimers()
  lines.value = []
  if (typeof EventSource === "undefined") { startTailPoll(); return }
  const source = new EventSource(trainLogStreamUrl(props.taskId))
  eventSource = source
  source.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data) as { text?: string; done?: boolean }
      if (data.done) { closeStream(); return }
      if (typeof data.text === "string") {
        lines.value.push(data.text)
        if (!detectedError.value && ERROR_RE.test(data.text)) detectedError.value = true
        scrollToBottom()
      }
    } catch {}
  }
  source.onerror = () => { closeStream(); startTailPoll() }
}

function toggle() {
  open.value = !open.value
  if (open.value) startStream()
  else startProbe()
}

function onScroll() {
  const el = logBody.value
  if (!el) return
  follow.value = el.scrollTop + el.clientHeight >= el.scrollHeight - 8
}

function jumpToError() {
  const el = logBody.value
  if (!el || lastErrorIndex.value < 0) return
  follow.value = false
  const lineHeight = parseFloat(getComputedStyle(el).lineHeight) || 18
  el.scrollTop = Math.max(0, lastErrorIndex.value * lineHeight - el.clientHeight / 3)
}

async function copyLog() {
  try {
    await copyText(logText.value)
    ElMessage.success(t("tasks.log.copied"))
  } catch {
    ElMessage.error(t("tasks.log.copyFail"))
  }
}

function downloadLog() {
  const url = URL.createObjectURL(new Blob([logText.value], { type: "text/plain;charset=utf-8" }))
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = `train-log-${props.taskId}.txt`
  anchor.click()
  URL.revokeObjectURL(url)
}

watch(() => props.taskId, () => {
  open.value = false
  lines.value = []
  detectedError.value = false
  unavailable.value = false
  follow.value = true
  startProbe()
}, { immediate: true })

onBeforeUnmount(() => { clearTimers(); closeStream() })
</script>

<template>
  <section class="task-log-panel" :class="{ open }">
    <header class="log-header" @click="toggle">
      <span class="log-title">{{ t("tasks.log.title") }}<i v-if="hasError" class="log-alert" :title="t('tasks.log.errorBadge')"></i></span>
      <button class="log-toggle">{{ open ? t("tasks.log.collapse") : t("tasks.log.expand") }}</button>
    </header>
    <div v-if="open" class="log-body">
      <div class="log-toolbar">
        <button :class="{ active: follow }" @click.stop="follow = !follow; scrollToBottom()">{{ t("tasks.log.follow") }}</button>
        <button :disabled="lastErrorIndex < 0" @click.stop="jumpToError">{{ t("tasks.log.jumpToError") }}</button>
        <button :disabled="!lines.length" @click.stop="copyLog">{{ t("tasks.log.copy") }}</button>
        <button :disabled="!lines.length" @click.stop="downloadLog">{{ t("tasks.log.download") }}</button>
        <span class="log-count">{{ t("tasks.log.count", { n: lines.length }) }}</span>
      </div>
      <p v-if="unavailable" class="log-hint">{{ t("tasks.log.unavailable") }}</p>
      <p v-else-if="!lines.length" class="log-hint">{{ t("tasks.log.empty") }}</p>
      <pre v-else ref="logBody" class="log-lines" @scroll.passive="onScroll">{{ logText }}</pre>
    </div>
  </section>
</template>
