<script setup lang="ts">
import AcrylicSelect from './AcrylicSelect.vue'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { getCurrentWindow } from '@tauri-apps/api/window'
import { getVersion } from '@tauri-apps/api/app'
import { invoke } from '@tauri-apps/api/core'
import { runtimeStatus, listenToRuntime, startTrainer } from './bridge'
import type { RuntimePhase, RuntimeSnapshot } from './bridge'
import LogPanel from './LogPanel.vue'
import Icon from './LauncherIcon.vue'
import { createLogEntry, fromLogRecord } from './log-model'
import type { LogRecord } from './bridge'
import type { LogEntry, LogSource } from './log-model'
import { cancelOperation, chooseDirectory, diagnoseGui, installManagedRelease, listenToLogEntries, openTrainer, operationEvents, operationHistory, operationSnapshot, planGuiRepair, prefetchRelease, previewSourceRepair, recoverGuiRepair, repairGuiPackage, repairManagedSource, rollbackRelease, runCommand, runReleaseCommand, stopTrainer } from './bridge'
import type { GuiDiagnosis, GuiRepairPreview, OperationSnapshot, PackageIntegrity, ReleaseCommand, Report, ReportCommand, VersionView } from './bridge'
import { loadNetworkSettings, saveNetworkSettings } from './bridge'
import type { NetworkSettings, NetworkSettingsView } from './bridge'
import { settingsForSave } from './network-settings'
import type { ProxyField } from './network-settings'
import { previewBasePythonRepair, repairBasePython, recoverBasePython } from './bridge'
import type { BasePythonRepairPreview } from './bridge'
import { formatBytes as formatFileSize } from './bytes'
import { previewGuiRegistration, restoreGuiRegistration, recoverGuiRegistration } from './bridge'
import type { GuiRegistrationPreview } from './bridge'

import { previewGuiLifecycle, guiLifecycleHistory, applyGuiLifecycle } from './bridge'
import type { GuiLifecyclePreview, GuiLifecycleHistory, GuiLifecycleAction } from './bridge'
import EnginePanel from './EnginePanel.vue'
import TrustPanel from './TrustPanel.vue'
import ImportPanel from './ImportPanel.vue'
import ShellPanel from './ShellPanel.vue'

type Page = 'launch' | 'versions' | 'environment' | 'logs' | 'settings'
type Setting = 'appearance' | 'network' | 'profiles' | 'security' | 'about'
interface Confirmation {
  title: string
  detail: string
  action: string
  destructive?: boolean
  scope?: 'gui'
  paths?: string[]
  execute: () => Promise<void>
}

const page = ref<Page>('launch')
const path = ref(localStorage.getItem('next-trainer-launcher-root') ?? localStorage.getItem('launcher-probe-root') ?? '')
const report = ref<Report | null>(null)
const pending = ref('')
const error = ref('')
const message = ref('正在检查安装状态…')
const logs = ref<LogEntry[]>([])
let logSequence = 0
const visibleLogIds = new Set<string>()
const logFocus = ref<{ id: string; request: number } | null>(null)
let logFocusRequest = 0
const logSessionId = ref('')
const runtime = ref<RuntimeSnapshot | null>(null)
const optimisticPhase = ref<RuntimePhase | null>(null)
const serviceAction = ref('')
const requestedRunId = ref<string | null>(null)
let serviceEpoch = 0
let runtimeTimer: ReturnType<typeof setInterval> | undefined
let runtimeQueryPending = false
let runtimeUnlisten: (() => void) | undefined
const setting = ref<Setting>('appearance')
const sidebarExpanded = ref(false)
const sidebarToggle = ref<HTMLButtonElement>()
const informationTab = ref<'releases' | 'friends'>('releases')
const advanced = ref(false)
const appVersion = ref('0.2.0')
const toast = ref('')
const appearance = ref(loadAppearance())
const acrylicOpacity = computed(() => {
  const alpha = Math.round(179 * appearance.value.mask / 100)
  return { luminosity: .15 + .88 * alpha / 255, tint: Math.round(alpha * .861) / 255 }
})
const homeInk = ref({ titleDark: true, headingDark: true, controlsDark: true })
const backgroundInput = ref<HTMLInputElement>()
const confirmation = ref<Confirmation | null>(null)
const confirmationCancel = ref<HTMLButtonElement>()
const operation = ref<OperationSnapshot | null>(null)
const history = ref<OperationSnapshot[]>([])
const guiDiagnosis = ref<GuiDiagnosis | null>(null)
const guiPreview = ref<GuiRepairPreview | null>(null)
const basePythonPreview = ref<BasePythonRepairPreview | null>(null)
const registrationPreview = ref<GuiRegistrationPreview | null>(null)
const registrationReleaseId = ref('')
const registrationInstanceId = ref('')
const lifecyclePreview = ref<GuiLifecyclePreview | null>(null)
const lifecycleHistory = ref<GuiLifecycleHistory | null>(null)
const lifecycleTransaction = ref('')
const lifecycleAction = ref<GuiLifecycleAction>('rebuild')
const showAllPackages = ref(false)
const networkView = ref<NetworkSettingsView | null>(null)
const networkDraft = ref({ mode: 'auto' as NonNullable<NetworkSettings['mode']>, http_proxy: '', https_proxy: '', no_proxy: '' })
const networkInherit = ref<ProxyField[]>([])
let guiEpoch = 0
let operationTimer: ReturnType<typeof setTimeout> | undefined
let disposed = false
let operationCursor = 0
let unlisten: (() => void) | undefined
let previousFocus: HTMLElement | null = null

const sameRoot = computed(() => samePath(path.value, report.value?.root ?? ''))
const versions = computed(() => report.value?.versions ?? [])
const currentVersion = computed(() => versions.value.find((version) => version.id === report.value?.current_release) ?? versions.value.find((version) => version.current))
const defaultRelease = computed(() => versions.value.find((version) => version.channel === 'dev') ?? versions.value[0])
const installTarget = computed(() => currentVersion.value ?? defaultRelease.value)
const titlebarVersion = computed(() => {
  const version = currentVersion.value ?? installTarget.value
  return version ? `${version.version} · ${channelName(version.channel)}` : `启动器 ${appVersion.value}`
})
const rollbackVersion = computed(() => versions.value.find((version) => version.id === report.value?.previous_known_good))
const ready = computed(() => Boolean(sameRoot.value && report.value?.uv && report.value?.python && report.value?.source && report.value?.environment && report.value?.frontend))
const busy = computed(() => Boolean(pending.value) || operation.value?.status === 'running')
const phaseText: Record<OperationSnapshot['phase'], string> = { preparing: '准备中', downloading: '正在下载', executing: '正在执行', verifying: '正在校验', committing: '正在保存', recovering: '正在恢复' }
const operationStatusText: Record<OperationSnapshot['status'], string> = { running: '进行中', succeeded: '已完成', failed: '失败', cancelled: '已取消', interrupted: '上次操作未完整结束' }
const runtimePhase = computed<RuntimePhase>(() => optimisticPhase.value ?? (samePath(runtime.value?.root ?? '', path.value) ? runtime.value?.phase : null) ?? (sameRoot.value && report.value?.healthy ? 'ready' : sameRoot.value && report.value?.running ? 'degraded' : 'stopped'))
const healthy = computed(() => runtimePhase.value === 'ready')
const transitioning = computed(() => ['checking', 'starting', 'stopping'].includes(runtimePhase.value))
const running = computed(() => ['starting', 'ready', 'degraded', 'stopping', 'stop_failed'].includes(runtimePhase.value))
const serviceUrl = computed(() => healthy.value ? runtime.value?.url ?? (report.value?.port ? `http://127.0.0.1:${report.value.port}` : '') : '')
const mutationDisabled = computed(() => busy.value || !sameRoot.value || running.value || transitioning.value || Boolean(serviceAction.value))
const installed = computed(() => Boolean(currentVersion.value?.installed || report.value?.source))
const rollbackAvailable = computed(() => Boolean(rollbackVersion.value?.installed && rollbackVersion.value.source_ok && rollbackVersion.value.environment_ok && rollbackVersion.value.id !== currentVersion.value?.id))
const channels = computed(() => {
  const listed = ['main', 'dev', ...versions.value.map((version) => version.channel)]
  return [...new Set(listed)].map((channel) => ({ channel, versions: versions.value.filter((version) => version.channel === channel) }))
})
const runtimeLabels: Record<RuntimePhase, string> = { stopped: '服务已停止', checking: '正在检查启动条件', starting: '正在启动，等待服务', ready: '服务已就绪', degraded: '进程运行，服务暂不可达', stopping: '正在停止服务', exited: '服务已退出', start_failed: '启动失败', stop_failed: '停止失败，请查看日志' }
const stateText = computed(() => {
  if (transitioning.value || running.value || ['exited', 'start_failed', 'stop_failed'].includes(runtimePhase.value)) return runtimeLabels[runtimePhase.value]
  if (!report.value) return '等待检查'
  if (!sameRoot.value) return '目录待检查'
  if (ready.value) return '可以启动'
  return installed.value ? '需要修复' : '尚未安装'
})
const stateGood = computed(() => sameRoot.value && (healthy.value || (ready.value && !transitioning.value)))
const primaryLabel = computed(() => {
  if (!report.value || !sameRoot.value) return '检查安装状态'
  if (!installed.value) return '安装训练器'
  if (!ready.value) return '检查并修复'
  return '启动训练器'
})
const primaryDisabled = computed(() => busy.value || running.value || transitioning.value || Boolean(serviceAction.value) || (Boolean(report.value) && sameRoot.value && !installed.value && !installTarget.value))
const managedCurrent = computed(() => Boolean(sameRoot.value && currentVersion.value?.managed_recipe))
const registrationVersions = computed(() => versions.value.filter((version) => version.managed_recipe))
const registrationRelease = computed(() => registrationVersions.value.find((version) => version.id === registrationReleaseId.value)
  ?? (currentVersion.value?.managed_recipe ? currentVersion.value : registrationVersions.value[0]))
