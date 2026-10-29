<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { cancelOperation, chooseDirectory, listenToLogs, openTrainer, operationEvents, operationHistory, operationSnapshot, prefetchRelease, rollbackRelease, runCommand, runReleaseCommand, stopTrainer } from './bridge'
import type { OperationSnapshot, ReleaseCommand, Report, ReportCommand, VersionView } from './bridge'

type Page = 'launch' | 'versions' | 'environment'
interface Confirmation {
  title: string
  detail: string
  action: string
  destructive?: boolean
  execute: () => Promise<void>
}

const page = ref<Page>('launch')
const path = ref(localStorage.getItem('next-trainer-launcher-root') ?? localStorage.getItem('launcher-probe-root') ?? '')
const report = ref<Report | null>(null)
const pending = ref('')
const error = ref('')
const message = ref('正在检查安装状态…')
const logs = ref<string[]>([])
const logPanel = ref<HTMLPreElement>()
const confirmation = ref<Confirmation | null>(null)
const confirmationCancel = ref<HTMLButtonElement>()
const operation = ref<OperationSnapshot | null>(null)
const history = ref<OperationSnapshot[]>([])
let operationTimer: ReturnType<typeof setTimeout> | undefined
let disposed = false
let operationCursor = 0
let unlisten: (() => void) | undefined
let previousFocus: HTMLElement | null = null

const pageTitle = computed(() => ({ launch: '启动', versions: '版本管理', environment: '环境管理' })[page.value])
const sameRoot = computed(() => path.value.trim() === report.value?.root)
const versions = computed(() => report.value?.versions ?? [])
const currentVersion = computed(() => versions.value.find((version) => version.id === report.value?.current_release) ?? versions.value.find((version) => version.current))
const defaultRelease = computed(() => versions.value.find((version) => version.channel === 'dev') ?? versions.value[0])
const installTarget = computed(() => currentVersion.value ?? defaultRelease.value)
const rollbackVersion = computed(() => versions.value.find((version) => version.id === report.value?.previous_known_good))
const ready = computed(() => Boolean(sameRoot.value && report.value?.uv && report.value?.python && report.value?.source && report.value?.environment && report.value?.frontend))
const busy = computed(() => Boolean(pending.value) || operation.value?.status === 'running')
const phaseText: Record<OperationSnapshot['phase'], string> = { preparing: '准备中', downloading: '正在下载', executing: '正在执行', verifying: '正在校验', committing: '正在保存', recovering: '正在恢复' }
const operationStatusText: Record<OperationSnapshot['status'], string> = { running: '进行中', succeeded: '已完成', failed: '失败', cancelled: '已取消', interrupted: '上次操作未完整结束' }
const running = computed(() => Boolean(report.value?.running))
const mutationDisabled = computed(() => busy.value || !sameRoot.value || running.value)
const installed = computed(() => Boolean(currentVersion.value?.installed || report.value?.source))
const rollbackAvailable = computed(() => Boolean(rollbackVersion.value?.installed && rollbackVersion.value.source_ok && rollbackVersion.value.environment_ok && rollbackVersion.value.id !== currentVersion.value?.id))
const channels = computed(() => {
  const listed = ['main', 'dev', ...versions.value.map((version) => version.channel)]
  return [...new Set(listed)].map((channel) => ({ channel, versions: versions.value.filter((version) => version.channel === channel) }))
})
const stateText = computed(() => {
  if (!report.value) return '等待检查'
  if (!sameRoot.value) return '目录待检查'
  if (report.value.healthy) return '服务已就绪'
  if (running.value) return '进程运行中'
  if (ready.value) return '可以启动'
  if (installed.value) return '需要修复'
  return '尚未安装'
})
const stateGood = computed(() => sameRoot.value && (report.value?.healthy || ready.value))
const statusItems = computed(() => [
  { label: '基础工具', ok: report.value?.uv && report.value?.python, detail: 'uv / 自管 Python' },
  { label: '训练器源码', ok: report.value?.source, detail: currentVersion.value ? `${currentVersion.value.channel} · ${currentVersion.value.commit.slice(0, 8)}` : '尚未选择版本' },
  { label: '运行环境', ok: report.value?.environment, detail: '主程序独立环境' },
  { label: '网页资源', ok: report.value?.frontend, detail: '训练器前端' },
])
const primaryLabel = computed(() => {
  if (!report.value || !sameRoot.value) return '检查安装状态'
  if (!installed.value) return '安装训练器'
  if (!ready.value) return '检查并修复'
  return '启动训练器'
})
const primaryDisabled = computed(() => busy.value || running.value || (Boolean(report.value) && sameRoot.value && !installed.value && !installTarget.value))
const installDownloadBytes = computed(() => installTarget.value?.download_bytes ?? 0)