const guiRecoveryNeeded = computed(() => Boolean(guiDiagnosis.value?.dirty || guiDiagnosis.value?.recovery_pending || (guiDiagnosis.value && guiDiagnosis.value.generation !== guiDiagnosis.value.binding_generation)))
const affectedPackages = computed(() => guiDiagnosis.value?.integrity.packages.filter(packageNeedsAttention) ?? [])
const visiblePackages = computed(() => showAllPackages.value ? guiDiagnosis.value?.integrity.packages ?? [] : affectedPackages.value)
const guiPlanBlocked = computed(() => Boolean(guiRecoveryNeeded.value || guiDiagnosis.value?.source_error || guiDiagnosis.value?.installed_metadata_error))

watch([path, () => currentVersion.value?.id], clearGuiState, { flush: 'sync' })
watch(path, () => { runtime.value = null; optimisticPhase.value = null; serviceEpoch += 1; serviceAction.value = ''; requestedRunId.value = null; void syncRuntime(); networkView.value = null; networkInherit.value = []; networkDraft.value = { mode: 'auto', http_proxy: '', https_proxy: '', no_proxy: '' } }, { flush: 'sync' })
function acceptNetworkSettings(view: NetworkSettingsView) {
  networkView.value = view
  networkInherit.value = []
  networkDraft.value = { mode: view.settings.mode ?? 'auto', http_proxy: view.settings.http_proxy ?? '', https_proxy: view.settings.https_proxy ?? '', no_proxy: view.settings.no_proxy ?? '' }
}
async function readNetworkSettings() {
  const root = path.value.trim()
  await perform('读取网络设置', async () => {
    const view = await loadNetworkSettings(root)
    if (path.value.trim() === root) acceptNetworkSettings(view)
  })
}
async function storeNetworkSettings() {
  const root = path.value.trim()
  if (!networkView.value) return
  const settings = settingsForSave(networkView.value.settings, networkDraft.value, networkInherit.value)
  await perform('保存网络设置', async () => {
    const view = await saveNetworkSettings(root, settings)
    if (path.value.trim() === root) acceptNetworkSettings(view)
  })
}
function inheritNetworkField(key: ProxyField) {
  networkDraft.value[key] = ''
  if (!networkInherit.value.includes(key)) networkInherit.value.push(key)
}
function editNetworkField(key: ProxyField) {
  networkInherit.value = networkInherit.value.filter((field) => field !== key)
}

function clearGuiState() {
  guiEpoch += 1
  guiDiagnosis.value = null
  guiPreview.value = null
  basePythonPreview.value = null
  registrationPreview.value = null
  registrationInstanceId.value = ''
  lifecyclePreview.value = null
  lifecycleHistory.value = null
  lifecycleTransaction.value = ''
  showAllPackages.value = false
  if (confirmation.value?.scope === 'gui') dismissConfirmation()
}
function packageNeedsAttention(item: PackageIntegrity) {
  return item.status !== 'verified_original_files' || item.issues.length > 0 || item.generated.some((file) => file.kind === 'optional_derived_bytecode_unverified' && file.present)
}
function packageStatus(item: PackageIntegrity) {
  if (item.generated.some((file) => file.kind === 'optional_derived_bytecode_unverified' && file.present)) return '存在未验证字节码'
  return ({ verified_original_files: '原文件通过', missing: '文件缺失', damaged: '内容改变', unsupported: '需要进一步诊断' })[item.status] ?? '待检查'
}
function packagePlanDisabled(item: PackageIntegrity) {
  return mutationDisabled.value || guiPlanBlocked.value || item.unsupported.length > 0 || item.issues.length > 0
    || item.generated.some((file) => file.kind === 'optional_derived_bytecode_unverified' && file.present)
    || item.generated.some((file) => file.kind === 'rewritten_record' && (!file.present || item.damaged.includes(file.path)))
}

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
function appendLog(entry: LogEntry) {
  if (visibleLogIds.has(entry.id)) return
  visibleLogIds.add(entry.id)
  logs.value.push(entry)
  if (logs.value.length > 2000) logs.value.splice(0, logs.value.length - 2000).forEach(removed => visibleLogIds.delete(removed.id))
}
function addLog(line: string, source: LogSource = 'unknown') {
  appendLog(createLogEntry(++logSequence, line, path.value.trim(), operation.value?.status === 'running' ? operation.value.id : runtime.value?.run_id ?? null, source))
}
function acceptLogEntry(record: LogRecord) {
  logSessionId.value = record.session_id
  appendLog(fromLogRecord(record))
}
function showLogs(focusError = false) {
  const id = focusError ? [...logs.value].reverse().find(entry => entry.level === 'ERROR' && samePath(entry.root, path.value))?.id ?? logs.value.at(-1)?.id ?? null : null
  logFocus.value = id ? { id, request: ++logFocusRequest } : null
  page.value = 'logs'
}
function samePath(left: string, right: string) { return left.trim().replace(/\\/g, '/').replace(/\/$/, '').toLowerCase() === right.trim().replace(/\\/g, '/').replace(/\/$/, '').toLowerCase() }
function acceptRuntime(value: RuntimeSnapshot) {
  if (disposed || !samePath(value.root, path.value)) return
  if (runtime.value && value.seq <= runtime.value.seq) return
  const acceptedAt = performance.now()
  const previousPhase = runtime.value?.phase
  runtime.value = value
  if (previousPhase !== value.phase) {
    addLog(`[信息] ${runtimeLabels[value.phase]}${value.url ? ` · ${value.url}` : ''}`, 'launcher')
    if (!busy.value) message.value = runtimeLabels[value.phase]
  }
  optimisticPhase.value = null
  void nextTick(() => {
    // 原生验收读取此标记测量事件接受到渲染；不写进用户日志。
    document.documentElement.dataset.runtimeRenderedSeq = String(value.seq)
    document.documentElement.dataset.runtimeRenderMs = (performance.now() - acceptedAt).toFixed(2)
    document.documentElement.dataset.runtimeObservedAt = String(value.observed_at)
    document.documentElement.dataset.runtimeRenderedAt = String(Date.now())
  })
}
async function syncRuntime() {
  if (disposed || runtimeQueryPending) return
  const root = path.value.trim()
  if (!root) return
  runtimeQueryPending = true
  try { const value = await runtimeStatus(root); if (samePath(root, path.value)) acceptRuntime(value) }
  catch { /* 普通浏览器预览没有桌面接口；实际操作错误会明确显示。 */ }
  finally { runtimeQueryPending = false }
}
function acceptReport(value: Report) {
  const rootChanged = report.value?.root !== value.root
  report.value = { ...value, versions: value.versions ?? [], interrupted: value.interrupted ?? [] }
  path.value = value.root
  localStorage.setItem('next-trainer-launcher-root', value.root)
  if (!logs.value.length && value.logs.length) value.logs.forEach(line => addLog(line))
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
  const root = path.value.trim()
  const stillCurrent = () => !disposed && operation.value?.id === current.id && path.value.trim() === root
  try {
    const next = await operationSnapshot(current.id)
    if (!stillCurrent()) return
    // 游标失效时以快照为准；当前会话的事件随后从新游标继续。
    try {
      const events = await operationEvents(current.id, operationCursor)
      if (!stillCurrent()) return
      events.forEach((event) => { addLog(event.message, 'environment'); operationCursor = Math.max(operationCursor, event.seq) })
    } catch (reason) {
      if (!errorText(reason).includes('事件游标已过期')) throw reason
      operationCursor = Math.max(operationCursor, next.event_seq)
      addLog('部分较早事件已过期，已重新读取完整状态。')
    }
    if (!stillCurrent()) return
    operation.value = next
    message.value = `${phaseText[next.phase]} · ${operationStatusText[next.status]}`
    if (next.error) error.value = next.error.message
    if (next.status !== 'running') {
      clearGuiState()
      await refreshHistory()
      if (next.kind !== 'download' && stillCurrent()) {
        const value = await runCommand('inspect', root)
        if (stillCurrent()) acceptReport(value)
      }
      return
    }
  } catch (reason) { if (stillCurrent()) error.value = errorText(reason) }
  if (stillCurrent() && operation.value?.status === 'running') operationTimer = setTimeout(() => { void pollOperation() }, 250)
}
async function prefetch(version: VersionView, install = false) {
  if (busy.value) return
  pending.value = '准备下载'
  error.value = ''
  try {
    operation.value = await (install ? installManagedRelease(path.value.trim(), version.id) : prefetchRelease(path.value.trim(), version.id))
    operationCursor = 0
    message.value = install ? '正在安装主程序' : '正在准备安装文件'
    void pollOperation()
  } catch (reason) { error.value = errorText(reason) }
  finally { pending.value = '' }
}
async function cancelCurrentOperation() {
  const current = operation.value
  if (!current || current.status !== 'running') return
  const root = path.value.trim()
  const stillCurrent = () => !disposed && operation.value?.id === current.id && path.value.trim() === root
  try {
    const receipt = await cancelOperation(current.id)
    if (!stillCurrent()) return
    message.value = receipt === 'commit_in_progress' ? '正在保存操作结果，请等待本次保存完成。' : receipt === 'already_finished' ? '本次操作已经结束，正在刷新状态。' : '已请求取消，正在等待任务结束与必要的恢复校验…'
    const next = await operationSnapshot(current.id)
    if (stillCurrent()) operation.value = next
  } catch (reason) { if (stillCurrent()) error.value = errorText(reason) }
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
    addLog(`[失败] ${error.value}`, 'launcher')
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
  const buttons = [...(event.currentTarget as HTMLElement).querySelectorAll<HTMLElement>('button:not(:disabled), [tabindex="0"]')]
  const first = buttons[0]
  const last = buttons[buttons.length - 1]
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
}
function install(version: VersionView) {
  if (version.managed_recipe) return prefetch(version, true)
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
  return start()
}
function browse() {
  return perform('选择目录', async () => {
    const selected = await chooseDirectory()
    if (selected) acceptReport(await runCommand('inspect', selected))
  })
}
async function start() {
  if (primaryDisabled.value) return
  const epoch = ++serviceEpoch, root = path.value.trim(), runId = `start-${crypto.randomUUID()}`
  requestedRunId.value = runId
  serviceAction.value = 'start'; optimisticPhase.value = 'checking'; error.value = ''; message.value = '正在检查启动条件…'
  try {
    const value = await startTrainer(root, runId)
    if (epoch === serviceEpoch && samePath(root, path.value)) { acceptReport(value); await syncRuntime() }
  } catch (reason) {
    if (epoch === serviceEpoch && samePath(root, path.value)) { error.value = errorText(reason); optimisticPhase.value = 'start_failed'; addLog(`[失败] ${error.value}`, 'launcher'); await syncRuntime() }
  } finally { if (epoch === serviceEpoch) serviceAction.value = '' }
}
async function stop() {
  if (runtimePhase.value === 'stopping' || serviceAction.value === 'stop') return
  const epoch = ++serviceEpoch, root = path.value.trim()
  serviceAction.value = 'stop'; optimisticPhase.value = 'stopping'; error.value = ''; message.value = '正在停止服务并回收进程…'
  try { const value = await stopTrainer(requestedRunId.value ?? runtime.value?.run_id ?? null); if (epoch === serviceEpoch && samePath(root, path.value)) acceptRuntime(value) }
  catch (reason) { if (epoch === serviceEpoch) { error.value = errorText(reason); optimisticPhase.value = 'stop_failed'; addLog(`[失败] ${error.value}`, 'launcher'); await syncRuntime() } }
  finally { if (epoch === serviceEpoch) { serviceAction.value = ''; requestedRunId.value = null } }
}
async function open() {
  try { await openTrainer() } catch (reason) { error.value = errorText(reason); addLog(`[失败] ${error.value}`, 'launcher'); await syncRuntime() }
}
async function openProjectLink(target: 'project' | 'releases' | 'blog' | 'bilibili' | 'modelscope' | 'issues' | 'license') { try { await invoke('open_project_link', { target }) } catch (reason) { notify(errorText(reason)) } }
async function copyAddress() { try { await navigator.clipboard.writeText(serviceUrl.value); notify('已复制服务地址') } catch { notify('复制失败，请在日志中选择地址复制') } }
function notify(value: string) { toast.value = value; setTimeout(() => { if (toast.value === value) toast.value = '' }, 3500) }
watch(error, value => { if (value && page.value !== 'launch') notify(value) })
function openSetting(value: Setting) { setting.value = value; page.value = 'settings'; if (value === 'network' && sameRoot.value && !networkView.value) void readNetworkSettings() }
function loadAppearance() {
  const number = (value: unknown, fallback: number, min: number, max: number) => typeof value === 'number' && Number.isFinite(value) ? Math.min(max, Math.max(min, value)) : fallback
  const defaults = { materialVersion: 1, background: '', mask: 60, blur: 30, reduceMotion: false, logFontSize: 12 }
  try {
    const saved = JSON.parse(localStorage.getItem('next-trainer-launcher-appearance') ?? '{}')
    // 旧主题被统一材质替代；仅更新旧版默认强度，保留用户自定义图片与其他设置。
    return { materialVersion: 1, background: typeof saved.background === 'string' && /^data:image\/(?:png|jpeg|webp);base64,/.test(saved.background) ? saved.background : '', mask: number(saved.materialVersion !== 1 && saved.mask === 28 ? 60 : saved.mask, 60, 0, 80), blur: number(saved.materialVersion !== 1 && saved.blur === 24 ? 30 : saved.blur, 30, 0, 60), reduceMotion: Boolean(saved.reduceMotion), logFontSize: number(saved.logFontSize, 12, 12, 18) }
  } catch { return defaults }
}
watch(appearance, value => {
  try { localStorage.setItem('next-trainer-launcher-appearance', JSON.stringify(value)) }
  catch { notify('外观设置未保存：本地存储空间不足，请换用较小的背景图片。') }
}, { deep: true })
// 白色海报上的品牌文字按局部亮度取深字，保留首页原图，不增加整屏遮罩。
let wallpaperImage: HTMLImageElement | undefined
let wallpaperEpoch = 0
function sampleHomeInk() {
  const image = wallpaperImage
  if (!image?.naturalWidth) return
  const width = innerWidth, height = innerHeight, scale = Math.max(width / image.naturalWidth, height / image.naturalHeight)
  const canvas = document.createElement('canvas'); canvas.width = 128; canvas.height = 72
  const context = canvas.getContext('2d', { willReadFrequently: true })
  if (!context) return
  context.drawImage(image, (width - image.naturalWidth * scale) / 2 * 128 / width, (height - image.naturalHeight * scale) / 2 * 72 / height, image.naturalWidth * scale * 128 / width, image.naturalHeight * scale * 72 / height)
  const needsDarkInk = (selector: string, fallback: { left: number; top: number; width: number; height: number }) => {
    const bounds = document.querySelector<HTMLElement>(selector)?.getBoundingClientRect()
    const rect = bounds?.width ? bounds : fallback
    const x = Math.max(0, Math.min(127, Math.floor(rect.left * 128 / width))), y = Math.max(0, Math.min(71, Math.floor(rect.top * 72 / height)))
    const pixels = context.getImageData(x, y, Math.max(1, Math.min(128 - x, Math.ceil(rect.width * 128 / width))), Math.max(1, Math.min(72 - y, Math.ceil(rect.height * 72 / height)))).data
    const linear = (value: number) => { const channel = value / 255; return channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4 }
    let luminance = 0
    for (let i = 0; i < pixels.length; i += 4) luminance += .2126 * linear(pixels[i]!) + .7152 * linear(pixels[i + 1]!) + .0722 * linear(pixels[i + 2]!)
    return luminance / (pixels.length / 4) > .179
  }
  homeInk.value = { titleDark: needsDarkInk('.titlebar-name', { left: 68, top: 8, width: 180, height: 32 }), headingDark: needsDarkInk('.home-heading>div', { left: 220, top: 80, width: 240, height: 110 }), controlsDark: needsDarkInk('.titlebar-state', { left: width - 240, top: 8, width: 220, height: 32 }) }
}
watch(() => appearance.value.background, source => {
  const epoch = ++wallpaperEpoch, image = new Image()
  image.onload = () => { if (epoch === wallpaperEpoch) { wallpaperImage = image; sampleHomeInk() } }
  image.src = source || '/assets/launcher-wallpaper.png'
}, { immediate: true })
onMounted(() => window.addEventListener('resize', sampleHomeInk))
onBeforeUnmount(() => { wallpaperEpoch += 1; window.removeEventListener('resize', sampleHomeInk) })
watch(page, value => { if (value === 'launch') void nextTick(sampleHomeInk) })
// 原生菜单与窗口也固定采用同一材质色系，不再暴露两套主题。
try { void getCurrentWindow().setTheme('dark').catch(() => undefined) } catch { /* 浏览器预览。 */ }
watch(() => appearance.value.reduceMotion, value => {
  document.documentElement.classList.toggle('reduce-motion', value)
}, { immediate: true })
let navigationAnimation: Animation | undefined
watch([page, setting], async () => {
  navigationAnimation?.cancel()
  await nextTick()
  if (appearance.value.reduceMotion || matchMedia('(prefers-reduced-motion: reduce)').matches) return
  const target = page.value === 'settings'
    ? document.querySelector<HTMLElement>('.settings-content > section:not([style*="display: none"])')
    : document.querySelector<HTMLElement>('.launcher-main > :not([style*="display: none"])')
  navigationAnimation = target?.animate([
    { opacity: 0, transform: 'translateY(12px)' },
    { opacity: 1, transform: 'translateY(0)' },
  ], { duration: 220, easing: 'cubic-bezier(.1,.9,.2,1)' })
}, { flush: 'post' })
onBeforeUnmount(() => navigationAnimation?.cancel())
async function chooseBackground(event: Event) {
  const input = event.target as HTMLInputElement, file = input.files?.[0]
  if (!file) return
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 8 * 1024 * 1024) { notify('请选择 8 MiB 以内的 PNG、JPEG 或 WebP 图片'); input.value = ''; return }
  try {
    const bitmap = await createImageBitmap(file)
    const ratio = Math.min(1, 1920 / bitmap.width, 1080 / bitmap.height)
    const canvas = document.createElement('canvas'); canvas.width = Math.round(bitmap.width * ratio); canvas.height = Math.round(bitmap.height * ratio)
    canvas.getContext('2d')?.drawImage(bitmap, 0, 0, canvas.width, canvas.height); bitmap.close()
    const background = canvas.toDataURL('image/webp', .86)
    // 先确保存储成功，再应用；重启后不会突然丢失背景。
    localStorage.setItem('next-trainer-launcher-appearance', JSON.stringify({ ...appearance.value, background }))
    appearance.value.background = background; notify('已应用本地背景')
  } catch { notify('无法读取或保存这张图片，请选择较小的有效图片。') }
  finally { input.value = '' }
}
async function windowControl(action: 'minimize' | 'maximize' | 'close') {
  try { const window = getCurrentWindow(); if (action === 'minimize') await window.minimize(); else if (action === 'maximize') await window.toggleMaximize(); else await window.close() }
  catch (reason) { notify(errorText(reason)) }
}
async function dragTitlebar(event: MouseEvent) {
  if (event.button !== 0 || (event.target as HTMLElement).closest('button')) return
  try { await getCurrentWindow().startDragging() } catch { /* 浏览器预览不支持原生拖动。 */ }
}