function formatBytes(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '未提供'
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB']
  let value = bytes
  let index = 0
  while (value >= 1024 && index < units.length - 1) { value /= 1024; index += 1 }
  return `${value.toFixed(index > 0 ? 1 : 0)} ${units[index]}`
}
function channelName(channel: string) {
  if (channel === 'main') return 'main（稳定线）'
  if (channel === 'dev') return 'dev（开发线）'
  return channel
}
function releaseState(version: VersionView) {
  if (!version.installed) return '未安装'
  if (!version.source_ok) return '源码需修复'
  if (!version.environment_ok) return '环境需修复'
  return '检查通过'
}
function protectedRelease(version: VersionView) {
  return version.current || version.id === report.value?.current_release || version.id === report.value?.previous_known_good
}
function addLog(line: string) {
  logs.value.push(line)
  if (logs.value.length > 1000) logs.value.splice(0, logs.value.length - 1000)
  void nextTick(() => { if (logPanel.value) logPanel.value.scrollTop = logPanel.value.scrollHeight })
}
function acceptReport(value: Report) {
  const rootChanged = report.value?.root !== value.root
  report.value = { ...value, versions: value.versions ?? [], interrupted: value.interrupted ?? [] }
  path.value = value.root
  localStorage.setItem('next-trainer-launcher-root', value.root)
  if (!logs.value.length && value.logs.length) value.logs.forEach(addLog)
  if (rootChanged) {
    if (operationTimer) clearTimeout(operationTimer)
    operation.value = null
    operationCursor = 0
    history.value = []
    void refreshHistory().catch((reason) => { error.value = errorText(reason) })
  }
  if (value.error) throw new Error(value.error)
}
async function refreshHistory() {
  const root = path.value.trim()
  const loaded = await operationHistory(root)
  if (!disposed && path.value.trim() === root) history.value = loaded.sort((a, b) => b.started_at - a.started_at).slice(0, 5)
}
async function pollOperation() {
  const current = operation.value
  if (!current || disposed) return
  try {
    const next = await operationSnapshot(current.id)
    // 游标失效时以快照为准；当前会话的事件随后从新游标继续。
    try {
      (await operationEvents(current.id, operationCursor)).forEach((event) => { addLog(event.message); operationCursor = Math.max(operationCursor, event.seq) })
    } catch (reason) {
      if (!errorText(reason).includes('事件游标已过期')) throw reason
      operationCursor = Math.max(operationCursor, next.event_seq)
      addLog('部分较早事件已过期，已重新读取完整状态。')
    }
    operation.value = next
    message.value = `${phaseText[next.phase]} · ${operationStatusText[next.status]}`
    if (next.error) error.value = next.error.message
    if (next.status !== 'running') { await refreshHistory(); return }
  } catch (reason) { error.value = errorText(reason) }
  if (!disposed) operationTimer = setTimeout(() => { void pollOperation() }, 250)
}
async function prefetch(version: VersionView) {
  if (busy.value) return
  pending.value = '准备下载'
  error.value = ''
  try {
    operation.value = await prefetchRelease(path.value.trim(), version.id)
    operationCursor = 0
    message.value = '正在准备安装文件'
    void pollOperation()
  } catch (reason) { error.value = errorText(reason) }
  finally { pending.value = '' }
}
async function cancelDownload() {
  if (!operation.value || operation.value.status !== 'running') return
  try {
    const receipt = await cancelOperation(operation.value.id)
    message.value = receipt === 'commit_in_progress' ? '正在保存操作结果，请等待本次保存完成。' : '已请求取消，正在保存可恢复的下载进度…'
    operation.value = await operationSnapshot(operation.value.id)
  } catch (reason) { error.value = errorText(reason) }
}
function errorText(value: unknown): string {
  if (value instanceof Error) return value.message
  if (typeof value === 'string') return value
  return JSON.stringify(value) ?? String(value)
}
async function perform(label: string, action: () => Promise<void>) {
  if (busy.value) return
  pending.value = label
  error.value = ''
  message.value = `${label}…`
  try { await action(); message.value = `${label}完成` }
  catch (reason) {
    error.value = errorText(reason)
    message.value = `${label}失败，可查看日志后重试`
    addLog(`[失败] ${error.value}`)
  } finally { pending.value = '' }
}
function command(command: ReportCommand, label: string) {
  return perform(label, async () => acceptReport(await runCommand(command, path.value.trim())))
}
function releaseCommand(command: ReleaseCommand, version: VersionView, label: string) {
  return perform(label, async () => acceptReport(await runReleaseCommand(command, path.value.trim(), version.id)))
}
async function ask(value: Confirmation) {
  previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
  confirmation.value = value
  await nextTick()
  confirmationCancel.value?.focus()
}
function dismissConfirmation() {
  confirmation.value = null
  previousFocus?.focus()
  previousFocus = null
}
async function confirmAction() {
  const action = confirmation.value?.execute
  dismissConfirmation()
  await action?.()
}
function trapDialogFocus(event: KeyboardEvent) {
  if (event.key !== 'Tab') return
  const buttons = [...(event.currentTarget as HTMLElement).querySelectorAll<HTMLButtonElement>('button:not(:disabled)')]
  const first = buttons[0]
  const last = buttons[buttons.length - 1]
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
}
function install(version: VersionView) {
  return releaseCommand('install_release', version, `安装 ${channelName(version.channel)} ${version.version}`)
}
function select(version: VersionView) {
  if (version.channel === 'dev') return ask({
    title: '切换到 dev 开发线',
    detail: `将切换到 ${version.version}（${version.commit.slice(0, 8)}）。开发线可能包含尚未稳定的改动，训练任务与插件的兼容性需要自行确认。当前版本会保留，上一已健康版本可用于回退。`,
    action: '确认切换到 dev',
    execute: () => releaseCommand('select_release', version, '切换到 dev 开发线'),
  })
  return releaseCommand('select_release', version, `切换到 ${channelName(version.channel)}`)
}
function remove(version: VersionView) {
  return ask({
    title: '删除已安装版本',
    detail: `将删除 ${channelName(version.channel)} ${version.version}（${version.commit.slice(0, 8)}）的受管版本目录。共享用户资料目录 ${report.value?.profile_path ?? ''} 会保留。之后使用此版本需要重新安装。`,
    action: '删除此版本',
    destructive: true,
    execute: () => releaseCommand('remove_release', version, '删除已安装版本'),
  })
}
function rollback() {
  if (!rollbackVersion.value) return
  return perform('回退到上一已健康版本', async () => acceptReport(await rollbackRelease(path.value.trim())))
}
function primary() {
  if (!report.value || !sameRoot.value) return command('inspect', '检查安装状态')
  if (!installed.value && installTarget.value) return install(installTarget.value)
  if (!ready.value) { page.value = 'environment'; return }
  return command('start_trainer', '启动训练器')
}
function browse() {
  return perform('选择目录', async () => {
    const selected = await chooseDirectory()
    if (selected) acceptReport(await runCommand('inspect', selected))
  })
}
function stop() {
  return perform('停止训练器', async () => {
    await stopTrainer()
    acceptReport(await runCommand('inspect', path.value.trim()))
  })
}
function open() { return perform('打开训练器', openTrainer) }
onMounted(async () => {
  try { unlisten = await listenToLogs(addLog) }
  catch { addLog('桌面事件接口尚未连接；请通过桌面启动器打开此页面。') }
  await command('inspect', '检查安装状态')
  try { await refreshHistory() } catch (reason) { error.value = errorText(reason) }
})
onBeforeUnmount(() => { disposed = true; if (operationTimer) clearTimeout(operationTimer); unlisten?.() })
</script>