async function diagnoseManagedGui() {
  if (!managedCurrent.value || mutationDisabled.value || !currentVersion.value) return
  clearGuiState()
  const root = path.value.trim()
  const releaseId = currentVersion.value.id
  const epoch = guiEpoch
  await perform('只读诊断 GUI 依赖', async () => {
    const value = await diagnoseGui(root, releaseId)
    if (epoch !== guiEpoch || root !== path.value.trim() || releaseId !== currentVersion.value?.id) return
    guiDiagnosis.value = value
    addLog(`只读诊断完成：${value.integrity.packages.length} 个包，实例代次 ${value.generation}。生成脚本的内容验证范围见诊断说明。`)
  })
}
async function inspectBasePythonRepair() {
  if (mutationDisabled.value) return
  const root = path.value.trim()
  const epoch = guiEpoch
  basePythonPreview.value = null
  await perform('只读检查基础 Python 与引用环境', async () => {
    const preview = await previewBasePythonRepair(root)
    if (epoch !== guiEpoch || root !== path.value.trim()) return
    basePythonPreview.value = preview
  })
}
async function inspectGuiRegistration() {
  const version = registrationRelease.value
  if (!version || mutationDisabled.value) return
  const root = path.value.trim()
  const epoch = guiEpoch
  const selectedInstance = registrationInstanceId.value || null
  registrationPreview.value = null
  await perform('只读检查安装登记', async () => {
    const value = await previewGuiRegistration(root, version.id, selectedInstance)
    if (epoch !== guiEpoch || root !== path.value.trim() || version.id !== registrationRelease.value?.id) return
    registrationPreview.value = value
  })
}
function changeRegistrationRelease() {
  guiEpoch += 1
  registrationPreview.value = null
  registrationInstanceId.value = ''
  if (confirmation.value?.scope === 'gui') dismissConfirmation()
}
function confirmGuiRegistration(recovery = false) {
  const preview = registrationPreview.value
  const version = registrationRelease.value
  if (!preview || !version || mutationDisabled.value || (recovery ? preview.status !== 'pending' : preview.status !== 'ready' || !preview.plan || !preview.plan_sha256)) return
  const root = path.value.trim()
  const epoch = guiEpoch
  const candidate = preview.plan?.candidate
  return ask({
    scope: 'gui', title: recovery ? '继续恢复安装登记' : '恢复安装登记',
    detail: '将离线核验固定文件、解释器和全部依赖，并在独立临时资料目录验证真实入口，再补齐缺失的安装记录。已有环境与用户资料须保持不变；登记恢复完成后，仍需选择版本并正常启动才能建立本次启动健康记录。',
    paths: preview.plan ? [`版本：${version.id}`, `环境：${preview.plan.proof.environment}`, `实例：${candidate?.id} · 路径格式 ${candidate?.storage_version} · 已知代次 ${candidate?.generation}`, `可信文件：${preview.plan.proof.files.toLocaleString()} 个`, `固定文件索引：${preview.plan.proof.trusted_index_sha256}`] : [`事务：${preview.transaction}`],
    action: recovery ? '继续核验与补齐登记' : '确认核验并恢复登记',
    execute: async () => {
      if (epoch !== guiEpoch || root !== path.value.trim() || version.id !== registrationRelease.value?.id) { error.value = '目录或版本已改变，请重新检查安装登记。'; return }
      await startGuiOperation('正在验证并恢复安装登记', () => recovery ? recoverGuiRegistration(root, version.id)
        : restoreGuiRegistration(root, version.id, candidate!.id, preview.plan_sha256!))
    },
  })
}
async function inspectLifecycle(action: 'rebuild' | 'rollback') {
  const version = registrationRelease.value
  if (!version || mutationDisabled.value) return
  const root = path.value.trim(), epoch = guiEpoch
  lifecyclePreview.value = null
  await perform('检查实例重建与回退计划', async () => {
    const history = await guiLifecycleHistory(root, version.id)
    const value = await previewGuiLifecycle(root, version.id, action, lifecycleTransaction.value || null)
    if (epoch !== guiEpoch || root !== path.value.trim()) return
    lifecycleHistory.value = history
    lifecycleAction.value = action
    lifecyclePreview.value = value
  })
}
async function inspectLifecycleHistory() {
  const version = registrationRelease.value
  if (!version || mutationDisabled.value) return
  const root = path.value.trim(), epoch = guiEpoch
  await perform('读取实例操作记录', async () => {
    const value = await guiLifecycleHistory(root, version.id)
    if (epoch === guiEpoch && root === path.value.trim()) lifecycleHistory.value = value
  })
}
function confirmLifecycle(action: GuiLifecycleAction, transaction: string | null = null, instance: string | null = null) {
  const version = registrationRelease.value, preview = lifecyclePreview.value
  if (!version || mutationDisabled.value) return
  if ((action === 'rebuild' || action === 'rollback') && (preview?.status !== 'ready' || !preview.plan_sha256)) return
  const root = path.value.trim(), epoch = guiEpoch
  const title = action === 'rebuild' ? '在新路径重建环境' : action === 'rollback' ? '回退到同版本旧实例' : '恢复实例事务'
  return ask({ scope: 'gui', title,
    detail: action === 'rebuild'
      ? '在新的固定路径创建环境，原实例和资料保留。只有固定依赖及独立入口验证通过后才切换绑定；未完成的候选保持不可启动。'
      : '重新验证目标实例和当前绑定，恢复时保留原事务、资料与非目标文件。恢复完成并不代表训练或模型已验证。',
    paths: [`版本：${version.id}`, `安装目录：${root}`, ...(transaction ? [`操作记录：${transaction}`] : []), ...(instance ? [`实例：${instance}`] : [])],
    action: action === 'rebuild' ? '确认创建新实例' : action === 'rollback' ? '确认验证并回退' : '确认恢复事务',
    execute: async () => {
      if (epoch !== guiEpoch || root !== path.value.trim() || version.id !== registrationRelease.value?.id) { error.value = '目录或版本已变化，请重新检查。'; return }
      await startGuiOperation(title, () => applyGuiLifecycle(root, version.id, action, preview?.plan_sha256 ?? null, transaction, instance))
      lifecyclePreview.value = null
      lifecycleHistory.value = null
    },
  })
}
function confirmBasePythonRepair(recovery = false) {
  const preview = basePythonPreview.value
  const version = currentVersion.value ?? defaultRelease.value
  if (!preview || !version || mutationDisabled.value || (recovery ? !preview.recovery_available : !preview.repair_available)) return
  const root = path.value.trim()
  const epoch = guiEpoch
  return ask({
    scope: 'gui', title: recovery ? '继续基础 Python 组件恢复' : '恢复基础 Python 组件',
    detail: `将恢复 ${preview.target} 的完整固定组件，共 ${preview.expected_files.length.toLocaleString()} 个文件。${preview.references.length} 个引用环境会统一暂停使用，逐个验证通过后再保存新代次；环境安装文件、源码与用户资料须保持不变。本来待恢复的实例不会因此变成可用。`,
    paths: [...preview.references.map((reference) => `引用：${reference.release_id} / ${reference.instance_id} · 代次 ${reference.generation} · ${reference.environment}${reference.initial_dirty ? ' · 原本待恢复' : ''}`), ...preview.expected_files],
    action: recovery ? '继续恢复与逐环境校验' : '确认恢复完整组件',
    execute: async () => {
      if (epoch !== guiEpoch || root !== path.value.trim()) { error.value = '目录或版本已改变，请重新检查基础 Python。'; return }
      await startGuiOperation('正在恢复基础 Python 与引用环境', () => recovery ? recoverBasePython(root, version.id) : repairBasePython(root, version.id, preview.plan_sha256))
    },
  })
}
async function previewPackage(item: PackageIntegrity) {
  if (!currentVersion.value || !guiDiagnosis.value || packagePlanDisabled(item)) return
  guiPreview.value = null
  const root = path.value.trim()
  const releaseId = currentVersion.value.id
  const epoch = guiEpoch
  await perform(`生成 ${item.name} 修复清单`, async () => {
    const value = await planGuiRepair(root, releaseId, item.name)
    if (epoch !== guiEpoch || root !== path.value.trim() || releaseId !== currentVersion.value?.id) return
    guiPreview.value = value
    await nextTick()
    document.getElementById('gui-repair-preview')?.scrollIntoView({ block: 'nearest' })
  })
}
function confirmGuiRepair() {
  const preview = guiPreview.value
  const version = currentVersion.value
  if (!preview || !version || mutationDisabled.value || guiPlanBlocked.value) return
  const root = path.value.trim()
  const epoch = guiEpoch
  return ask({
    scope: 'gui', title: `确认修复 ${preview.package}`,
    detail: `将按以下 ${preview.paths.length.toLocaleString()} 个文件路径修复 ${preview.package} ${preview.version}。仅离线重装此包，先保存独立快照，再验证完整依赖与关键导入。快照恢复后若仍不通过验证，实例会保持待恢复状态。安装器生成脚本只检查路径与存在性。`,
    paths: preview.paths, action: '确认修复此包',
    execute: async () => {
      if (epoch !== guiEpoch || root !== path.value.trim() || version.id !== currentVersion.value?.id) { error.value = '目录或版本已改变，请重新诊断生成清单。'; return }
      await startGuiOperation('正在修复指定包', () => repairGuiPackage(root, version.id, preview.package, preview.plan_sha256))
    },
  })
}
function confirmGuiRecovery() {
  const version = currentVersion.value
  const diagnosis = guiDiagnosis.value
  if (!version || !diagnosis || mutationDisabled.value || !guiRecoveryNeeded.value) return
  const root = path.value.trim()
  const epoch = guiEpoch
  return ask({
    scope: 'gui', title: '恢复未完成的单包修复',
    detail: `将读取实例 ${diagnosis.instance_id} 的持久修复记录，恢复独立快照或完成已验证代次的登记，并重新检查依赖与关键导入。原快照已损坏时会继续保留待恢复状态，恢复操作不保证环境通过验证。`,
    action: '开始恢复与校验',
    execute: async () => {
      if (epoch !== guiEpoch || root !== path.value.trim() || version.id !== currentVersion.value?.id) { error.value = '目录或版本已改变，请重新诊断。'; return }
      await startGuiOperation('正在恢复未完成修复', () => recoverGuiRepair(root, version.id))
    },
  })
}
async function inspectSourceRepair(version: VersionView) {
  if (mutationDisabled.value) return
  const root = path.value.trim()
  await perform('查看源码修复清单', async () => {
    const preview = await previewSourceRepair(root, version.id)
    if (root !== path.value.trim()) return
    await ask({
      scope: 'gui', title: '确认修复固定版本源码',
      detail: `将替换 ${preview.replacement_root} 中的 ${preview.expected_source_files.length} 个固定源码和前端文件，原目录移至备份。环境实例和用户资料须保持不变。${preview.source_integrity_error ? '当前源码检查未通过。' : '当前源码完整，执行时将再次检查。'}`,
      paths: [...preview.expected_source_files, ...preview.generated_files],
      action: '确认修复源码',
      execute: async () => {
        if (root !== path.value.trim()) { error.value = '目录已改变，请重新查看清单。'; return }
        await startGuiOperation('正在修复固定源码', () => repairManagedSource(root, version.id))
      },
    })
  })
}
async function startGuiOperation(label: string, action: () => Promise<OperationSnapshot>) {
  if (busy.value) return
  pending.value = label
  error.value = ''
  try {
    operation.value = await action()
    operationCursor = 0
    clearGuiState()
    message.value = label
    void pollOperation()
  } catch (reason) {
    error.value = errorText(reason)
    clearGuiState()
    message.value = '操作未能开始，请重新诊断后重试。'
  } finally { pending.value = '' }
}
onMounted(async () => {
  try { unlisten = await listenToLogEntries(acceptLogEntry); runtimeUnlisten = await listenToRuntime(acceptRuntime) }
  catch { addLog('桌面事件接口尚未连接；请通过桌面启动器打开此页面。') }
  await syncRuntime()
  runtimeTimer = setInterval(() => { void syncRuntime() }, 1500)
  void getVersion().then(value => { appVersion.value = value }).catch(() => undefined)
  await command('inspect', '检查安装状态')
  await syncRuntime()
  try { await refreshHistory() } catch (reason) { error.value = errorText(reason) }
})
onBeforeUnmount(() => { disposed = true; if (operationTimer) clearTimeout(operationTimer); if (runtimeTimer) clearInterval(runtimeTimer); unlisten?.(); runtimeUnlisten?.() })
</script>