<template>
  <div class="app-shell" :aria-busy="busy">
    <aside class="sidebar">
      <div class="brand"><span class="brand-mark" aria-hidden="true">N</span><div>Next Trainer<small>桌面启动器</small></div></div>
      <nav aria-label="主导航">
        <button :class="{ selected: page === 'launch' }" :aria-current="page === 'launch' ? 'page' : undefined" @click="page = 'launch'"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="m6 3 10 7-10 7Z" /></svg>启动</button>
        <button :class="{ selected: page === 'versions' }" :aria-current="page === 'versions' ? 'page' : undefined" @click="page = 'versions'"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3 4h14v12H3zM3 8h14M7 8v8" /></svg>版本管理</button>
        <button :class="{ selected: page === 'environment' }" :aria-current="page === 'environment' ? 'page' : undefined" @click="page = 'environment'"><svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3 5h14M3 10h14M3 15h14M7 3v4M13 8v4M8 13v4" /></svg>环境管理</button>
      </nav>
      <div class="sidebar-foot"><span class="development-tag">0.2 开发版</span><p>Next Trainer Launcher<br>独立启动与环境恢复</p></div>
    </aside>

    <main>
      <header class="page-heading"><h1>{{ pageTitle }}</h1><span class="state-pill" :class="{ good: stateGood }"><i aria-hidden="true"></i>{{ stateText }}</span></header>
      <section class="directory-panel" aria-labelledby="directory-label">
        <label id="directory-label" for="install-root">安装目录</label>
        <div class="directory-input"><input id="install-root" v-model="path" :disabled="busy || running" placeholder="首次检查将使用默认目录" spellcheck="false" @keydown.enter="command('inspect', '检查安装状态')" /><button :disabled="busy || running" @click="browse">选择…</button><button :disabled="busy" @click="command('inspect', '检查安装状态')">检查</button></div>
      </section>

      <div class="page-content">
        <section v-if="operation" class="interrupted-note" role="status" aria-live="polite"><strong>{{ phaseText[operation.phase] }} · {{ operationStatusText[operation.status] }}</strong><p>准备安装文件；完整校验通过后可继续安装此版本。</p><button v-if="operation.status === 'running'" :disabled="operation.cancel_requested" @click="cancelDownload">{{ operation.cancel_requested ? '正在取消…' : '取消下载' }}</button><p v-if="operation.error">{{ operation.error.message }}</p></section>
        <section v-else-if="history.some((item) => item.status === 'interrupted')" class="interrupted-note" role="status"><strong>上次下载未完整结束</strong><p>可在版本管理中重新准备安装文件，继续下载；当前安装状态请重新检查。</p></section>
        <section v-if="report?.interrupted.length && sameRoot" class="interrupted-note" role="status"><strong>检测到未完成的操作</strong><ul><li v-for="(item, index) in report.interrupted" :key="index">{{ item }}</li></ul><span>请重新检查后重试对应安装或修复步骤。</span></section>
        <template v-if="page === 'launch'">
          <section class="summary-grid" aria-label="实际安装状态"><div v-for="item in statusItems" :key="item.label" class="summary-item"><div><span class="status-dot" :class="{ ok: sameRoot && item.ok }" aria-hidden="true"></span><strong>{{ item.label }}</strong><span class="status-word">{{ !report || !sameRoot ? '待检查' : item.ok ? '已就绪' : '待处理' }}</span></div><small>{{ item.detail }}</small></div></section>
          <section v-if="!installed" class="welcome-panel" aria-labelledby="welcome-title"><h2 id="welcome-title">安装 Next Trainer</h2><p>选择安装目录后，一次完成基础工具、训练器和主程序运行环境的安装。</p><div class="first-release"><span>{{ currentVersion ? '当前选择' : '默认安装' }}</span><strong>{{ installTarget ? channelName(installTarget.channel) : '等待发布清单' }}</strong><code v-if="installTarget">{{ installTarget.version }} · {{ installTarget.commit.slice(0, 8) }}</code></div><p v-if="installTarget?.channel === 'dev'" class="hint">当前安装包默认使用 dev 开发线；版本来自内置发布清单。可在版本管理中查看和安装 main 稳定线。</p><p class="hint">需要联网，建议预留至少 3 GiB。{{ installDownloadBytes ? `源码制品下载 ${formatBytes(installDownloadBytes)}，` : '' }}另外还需下载基础工具与主程序依赖；GPU 训练环境按引擎另行安装。</p></section>
          <section v-else class="current-panel" aria-labelledby="current-title"><div class="section-caption"><h2 id="current-title">当前训练器</h2><button class="text-button" :disabled="busy" @click="page = 'versions'">管理版本</button></div><div class="current-version"><strong>{{ currentVersion?.version ?? report?.version ?? '版本信息待检查' }}</strong><span v-if="currentVersion" class="line-tag">{{ channelName(currentVersion.channel) }}</span><code v-if="currentVersion">{{ currentVersion.commit.slice(0, 12) }}</code></div><p class="hint">{{ report?.healthy ? `训练器网页已就绪：http://127.0.0.1:${report.port}` : ready ? '主程序检查通过，可以启动训练器。' : '当前安装有缺失或检查未通过，请在环境管理中检查并修复。' }}</p></section>
          <section class="launch-bar" aria-label="训练器运行控制"><div><strong>{{ pending || (report?.healthy ? '服务已就绪' : ready ? '准备就绪' : installed ? '需要处理检查项' : '开始安装') }}</strong><small>{{ busy ? '请等待当前步骤完成，详细进度见下方日志。' : '启动状态以实际检查与服务响应为准。' }}</small></div><div class="launch-buttons"><button v-if="running" :disabled="busy" @click="stop">停止</button><button v-if="report?.healthy" :disabled="busy" @click="open">在浏览器打开</button><button v-if="!running" class="primary" :disabled="primaryDisabled" @click="primary">{{ primaryLabel }}</button></div></section>
          <section v-if="report?.profile_path && sameRoot" class="profile-info"><span>共享用户资料</span><code>{{ report.profile_path }}</code></section>
        </template>

        <template v-else-if="page === 'versions'">
          <div class="section-caption"><h2>内置发布清单</h2><span>固定制品，尚未查询远端更新</span></div>
          <section class="rollback-panel"><div><strong>上一已健康版本</strong><p v-if="rollbackVersion"><span>{{ channelName(rollbackVersion.channel) }} · {{ rollbackVersion.version }}</span><code>{{ rollbackVersion.commit.slice(0, 8) }}</code></p><p v-else>尚无可回退记录。版本成功启动并通过健康检查后会记录。</p></div><button :disabled="mutationDisabled || !rollbackAvailable" @click="rollback">回退到此版本</button></section>
          <p v-if="rollbackVersion && !rollbackAvailable" class="inline-note">回退目标尚未安装完整或存在检查问题，请先修复对应版本。</p>
          <section v-for="group in channels" :key="group.channel" class="channel-section" :aria-label="channelName(group.channel)"><h3>{{ channelName(group.channel) }}<span>{{ group.channel === 'dev' ? '包含开发中的改动' : group.channel === 'main' ? '稳定发布线' : '内置版本' }}</span></h3><p v-if="!group.versions.length" class="empty-channel">内置清单尚未提供此发布线的版本。</p><article v-for="version in group.versions" :key="version.id" class="version-card" :aria-label="`${version.channel} ${version.version} ${version.commit.slice(0, 8)}`"><div class="version-top"><div><strong>{{ version.version }}</strong><span v-if="version.current || version.id === report?.current_release" class="current-tag">当前使用</span><span v-else-if="version.id === report?.previous_known_good" class="healthy-tag">回退保留</span><span v-else-if="version.known_good" class="healthy-tag">曾健康启动</span></div><span class="release-state" :class="{ good: version.installed && version.source_ok && version.environment_ok }">{{ releaseState(version) }}</span></div><dl class="version-details"><div><dt>提交</dt><dd><code>{{ version.commit }}</code></dd></div><div><dt>下载</dt><dd><code>{{ formatBytes(version.download_bytes) }}</code><span class="detail-note">源码制品</span></dd></div><div><dt>磁盘</dt><dd><code>{{ formatBytes(version.source_bytes) }}</code><span class="detail-note">{{ version.installed ? '源码展开；运行环境另计' : '预计源码展开；运行环境另计' }}</span></dd></div><div v-if="version.installed"><dt>检查</dt><dd><span :class="{ 'check-warning': !version.source_ok }">源码{{ version.source_ok ? '完整' : '需修复' }}</span><span class="detail-separator">/</span><span :class="{ 'check-warning': !version.environment_ok }">环境{{ version.environment_ok ? '通过' : '需修复' }}</span></dd></div></dl><div class="version-actions"><button :disabled="mutationDisabled" @click="install(version)">{{ version.installed ? '检查并补全安装' : '下载安装' }}</button><button :disabled="mutationDisabled || !version.installed || !version.source_ok || !version.environment_ok || version.current || version.id === report?.current_release" @click="select(version)">切换到此版本</button><button class="delete-button" :disabled="mutationDisabled || !version.installed || protectedRelease(version)" :title="protectedRelease(version) ? '当前版本及上一已健康版本需保留' : '删除受管版本目录'" @click="remove(version)">删除</button></div></article></section>
          <p class="scope-note">已安装表示版本目录存在，不代表可以运行。切换依据每个版本的实际检查；当前版本和上一已健康版本受删除保护。main / dev 使用发布线与提交区分，即使版本号相同也分别管理。</p>
          <section class="environment-actions" aria-label="准备版本安装文件"><button v-for="version in versions" :key="version.id" :disabled="mutationDisabled" @click="prefetch(version)">准备 {{ channelName(version.channel) }} 安装文件</button></section>
        </template>

        <template v-else>
          <div class="section-caption"><h2>主程序与基础工具</h2><button class="compact" :disabled="busy" @click="command('inspect', '检查安装状态')">重新检查</button></div>
          <p class="environment-scope">当前检查覆盖启动器基础工具、训练器主程序和网页资源。各独立训练引擎的 Python / Torch / GPU 诊断尚未接入。</p>
          <div v-if="report?.checks.length && sameRoot" class="checks" role="list" aria-label="环境检查明细"><div v-for="(check, index) in report.checks" :key="`${index}-${check.name}`" class="check-row" role="listitem"><span class="check-badge" :class="{ ok: check.ok }">{{ check.ok ? '通过' : '待处理' }}</span><div><strong>{{ check.name }}</strong><p>{{ check.detail }}</p></div></div></div>
          <p v-else class="scope-note">请先检查安装目录。训练器目录缺失或环境损坏时，桌面检查与修复入口仍可使用。</p>
          <div class="environment-actions"><button :disabled="mutationDisabled" @click="command('bootstrap', '准备基础工具')">准备基础工具</button><button :disabled="mutationDisabled" @click="command('restore_trainer', '恢复当前版本源码')">恢复当前版本源码</button><button :disabled="mutationDisabled" @click="command('install_environment', '安装或修复运行环境')">安装 / 修复运行环境</button></div>
          <p class="hint">源码恢复会将原目录移至备份；请留意日志中的路径和数据处理结果。运行中的训练器需先停止，才能安装或修复。</p>
          <section v-if="report?.profile_path && sameRoot" class="profile-info"><span>共享用户资料</span><code>{{ report.profile_path }}</code></section>
        </template>
      </div>

      <section class="runtime-panel" aria-label="操作日志"><div class="runtime-status" role="status" aria-live="polite"><span class="working-dot" :class="{ active: pending }" aria-hidden="true"></span><span>{{ message }}</span><span class="log-count">{{ logs.length }} 行日志</span></div><p v-if="error" class="error" role="alert">{{ error }}</p><pre ref="logPanel" tabindex="0" aria-label="日志内容">{{ logs.length ? logs.join('\n') : '等待操作。检查结果以实际文件和运行探测为准。' }}</pre></section>
    </main>

    <div v-if="confirmation" class="dialog-backdrop" @keydown.esc.prevent="dismissConfirmation" @keydown="trapDialogFocus"><section class="confirmation-dialog" role="dialog" aria-modal="true" aria-labelledby="confirmation-title" aria-describedby="confirmation-detail"><h2 id="confirmation-title">{{ confirmation.title }}</h2><p id="confirmation-detail">{{ confirmation.detail }}</p><div><button ref="confirmationCancel" @click="dismissConfirmation">取消</button><button :class="confirmation.destructive ? 'danger' : 'primary'" @click="confirmAction">{{ confirmation.action }}</button></div></section></div>
  </div>
</template>