<template>
  <div class="app-shell" :class="{ 'home-view': page === 'launch', 'reduce-motion': appearance.reduceMotion, 'home-title-dark': homeInk.titleDark, 'home-heading-dark': homeInk.headingDark, 'home-controls-dark': homeInk.controlsDark }" data-material="acrylic" :data-page="page" :data-runtime-phase="runtimePhase" :data-runtime-run-id="runtime?.run_id ?? ''" :data-runtime-seq="runtime?.seq ?? 0" :style="{ '--wallpaper': 'url(' + (appearance.background || '/assets/launcher-wallpaper.png') + ')', '--content-blur': `${appearance.blur}px`, '--mask-opacity': String(appearance.mask / 100) }">
    <svg class="material-definitions" aria-hidden="true" focusable="false"><defs><filter id="fluent-acrylic" x="0" y="0" width="100%" height="100%" color-interpolation-filters="sRGB"><feGaussianBlur in="SourceGraphic" :stdDeviation="appearance.blur" edgeMode="duplicate" result="blur" /><feFlood flood-color="#202020" :flood-opacity="acrylicOpacity.luminosity" result="luminosity" /><feBlend in="luminosity" in2="blur" mode="luminosity" result="lit" /><feFlood flood-color="#1c1c1c" :flood-opacity="acrylicOpacity.tint" result="tint" /><feBlend in="tint" in2="lit" mode="color" /></filter></defs></svg>
    <Transition name="wallpaper" appear><div :key="appearance.background" class="wallpaper" :style="{ backgroundImage: 'url(' + (appearance.background || '/assets/launcher-wallpaper.png') + ')' }" aria-hidden="true"></div></Transition><div class="wallpaper-shade" aria-hidden="true"></div><div class="acrylic-layer" aria-hidden="true"></div>
    <aside id="launcher-sidebar" class="sidebar" :class="{ expanded: sidebarExpanded }" aria-label="启动器导航" @keydown.esc="sidebarExpanded && (sidebarExpanded = false, sidebarToggle?.focus())">
      <button ref="sidebarToggle" class="sidebar-toggle" :aria-label="sidebarExpanded ? '收起侧边栏' : '展开侧边栏'" :title="sidebarExpanded ? '收起侧边栏' : '展开侧边栏'" :aria-expanded="sidebarExpanded" aria-controls="launcher-sidebar" @click="sidebarExpanded = !sidebarExpanded"><Icon name="menu" /><span class="nav-label" aria-hidden="true">收起导航</span></button>
      <nav aria-label="主导航"><button v-for="item in ([{ id: 'launch', icon: 'home', label: '首页' }, { id: 'versions', icon: 'versions', label: '版本管理' }, { id: 'environment', icon: 'environment', label: '环境管理' }, { id: 'logs', icon: 'logs', label: '日志' }] as const)" :key="item.id" :class="{ selected: page === item.id }" :aria-current="page === item.id ? 'page' : undefined" :aria-label="item.label" :title="item.label" @click="page = item.id"><Icon :name="item.icon" /><span class="nav-label" aria-hidden="true">{{ item.label }}</span></button></nav>
      <div class="sidebar-foot"><button :class="{ selected: page === 'settings' }" :aria-current="page === 'settings' ? 'page' : undefined" aria-label="启动器设置" title="启动器设置" @click="page = 'settings'"><Icon name="settings" /><span class="nav-label" aria-hidden="true">设置</span></button></div>
    </aside>
    <header class="titlebar" @mousedown="dragTitlebar" @dblclick="windowControl('maximize')"><span class="titlebar-name">{{ titlebarVersion }}</span><span class="titlebar-state" :class="{ good: stateGood, working: transitioning }" role="status" aria-live="polite"><i></i>{{ stateText }}</span><div class="window-controls"><button aria-label="最小化" title="最小化" @dblclick.stop @click="windowControl('minimize')"><Icon name="minimize" /></button><button aria-label="最大化或还原" title="最大化 / 还原" @dblclick.stop @click="windowControl('maximize')"><Icon name="maximize" /></button><button class="window-close" aria-label="关闭启动器" title="关闭" @dblclick.stop @click="windowControl('close')"><Icon name="close" /></button></div></header>
    <main class="launcher-main">
      <section v-show="page === 'launch'" class="home-page" aria-label="首页">
        <div class="home-heading"><img src="/assets/home-logo.webp" alt="Next Trainer 项目标志" /><div><h1>Next<span>Trainer</span></h1><p>让灵感，成为你的模型。</p></div></div>
        <article class="release-float" aria-label="项目信息">
          <button class="release-art" data-link-target="releases" aria-label="打开 Next Trainer 项目发布页" @click="openProjectLink('releases')"><img class="release-cover" src="/assets/next-trainer-cover.png" alt="Next Trainer 项目封面" /></button>
          <div class="release-body">
            <div class="release-tabs" role="tablist" aria-label="项目信息栏目">
              <button id="project-releases-tab" role="tab" :aria-selected="informationTab === 'releases'" aria-controls="project-releases" :class="{ selected: informationTab === 'releases' }" @click="informationTab = 'releases'">项目发布</button>
              <button id="friend-links-tab" role="tab" :aria-selected="informationTab === 'friends'" aria-controls="friend-links" :class="{ selected: informationTab === 'friends' }" @click="informationTab = 'friends'">友情链接</button>
            </div>
            <div v-show="informationTab === 'releases'" id="project-releases" class="release-copy release-detail" role="tabpanel" aria-labelledby="project-releases-tab"><p>版本更新、功能说明与项目发布记录。</p><button class="text-row" data-link-target="releases" @click="openProjectLink('releases')"><span>前往 GitHub Releases</span><Icon name="external" /></button></div>
            <div v-show="informationTab === 'friends'" id="friend-links" class="friend-links" role="tabpanel" aria-labelledby="friend-links-tab">
              <button data-link-target="blog" @click="openProjectLink('blog')"><span>Displace 博客</span><Icon name="external" /></button>
              <button data-link-target="bilibili" @click="openProjectLink('bilibili')"><span>Bilibili 个人空间</span><Icon name="external" /></button>
              <button data-link-target="modelscope" @click="openProjectLink('modelscope')"><span>ModelScope 魔搭</span><Icon name="external" /></button>
            </div>
          </div>
        </article>
        <div v-if="error || runtime?.error" class="home-error" role="alert"><Icon name="info" /><span>{{ error || runtime?.error }}</span><button @click="showLogs(true)">查看日志<Icon name="arrow" /></button></div>
        <div class="home-bottom"><div v-if="operation?.status === 'running'" class="home-operation-actions"><span>{{ phaseText[operation.phase] }}</span><button @click="showLogs()">查看日志</button><button :disabled="operation.cancel_requested" @click="cancelCurrentOperation">{{ operation.cancel_requested ? '正在收尾' : '取消操作' }}</button></div><div v-if="healthy && serviceUrl" class="service-caption"><span>{{ serviceUrl }}</span><button class="icon-button" aria-label="复制服务地址" title="复制服务地址" @click="copyAddress"><Icon name="copy" /></button></div><div class="launch-row"><button v-if="['checking', 'starting', 'ready', 'degraded', 'stop_failed'].includes(runtimePhase)" class="secondary-pill" :disabled="serviceAction === 'stop'" @click="stop"><Icon :name="transitioning ? 'close' : 'stop'" />{{ ['checking', 'starting'].includes(runtimePhase) ? '取消启动' : '停止服务' }}</button><button v-else class="secondary-pill" @click="openSetting('profiles')"><Icon name="folder" />安装位置</button><button v-if="healthy" class="launch-button" data-action="open-trainer" @click="open"><Icon name="external" />打开训练器</button><button v-else class="launch-button" data-action="start-trainer" :disabled="primaryDisabled" @click="primary"><Icon :name="transitioning || pending ? 'refresh' : 'home'" :class="{ spin: transitioning || pending }" />{{ transitioning ? runtimeLabels[runtimePhase] : pending || primaryLabel }}</button></div></div>
      </section>
      <section v-show="page === 'versions'" class="content-page" aria-label="版本管理"><header class="page-title"><h1>版本管理</h1><p>在本机版本之间切换，资料始终保留。</p></header><div class="section-toolbar"><span class="context-label">{{ versions.filter(version => version.installed).length }} 个已安装版本</span><button :disabled="busy" @click="command('inspect', '检查安装状态')"><Icon name="refresh" />刷新本机版本</button></div><div v-if="currentVersion" class="version-installed"><img src="/assets/home-logo.webp" alt="Next Trainer" /><div><h2>Next Trainer <span>{{ currentVersion.version }}</span></h2><div class="inline-tags"><span class="tag active-tag">当前使用</span><span class="tag">{{ channelName(currentVersion.channel) }}</span><code>{{ currentVersion.commit.slice(0, 8) }}</code></div><p>{{ ready ? '源码、主程序环境与网页资源均已就绪' : '请根据检查结果安装或修复' }}</p></div><button @click="page = 'environment'">检查与修复<Icon name="arrow" /></button></div>

          <div class="section-caption"><h2>内置发布清单</h2><span>固定制品，尚未查询远端更新</span></div>
          <section class="rollback-panel"><div><strong>上一已健康版本</strong><p v-if="rollbackVersion"><span>{{ channelName(rollbackVersion.channel) }} · {{ rollbackVersion.version }}</span><code>{{ rollbackVersion.commit.slice(0, 8) }}</code></p><p v-else>尚无可回退记录。版本成功启动并通过健康检查后会记录。</p></div><button :disabled="mutationDisabled || !rollbackAvailable" @click="rollback">回退到此版本</button></section>
          <p v-if="rollbackVersion && !rollbackAvailable" class="inline-note">回退目标尚未安装完整或存在检查问题，请先修复对应版本。</p>
          <section v-for="group in channels" :key="group.channel" class="channel-section" :aria-label="channelName(group.channel)"><h3>{{ channelName(group.channel) }}<span>{{ group.channel === 'dev' ? '包含开发中的改动' : group.channel === 'main' ? '稳定发布线' : '内置版本' }}</span></h3><p v-if="!group.versions.length" class="empty-channel">内置清单尚未提供此发布线的版本。</p><article v-for="version in group.versions" :key="version.id" class="version-card" :aria-label="`${version.channel} ${version.version} ${version.commit.slice(0, 8)}`"><div class="version-top"><div><strong>{{ version.version }}</strong><span v-if="version.current || version.id === report?.current_release" class="current-tag">当前使用</span><span v-else-if="version.id === report?.previous_known_good" class="healthy-tag">回退保留</span><span v-else-if="version.known_good" class="healthy-tag">曾健康启动</span></div><span class="release-state" :class="{ good: version.installed && version.source_ok && version.environment_ok }">{{ releaseState(version) }}</span></div><dl class="version-details"><div><dt>提交</dt><dd><code>{{ version.commit }}</code></dd></div><div><dt>下载</dt><dd><code>{{ formatBytes(version.download_bytes) }}</code><span class="detail-note">源码制品</span></dd></div><div><dt>磁盘</dt><dd><code>{{ formatBytes(version.source_bytes) }}</code><span class="detail-note">{{ version.installed ? '源码展开；运行环境另计' : '预计源码展开；运行环境另计' }}</span></dd></div><div v-if="version.installed"><dt>检查</dt><dd><span :class="{ 'check-warning': !version.source_ok }">源码{{ version.source_ok ? '完整' : '需修复' }}</span><span class="detail-separator">/</span><span :class="{ 'check-warning': !version.environment_ok }">环境{{ version.environment_ok ? '通过' : '需修复' }}</span></dd></div></dl><div class="version-actions"><button v-if="version.managed_recipe && version.installed" :disabled="mutationDisabled" @click="inspectSourceRepair(version)">源码修复清单</button><button :disabled="mutationDisabled" @click="install(version)">{{ version.installed ? '检查并补全安装' : '下载安装' }}</button><button :disabled="mutationDisabled || !version.installed || !version.source_ok || !version.environment_ok || version.current || version.id === report?.current_release" @click="select(version)">切换到此版本</button><button class="delete-button" :disabled="mutationDisabled || !version.installed || protectedRelease(version)" :title="protectedRelease(version) ? '当前版本及上一已健康版本需保留' : '删除受管版本目录'" @click="remove(version)">删除</button></div></article></section>
          <p class="scope-note">已安装表示版本目录存在，不代表可以运行。切换依据每个版本的实际检查；当前版本和上一已健康版本受删除保护。main / dev 使用发布线与提交区分，即使版本号相同也分别管理。</p>
          <section class="environment-actions" aria-label="准备版本安装文件"><button v-for="version in versions" :key="version.id" :disabled="mutationDisabled" @click="prefetch(version)">准备 {{ channelName(version.channel) }} 安装文件</button></section>

      </section>
      <section v-show="page === 'environment'" class="content-page environment-page" aria-label="环境管理"><header class="page-title"><h1>环境管理</h1><p>每个训练引擎独立安装，按需检查与修复。</p></header><div class="section-toolbar"><div class="context-label">Next Trainer <b>{{ currentVersion?.version ?? '尚未选择版本' }}</b><span v-if="currentVersion" class="tag">当前版本</span></div><button :disabled="busy || transitioning" @click="command('inspect', '检查安装状态')"><Icon name="refresh" />检查环境</button></div><article class="main-environment"><div class="main-env-icon"><Icon name="environment" /></div><div class="main-env-copy"><h2>主程序环境 <span class="engine-state" :class="{ good: ready }"><i></i>{{ !sameRoot || !report ? '待检查' : ready ? '已就绪' : '需处理' }}</span></h2><p>基础 Python · 主程序依赖 · 网页资源</p></div><div class="main-env-actions"><button class="quiet-button" :disabled="mutationDisabled || !managedCurrent" @click="advanced = true; diagnoseManagedGui()">主程序修复</button><button @click="advanced = !advanced">{{ advanced ? '收起高级恢复' : '高级恢复' }}<Icon name="arrow" /></button></div></article>
        <EnginePanel v-if="sameRoot && registrationRelease" :root="path.trim()" :release-id="registrationRelease.id" :disabled="mutationDisabled" @operate="startGuiOperation" /><p v-else class="empty-note">检查安装目录并选择训练器版本后，可分别管理四个训练引擎。</p>
        <div v-show="advanced" class="advanced-recovery"><h2>主程序检查与高级恢复</h2><p class="hint">完整性检查与恢复按实际文件验证。执行修改前请先停止训练器。</p><div v-if="report?.checks.length && sameRoot" class="checks" role="list" aria-label="环境检查明细"><div v-for="(check, index) in report.checks" :key="`${index}-${check.name}`" class="check-row" role="listitem"><span class="check-badge" :class="{ ok: check.ok }">{{ check.ok ? '通过' : '待处理' }}</span><div><strong>{{ check.name }}</strong><p>{{ check.detail }}</p></div></div></div>
      <section v-if="sameRoot && registrationVersions.length" class="gui-diagnostics" aria-labelledby="registration-title">
            <div class="section-caption"><h2 id="registration-title">恢复安装登记</h2><button :disabled="mutationDisabled" @click="inspectGuiRegistration">只读检查登记</button></div>
            <p class="hint">源码和环境仍在、安装记录丢失时，可离线验证并补齐登记。检查不会执行解释器；确认后会使用独立临时资料验证真实入口。</p>
            <label>需要恢复的版本<AcrylicSelect :model-value="registrationRelease?.id" :disabled="mutationDisabled" :options="registrationVersions.map(version => ({ value: version.id, label: `${channelName(version.channel)} · ${version.version} · ${version.commit.slice(0, 8)}` }))" @change="registrationReleaseId = $event.target.value; changeRegistrationRelease()" /></label>
            <template v-if="registrationPreview">
              <p v-if="registrationPreview.reason" class="gui-issue" role="alert">{{ registrationPreview.reason }}</p>
              <p v-if="registrationPreview.status === 'pending'" class="hint">存在待恢复登记事务：{{ registrationPreview.transaction }}</p>
              <label v-if="registrationPreview.candidates?.length">指定已有实例<AcrylicSelect v-model="registrationInstanceId" :disabled="mutationDisabled" :options="[{ value: '', label: '按已有绑定检查' }, ...registrationPreview.candidates.map(candidate => ({ value: candidate.id, label: `${candidate.id} · 路径格式 ${candidate.storage_version} · 代次 ${candidate.generation} · ${candidate.status === 'clean' ? '已有验证记录' : candidate.status === 'missing_state' ? '实例记录缺失' : '需要先恢复原事务'}` }))]" @change="guiEpoch += 1; registrationPreview = null" /><span class="hint">选择后请重新执行只读检查，确认环境与影响。</span></label>
              <p v-if="registrationPreview.plan">环境：<code>{{ registrationPreview.plan.proof.environment }}</code> · {{ registrationPreview.plan.proof.files.toLocaleString() }} 个可信文件</p>
              <button v-if="registrationPreview.status === 'ready'" :disabled="mutationDisabled" @click="confirmGuiRegistration()">审查并恢复登记</button>
              <button v-if="registrationPreview.status === 'pending'" :disabled="mutationDisabled" @click="confirmGuiRegistration(true)">继续未完成登记恢复</button>
            </template>
          </section>
          <section v-if="sameRoot && registrationRelease" class="gui-diagnostics" aria-labelledby="lifecycle-title">
            <div class="section-caption"><h2 id="lifecycle-title">独立环境重建与回退</h2><button :disabled="mutationDisabled" @click="inspectLifecycleHistory">读取实例记录</button></div>
            <p class="hint">环境无法精准修复时，可在新路径重建。旧实例保留，切换前会验证依赖和独立入口；同版本回退使用已保存的重建记录。</p>
            <p>目标版本：{{ registrationRelease.version }} · {{ registrationRelease.commit.slice(0, 8) }}</p>
            <button :disabled="mutationDisabled" @click="inspectLifecycle('rebuild')">预览新实例重建</button>
            <template v-if="lifecycleHistory">
              <label>可回退的重建记录<AcrylicSelect v-model="lifecycleTransaction" :disabled="mutationDisabled" :options="[{ value: '', label: '请选择记录' }, ...lifecycleHistory.records.filter(item => item.rollback_available).map(record => ({ value: record.transaction, label: `${record.transaction} · ${record.candidate_id}` }))]" @change="lifecyclePreview = null" /></label>
              <button :disabled="mutationDisabled || !lifecycleTransaction" @click="inspectLifecycle('rollback')">预览同版本实例回退</button>
              <div v-for="pending in lifecycleHistory.pending_transactions" :key="pending.transaction" class="gui-recovery"><p>未完成实例事务：{{ pending.transaction }} · {{ pending.status }}</p><button :disabled="mutationDisabled" @click="confirmLifecycle(pending.kind === 'binding_switch' ? 'recover_rollback' : 'recover_rebuild', pending.transaction)">复验并恢复此事务</button></div>
              <div v-for="instance in lifecycleHistory.preserved_pending" :key="instance.instance_id" class="gui-recovery"><p>已保留的旧事务实例：{{ instance.instance_id }}</p><button :disabled="mutationDisabled" @click="confirmLifecycle('recover_preserved', null, instance.instance_id)">恢复旧实例事务</button></div>
              <button v-if="lifecycleHistory.status === 'rollback_pending'" :disabled="mutationDisabled" @click="confirmLifecycle('recover_rollback')">继续未完成的实例回退</button>
            </template>
            <template v-if="lifecyclePreview">
              <p v-if="lifecyclePreview.reason" class="gui-issue" role="alert">{{ lifecyclePreview.reason }}</p>
              <p v-if="lifecyclePreview.plan" class="hint">旧实例：{{ lifecyclePreview.plan.old_binding?.instance_id ?? '尚无绑定' }} · 预计下载 {{ formatFileSize(lifecyclePreview.plan.estimated_network_bytes ?? 0) }}</p>
              <button v-if="lifecyclePreview.status === 'ready'" :disabled="mutationDisabled" @click="confirmLifecycle(lifecycleAction, lifecycleAction === 'rollback' ? lifecycleTransaction : null)">审查并{{ lifecycleAction === 'rebuild' ? '创建新实例' : '回退旧实例' }}</button>
            </template>
          </section>
          <section v-if="sameRoot" class="gui-diagnostics" aria-labelledby="base-python-title">
            <div class="section-caption"><h2 id="base-python-title">基础 Python 组件</h2><button :disabled="mutationDisabled" @click="inspectBasePythonRepair">检查组件与引用环境</button></div>
            <p class="hint">检查只读取文件，Python 缺失或损坏时仍可查看。恢复会替换完整基础组件，并验证所有受管引用环境。</p>
            <template v-if="basePythonPreview">
              <p v-if="basePythonPreview.integrity_error" class="gui-issue" role="alert">{{ basePythonPreview.integrity_error }}</p>
              <p v-else class="hint">基础组件固定文件完整。</p>
              <p>{{ basePythonPreview.references.length }} 个引用环境 · {{ basePythonPreview.expected_files.length.toLocaleString() }} 个固定组件文件</p>
              <ul v-if="basePythonPreview.references.length"><li v-for="reference in basePythonPreview.references" :key="`${reference.release_id}:${reference.instance_id}`"><code>{{ reference.release_id }} / {{ reference.instance_id }}</code> · 代次 {{ reference.generation }} · {{ reference.initial_dirty ? '原本待恢复' : '需逐环境复验' }}<p class="hint">{{ reference.environment }}</p></li></ul>
              <p v-for="(blocker, index) in basePythonPreview.blockers" :key="index" class="gui-issue">{{ blocker }}</p>
              <p v-if="basePythonPreview.recovery_error" class="gui-issue">{{ basePythonPreview.recovery_error }}</p>
              <p v-if="basePythonPreview.pending_transaction" class="hint">存在未完成的基础组件事务：{{ basePythonPreview.pending_transaction }}</p>
              <details class="gui-file-details"><summary>完整组件文件清单（{{ basePythonPreview.expected_files.length.toLocaleString() }}）</summary><pre tabindex="0" aria-label="基础 Python 组件完整文件清单">{{ basePythonPreview.expected_files.join('\n') }}</pre></details>
              <button v-if="basePythonPreview.repair_available" :disabled="mutationDisabled" @click="confirmBasePythonRepair()">审查并恢复基础组件</button>
              <button v-if="basePythonPreview.recovery_available" :disabled="mutationDisabled" @click="confirmBasePythonRepair(true)">继续未完成组件恢复</button>
            </template>
          </section>
          <section v-if="managedCurrent" class="gui-diagnostics" aria-labelledby="gui-diagnostics-title">
            <div class="section-caption"><h2 id="gui-diagnostics-title">固定 GUI 依赖诊断与单包修复</h2><button :disabled="mutationDisabled" @click="diagnoseManagedGui">{{ pending === '只读诊断 GUI 依赖' ? '正在诊断…' : '只读诊断依赖' }}</button></div>
            <p class="hint">诊断依据固定 wheel 的真实文件摘要。选择单个包后，先审查文件清单，再确认离线修复。请先停止运行中的训练器。</p>
            <template v-if="guiDiagnosis">
              <dl class="gui-instance"><div><dt>实例</dt><dd><code>{{ guiDiagnosis.instance_id }}</code></dd></div><div><dt>实例代次 / 登记代次</dt><dd>{{ guiDiagnosis.generation }} / {{ guiDiagnosis.binding_generation }}</dd></div><div><dt>状态</dt><dd>{{ guiDiagnosis.dirty ? '待恢复，禁止启动' : guiDiagnosis.recovery_pending ? '存在待收尾修复记录' : guiDiagnosis.generation !== guiDiagnosis.binding_generation ? '登记代次不一致' : '可继续诊断' }}</dd></div></dl>
              <p v-if="guiDiagnosis.source_error" class="gui-issue" role="alert"><strong>源码检查未通过</strong>{{ guiDiagnosis.source_error }}</p>
              <p v-if="guiDiagnosis.installed_metadata_error" class="gui-issue" role="alert"><strong>安装元数据检查未通过</strong>{{ guiDiagnosis.installed_metadata_error }}</p>
              <div v-if="guiRecoveryNeeded" class="gui-recovery"><p>存在未完成的修复或实例代次不一致。恢复会读取持久记录并重新验证；原快照已损坏时会保留待恢复状态。</p><button :disabled="mutationDisabled" @click="confirmGuiRecovery">恢复未完成修复</button></div>
              <div class="gui-package-filter"><span>{{ guiDiagnosis.integrity.packages.length }} 个固定包 · {{ affectedPackages.length }} 个待处理</span><label><input v-model="showAllPackages" type="checkbox" />显示全部包</label></div>
              <p v-if="!visiblePackages.length" class="scope-note">固定包原文件和记录集合未发现缺坏。生成入口脚本只检查路径与存在性；解释器归属、pip check 与关键导入会在安装或修复验证时执行。</p>
              <article v-for="item in visiblePackages" :key="item.name" class="gui-package" :aria-label="`${item.name} ${packageStatus(item)}`">
                <div class="gui-package-heading"><div><strong>{{ item.name }}</strong><code>{{ item.version }}</code><span>{{ packageStatus(item) }}</span></div><button :disabled="packagePlanDisabled(item)" @click="previewPackage(item)">查看修复清单</button></div>
                <p v-if="item.missing.length || item.damaged.length" class="hint">缺失 {{ item.missing.length }} 项 · 内容或记录异常 {{ item.damaged.length }} 项</p>
                <details v-if="item.missing.length" class="gui-file-details"><summary>缺失文件（{{ item.missing.length }}）</summary><pre tabindex="0" :aria-label="`${item.name} 缺失文件完整路径`">{{ item.missing.join('\n') }}</pre></details>
                <details v-if="item.damaged.length" class="gui-file-details"><summary>内容或记录异常（{{ item.damaged.length }}）</summary><pre tabindex="0" :aria-label="`${item.name} 异常文件完整路径`">{{ item.damaged.join('\n') }}</pre></details>
                <p v-for="(issue, index) in [...item.issues, ...item.unsupported]" :key="index" class="gui-issue">{{ issue }}</p>
                <p v-if="item.generated.some((file) => file.kind === 'optional_derived_bytecode_unverified' && file.present)" class="gui-issue">发现未验证字节码。需要进一步诊断，固定无字节码运行合同禁止直接执行此环境。</p>
                <p v-if="packagePlanDisabled(item) && !mutationDisabled" class="hint">请先处理源码、元数据、文件记录异常或未完成的实例事务；单包修复清单由启动器重新验证后生成。</p>
              </article>
              <section v-if="guiPreview" id="gui-repair-preview" class="gui-preview" aria-labelledby="gui-preview-title">
                <div class="section-caption"><h2 id="gui-preview-title">待审修复清单：{{ guiPreview.package }}</h2><button class="compact" :disabled="busy" @click="guiPreview = null">关闭清单</button></div>
                <p>{{ guiPreview.version }} · 实例代次 {{ guiPreview.generation }} · {{ guiPreview.paths.length.toLocaleString() }} 个允许文件路径</p>
                <p class="hint">包含包原文件、安装器生成项、入口脚本及由原文件推导的可选缓存路径。生成路径进入清单不代表其内容已经验证。</p>
                <p class="hint">{{ guiPreview.before_original_files_verified ? '修复前原文件已通过静态检查，执行前会继续验证运行状态。' : '修复前发现原文件缺坏，已阻止执行受影响环境；修复后再验证完整依赖与关键导入。' }}</p>
                <pre class="gui-paths" tabindex="0" aria-label="单包修复完整允许路径清单">{{ guiPreview.paths.join('\n') }}</pre>
                <button class="primary" :disabled="mutationDisabled || guiPlanBlocked" @click="confirmGuiRepair">审查并确认修复此包</button>
              </section>
              <p class="scope-note">本次诊断只读取文件。固定包的原文件摘要与记录集合、安装器生成项的验证范围分别展示；诊断结果不代表训练器已健康启动。</p>
            </template>
          </section>
          <template v-else>
            <div class="environment-actions"><button :disabled="mutationDisabled" @click="command('bootstrap', '准备基础工具')">准备基础工具</button><button :disabled="mutationDisabled" @click="command('restore_trainer', '恢复当前版本源码')">恢复当前版本源码</button><button :disabled="mutationDisabled" @click="command('install_environment', '安装或修复运行环境')">安装 / 修复运行环境</button></div>
            <p class="hint">源码恢复会将原目录移至备份；请留意日志中的路径和数据处理结果。运行中的训练器需先停止，才能安装或修复。</p>
          </template>

        </div><p class="page-note"><Icon name="info" />模型与训练任务在训练网页中管理。<button class="text-button" @click="showLogs()">查看环境日志<Icon name="arrow" /></button></p>
      </section>
      <LogPanel v-show="page === 'logs'" :active="page === 'logs'" :entries="logs" :current-session-id="logSessionId" :root="path.trim()" :focus-request="logFocus" :font-size="appearance.logFontSize">
        <template #operation>
          <div v-if="report?.interrupted.length || history.some(item => item.status === 'interrupted')" class="operation-warning" role="region" aria-label="未完成操作"><Icon name="info" /><span>存在未完成操作，请在环境管理中检查并恢复。</span><button @click="page = 'environment'; advanced = true">查看恢复</button></div>
          <div v-if="operation?.status === 'running'" class="operation-monitor" role="region" aria-label="当前安装与修复任务"><div><strong>当前操作</strong><span>{{ phaseText[operation.phase] }} · {{ operation.cancel_requested ? '正在取消，等待收尾' : message }}</span></div><button data-action="cancel-operation" :disabled="operation.cancel_requested" @click="cancelCurrentOperation">{{ operation.cancel_requested ? '正在收尾' : '取消操作' }}</button></div>
          <div v-if="error" class="operation-error" role="alert"><span>{{ error }}</span><button class="icon-button" aria-label="关闭错误提示" @click="error = ''"><Icon name="close" /></button></div>
        </template>
      </LogPanel>
      <section v-show="page === 'settings'" class="settings-page" aria-label="设置"><nav class="settings-nav" aria-label="设置分类"><h1>启动器设置</h1><button v-for="item in ([{ id: 'appearance', icon: 'image', label: '外观' }, { id: 'network', icon: 'network', label: '网络' }, { id: 'profiles', icon: 'folder', label: '用户资料' }, { id: 'security', icon: 'shield', label: '安全与更新' }, { id: 'about', icon: 'info', label: '关于' }] as const)" :key="item.id" :class="{ selected: setting === item.id }" :aria-current="setting === item.id ? 'page' : undefined" @click="openSetting(item.id)"><Icon :name="item.icon" />{{ item.label }}</button></nav><div class="settings-content">
        <section v-show="setting === 'appearance'" class="appearance-settings"><h2>外观</h2><div class="setting-row"><h3>背景图片</h3><p class="setting-description">默认使用项目 Qwen-Image-2.1 海报。可以选择本地图片，保存在这台设备上。</p><input ref="backgroundInput" type="file" accept="image/png,image/jpeg,image/webp" hidden @change="chooseBackground" /><div class="actions"><button @click="backgroundInput?.click()"><Icon name="image" />选择本地背景</button><button :disabled="!appearance.background" @click="appearance.background = ''">恢复默认</button></div></div><div class="setting-row"><label for="background-mask">亚克力着色强度 <span>{{ appearance.mask }}%</span></label><input id="background-mask" v-model.number="appearance.mask" type="range" min="0" max="80" /></div><div class="setting-row"><label for="background-blur">亚克力模糊 <span>{{ appearance.blur }}px</span></label><input id="background-blur" v-model.number="appearance.blur" type="range" min="0" max="60" /></div><label class="switch-line"><input v-model="appearance.reduceMotion" type="checkbox" />减少动态效果</label><div class="setting-row"><label for="log-font-size">日志字号</label><AcrylicSelect id="log-font-size" v-model="appearance.logFontSize" :options="[12, 13, 14, 16, 18].map(size => ({ value: size, label: `${size} px` }))" /></div><p class="setting-description">外观更改会自动保存。首页保留清晰海报，其他页面与侧栏使用连续的亚克力材质。</p></section>
        <section v-show="setting === 'network'"><h2>网络</h2><section class="network-settings">

            <p class="hint">自动模式按环境变量与系统代理选择连接方式。手动代理连接失败会报告错误；本机服务始终直接连接。</p>
            <button class="compact" :disabled="busy || !sameRoot" @click="readNetworkSettings">读取当前设置</button>
            <template v-if="networkView">
              <label>连接方式<AcrylicSelect v-model="networkDraft.mode" :disabled="busy" :options="[{ value: 'auto', label: '自动' }, { value: 'system', label: '系统代理' }, { value: 'manual', label: '手动代理' }, { value: 'direct', label: '直接连接' }]" /></label>
              <template v-if="networkDraft.mode === 'manual' || networkDraft.mode === 'auto'">
                <label>HTTP 代理<input v-model="networkDraft.http_proxy" type="password" autocomplete="off" spellcheck="false" placeholder="http://127.0.0.1:11809" :disabled="busy" @input="editNetworkField('http_proxy')"><button :disabled="busy" @click="inheritNetworkField('http_proxy')">恢复继承</button></label>
                <label>HTTPS 代理<input v-model="networkDraft.https_proxy" type="password" autocomplete="off" spellcheck="false" placeholder="手动模式可复用 HTTP 代理" :disabled="busy" @input="editNetworkField('https_proxy')"><button :disabled="busy" @click="inheritNetworkField('https_proxy')">恢复继承</button></label>
              </template>
              <label v-if="networkDraft.mode !== 'direct'">绕过代理<input v-model="networkDraft.no_proxy" spellcheck="false" placeholder="example.org,10.0.0.0/8" :disabled="busy" @input="editNetworkField('no_proxy')"><button :disabled="busy" @click="inheritNetworkField('no_proxy')">恢复继承</button></label>
              <p class="hint">自动模式中，清空已填写的代理会禁用对应协议的代理；“恢复继承”会重新采用环境或系统设置。未编辑的空值设置会原样保留。</p>
              <p class="hint">生效来源：{{ ({ environment: '环境变量', system: '系统设置', manual: '手动设置', direct: '直接连接' } as Record<string, string>)[networkView.diagnostic.source] ?? networkView.diagnostic.source }}。{{ networkView.diagnostic.warning }}</p>
              <p class="hint">设置仅保存在当前安装目录；修改后用于后续操作。代理凭据会保存在本机，日志中的代理地址会隐藏凭据。</p>
              <button :disabled="mutationDisabled" @click="storeNetworkSettings">保存网络设置</button>
            </template>
          </section></section>
        <section v-show="setting === 'profiles'"><h2>用户资料</h2><p class="setting-description">训练器版本与用户资料独立保存。更换安装目录前请先停止当前服务。</p><section class="directory-panel" aria-labelledby="directory-label"><label id="directory-label" for="install-root">安装目录</label><div class="directory-input"><input id="install-root" v-model="path" :disabled="busy || running || transitioning" placeholder="首次检查将使用默认目录" spellcheck="false" @keydown.enter="command('inspect', '检查安装状态')" /><button :disabled="busy || running || transitioning" @click="browse">选择…</button><button :disabled="busy || transitioning" @click="command('inspect', '检查安装状态')">检查</button></div></section><section v-if="report?.profile_path && sameRoot" class="profile-info"><span>当前共享用户资料</span><code>{{ report.profile_path }}</code></section><ImportPanel v-if="sameRoot && registrationRelease" :root="path.trim()" :release-id="registrationRelease.id" :disabled="mutationDisabled" @operate="startGuiOperation" /></section>
        <section v-show="setting === 'security'"><h2>安全与更新</h2><TrustPanel v-if="sameRoot && registrationRelease" :root="path.trim()" :release-id="registrationRelease.id" :disabled="mutationDisabled" @changed="command('inspect', '刷新发布清单')" /><ShellPanel v-if="sameRoot && registrationRelease" :root="path.trim()" :release-id="registrationRelease.id" :disabled="mutationDisabled" /><p v-else class="setting-description">检查安装目录并选择训练器版本后，可管理更新来源与启动器恢复。</p></section>
        <section v-show="setting === 'about'" class="about-page"><img class="about-symbol" src="/assets/home-logo.webp" alt="Next Trainer 项目标志" /><h2>Next Trainer</h2><p class="setting-description">桌面启动器</p><p class="about-version">启动器 {{ appVersion }}<br />训练器 {{ currentVersion?.version ?? report?.version ?? '尚未选择' }}<span v-if="currentVersion"> · {{ currentVersion.commit.slice(0, 8) }}</span></p><p class="setting-description">独立环境、集中日志，让创作从容开始。</p><div class="setting-links"><button class="text-button" @click="openProjectLink('project')">项目主页 ↗</button><button class="text-button" @click="openProjectLink('issues')">问题反馈 ↗</button><button class="text-button" @click="openProjectLink('license')">开源许可 ↗</button></div><p class="setting-description">界面布局参考 Starward（星穹启动器）。默认背景与品牌使用本项目资源。</p></section>
      </div></section>

    </main>
    <div v-if="toast" class="toast" role="status">{{ toast }}</div>
        <div v-if="confirmation" class="dialog-backdrop" @keydown.esc.prevent="dismissConfirmation" @keydown="trapDialogFocus"><section class="confirmation-dialog" :class="{ 'gui-confirmation': confirmation.paths }" role="dialog" aria-modal="true" aria-labelledby="confirmation-title" aria-describedby="confirmation-detail"><h2 id="confirmation-title">{{ confirmation.title }}</h2><p id="confirmation-detail">{{ confirmation.detail }}</p><pre v-if="confirmation.paths" class="gui-paths" tabindex="0" aria-label="确认修复的完整文件清单">{{ confirmation.paths.join('\n') }}</pre><div><button ref="confirmationCancel" @click="dismissConfirmation">取消</button><button :class="confirmation.destructive ? 'danger' : 'primary'" @click="confirmAction">{{ confirmation.action }}</button></div></section></div>
  </div>
</template>
