<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { cancelOperation, chooseDirectory, diagnoseGui, installManagedRelease, listenToLogs, openTrainer, operationEvents, operationHistory, operationSnapshot, planGuiRepair, prefetchRelease, previewSourceRepair, recoverGuiRepair, repairGuiPackage, repairManagedSource, rollbackRelease, runCommand, runReleaseCommand, stopTrainer } from './bridge'
import type { GuiDiagnosis, GuiRepairPreview, OperationSnapshot, PackageIntegrity, ReleaseCommand, Report, ReportCommand, VersionView } from './bridge'
import { loadNetworkSettings, saveNetworkSettings } from './bridge'
import type { NetworkSettings, NetworkSettingsView } from './bridge'
import { settingsForSave } from './network-settings'
import type { ProxyField } from './network-settings'
import { previewBasePythonRepair, repairBasePython, recoverBasePython } from './bridge'
import type { BasePythonRepairPreview } from './bridge'
import { getDownloadBudget, reconcileDownloadBudget, saveDownloadBudget } from './bridge'
import type { BudgetSnapshot, OperationDownloadReceipt } from './bridge'
import { budgetDraft, formatBudgetBytes, parseBudgetCap } from './download-budget'
import { previewGuiRegistration, restoreGuiRegistration, recoverGuiRegistration } from './bridge'
import type { GuiRegistrationPreview } from './bridge'

type Page = 'launch' | 'versions' | 'environment'
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
const logs = ref<string[]>([])
const logPanel = ref<HTMLPreElement>()
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
const showAllPackages = ref(false)
const networkView = ref<NetworkSettingsView | null>(null)
const networkDraft = ref({ mode: 'auto' as NonNullable<NetworkSettings['mode']>, http_proxy: '', https_proxy: '', no_proxy: '' })
const networkInherit = ref<ProxyField[]>([])
const downloadBudget = ref<BudgetSnapshot | null>(null)
const downloadBudgetDraft = ref(budgetDraft(null, null))
const downloadBudgetEdited = ref(false)
const downloadBudgetError = ref('')
const downloadBudgetSaveError = ref('')
const downloadBudgetNotice = ref('')
const downloadBudgetRefreshing = ref(false)
const downloadBudgetSaving = ref(false)
let budgetEpoch = 0
let budgetTimer: ReturnType<typeof setInterval> | undefined
let guiEpoch = 0
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
const managedCurrent = computed(() => Boolean(sameRoot.value && currentVersion.value?.managed_recipe))
const registrationVersions = computed(() => versions.value.filter((version) => version.managed_recipe))
const registrationRelease = computed(() => registrationVersions.value.find((version) => version.id === registrationReleaseId.value)
  ?? (currentVersion.value?.managed_recipe ? currentVersion.value : registrationVersions.value[0]))
const guiRecoveryNeeded = computed(() => Boolean(guiDiagnosis.value?.dirty || guiDiagnosis.value?.recovery_pending || (guiDiagnosis.value && guiDiagnosis.value.generation !== guiDiagnosis.value.binding_generation)))
const affectedPackages = computed(() => guiDiagnosis.value?.integrity.packages.filter(packageNeedsAttention) ?? [])
const visiblePackages = computed(() => showAllPackages.value ? guiDiagnosis.value?.integrity.packages ?? [] : affectedPackages.value)
const guiPlanBlocked = computed(() => Boolean(guiRecoveryNeeded.value || guiDiagnosis.value?.source_error || guiDiagnosis.value?.installed_metadata_error))
const budget = computed(() => downloadBudget.value?.budget)
const latestDownloadReceipt = computed(() => downloadBudget.value?.latest_receipt)
const budgetNeedsSetup = computed(() => sameRoot.value && downloadBudget.value && !budget.value?.enabled)
const budgetSaveDisabled = computed(() => mutationDisabled.value || downloadBudgetRefreshing.value || downloadBudgetSaving.value || !downloadBudget.value || !downloadBudgetEdited.value || Boolean(budget.value?.active_operation || budget.value?.pending_reconciliation))

watch([path, () => currentVersion.value?.id], clearGuiState, { flush: 'sync' })
watch(path, () => { networkView.value = null; networkInherit.value = []; networkDraft.value = { mode: 'auto', http_proxy: '', https_proxy: '', no_proxy: '' } }, { flush: 'sync' })
watch(path, () => {
  budgetEpoch += 1
  downloadBudget.value = null
  downloadBudgetDraft.value = budgetDraft(null, null)
  downloadBudgetEdited.value = false
  downloadBudgetError.value = ''
  downloadBudgetSaveError.value = ''
  downloadBudgetNotice.value = ''
  downloadBudgetRefreshing.value = false
  downloadBudgetSaving.value = false
}, { flush: 'sync' })

function acceptDownloadBudget(value: BudgetSnapshot, replaceDraft = false) {
  downloadBudget.value = value
  if (replaceDraft || !downloadBudgetEdited.value) {
    downloadBudgetDraft.value = budgetDraft(value.budget.root_cap_body_bytes, value.budget.policy_revision)
    downloadBudgetEdited.value = false
  }
}
async function refreshDownloadBudget(replaceDraft = false) {
  if (!sameRoot.value || downloadBudgetRefreshing.value || downloadBudgetSaving.value) return
  const root = path.value.trim()
  const epoch = budgetEpoch
  downloadBudgetRefreshing.value = true
  try {
    const value = await getDownloadBudget(root)
    if (disposed || epoch !== budgetEpoch || root !== path.value.trim()) return
    acceptDownloadBudget(value, replaceDraft)
    downloadBudgetError.value = ''
    if (replaceDraft) {
      downloadBudgetSaveError.value = ''
      downloadBudgetNotice.value = '已重新读取保存的额度。'
    }
  } catch (reason) {
    if (!disposed && epoch === budgetEpoch && root === path.value.trim()) downloadBudgetError.value = errorText(reason)
  } finally {
    if (epoch === budgetEpoch) downloadBudgetRefreshing.value = false
  }
}
function editDownloadBudget() {
  downloadBudgetEdited.value = true
  downloadBudgetNotice.value = ''
}
async function storeDownloadBudget() {
  if (budgetSaveDisabled.value) return
  let bytes: number
  try { bytes = parseBudgetCap(downloadBudgetDraft.value.value, downloadBudgetDraft.value.unit) }
  catch (reason) { downloadBudgetSaveError.value = errorText(reason); return }
  const root = path.value.trim()
  const epoch = budgetEpoch
  const revision = downloadBudgetDraft.value.expectedRevision
  downloadBudgetSaving.value = true
  downloadBudgetError.value = ''
  downloadBudgetSaveError.value = ''
  await perform('保存下载额度', async () => {
    try {
      const value = await saveDownloadBudget(root, revision, bytes)
      if (disposed || epoch !== budgetEpoch || root !== path.value.trim()) return
      acceptDownloadBudget(value, true)
      downloadBudgetNotice.value = '下载额度已保存，累计扣账会继续保留。'
    } catch (reason) {
      if (epoch === budgetEpoch && root === path.value.trim()) downloadBudgetSaveError.value = `${errorText(reason)}。可重新读取保存的额度后再编辑。`
      throw reason
    }
  })
  if (epoch === budgetEpoch) downloadBudgetSaving.value = false
}
function showDownloadBudget() {
  page.value = 'environment'
  void nextTick(() => { document.getElementById('download-budget-title')?.scrollIntoView({ block: 'start' }) })
}
function confirmBudgetReconciliation() {
  if (mutationDisabled.value || !budget.value || !(budget.value.pending_reconciliation || budget.value.active_operation)) return
  const root = path.value.trim()
  const epoch = budgetEpoch
  return ask({
    scope: 'gui', title: '结清中断下载预留',
    detail: `启动器会先确认此目录没有正在执行的操作，再结束遗留的下载计账。当前显示的未结预留为 ${formatBudgetBytes(budget.value.reserved_body_bytes)}；未能确认的预留将计入保守扣账，累计扣账与额度会继续保留，余额不会因此增加。`,
    action: '确认按保守额度结清',
    execute: async () => {
      if (epoch !== budgetEpoch || root !== path.value.trim() || mutationDisabled.value) return
      downloadBudgetSaving.value = true
      downloadBudgetSaveError.value = ''
      await perform('结清中断下载预留', async () => {
        try {
          const value = await reconcileDownloadBudget(root)
          if (disposed || epoch !== budgetEpoch || root !== path.value.trim()) return
          acceptDownloadBudget(value, true)
          downloadBudgetError.value = ''
          downloadBudgetNotice.value = '中断预留已结清，累计扣账与原额度继续保留。'
        } catch (reason) {
          if (epoch === budgetEpoch && root === path.value.trim()) downloadBudgetSaveError.value = errorText(reason)
          throw reason
        }
      })
      if (epoch === budgetEpoch) downloadBudgetSaving.value = false
    },
  })
}
function receiptOutcome(value: OperationDownloadReceipt['outcome']) {
  return ({ succeeded: '已完成', failed: '失败', cancelled: '已取消', interrupted: '中断后已补记' })[value]
}
function receiptTime(value: number) {
  return new Date(value).toLocaleString('zh-CN', { hour12: false })
}

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
  void refreshDownloadBudget()
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
      events.forEach((event) => { addLog(event.message); operationCursor = Math.max(operationCursor, event.seq) })
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
      await refreshDownloadBudget()
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
  budgetTimer = setInterval(() => {
    if (busy.value || page.value === 'environment') void refreshDownloadBudget()
  }, 1000)
  try { unlisten = await listenToLogs(addLog) }
  catch { addLog('桌面事件接口尚未连接；请通过桌面启动器打开此页面。') }
  await command('inspect', '检查安装状态')
  try { await refreshHistory() } catch (reason) { error.value = errorText(reason) }
})
onBeforeUnmount(() => { disposed = true; if (operationTimer) clearTimeout(operationTimer); if (budgetTimer) clearInterval(budgetTimer); unlisten?.() })
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
        <section v-if="operation" class="interrupted-note" role="status" aria-live="polite"><strong>{{ phaseText[operation.phase] }} · {{ operationStatusText[operation.status] }}</strong><p>{{ operation.kind === 'download' ? '准备安装文件；完整校验通过后可继续安装此版本。' : operation.kind === 'repair' ? '按独立事务修复或恢复指定包，完成后重新诊断确认实例状态。' : '安装并验证主程序与独立运行环境。' }}</p><button v-if="operation.status === 'running'" :disabled="operation.cancel_requested" @click="cancelCurrentOperation">{{ operation.cancel_requested ? '正在取消与收尾…' : '取消操作' }}</button><p v-if="operation.error">{{ operation.error.message }}</p></section>
        <section v-else-if="history.some((item) => item.status === 'interrupted')" class="interrupted-note" role="status"><strong>上次操作未完整结束</strong><p>下载可在版本管理中继续；安装与修复请重新检查，固定 GUI 实例可在环境管理中诊断并恢复。</p></section>
        <section v-if="report?.interrupted.length && sameRoot" class="interrupted-note" role="status"><strong>检测到未完成的操作</strong><ul><li v-for="(item, index) in report.interrupted" :key="index">{{ item }}</li></ul><span>请重新检查后重试对应安装或修复步骤。</span></section>
        <section v-if="budgetNeedsSetup && page !== 'environment'" class="budget-setup-note"><p>尚未设置此目录的下载额度。已验证的缓存和本地修复可以继续使用；联网下载前请先设置有限额度。</p><button class="compact" :disabled="busy" @click="showDownloadBudget">设置下载额度</button></section>
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
          <section v-for="group in channels" :key="group.channel" class="channel-section" :aria-label="channelName(group.channel)"><h3>{{ channelName(group.channel) }}<span>{{ group.channel === 'dev' ? '包含开发中的改动' : group.channel === 'main' ? '稳定发布线' : '内置版本' }}</span></h3><p v-if="!group.versions.length" class="empty-channel">内置清单尚未提供此发布线的版本。</p><article v-for="version in group.versions" :key="version.id" class="version-card" :aria-label="`${version.channel} ${version.version} ${version.commit.slice(0, 8)}`"><div class="version-top"><div><strong>{{ version.version }}</strong><span v-if="version.current || version.id === report?.current_release" class="current-tag">当前使用</span><span v-else-if="version.id === report?.previous_known_good" class="healthy-tag">回退保留</span><span v-else-if="version.known_good" class="healthy-tag">曾健康启动</span></div><span class="release-state" :class="{ good: version.installed && version.source_ok && version.environment_ok }">{{ releaseState(version) }}</span></div><dl class="version-details"><div><dt>提交</dt><dd><code>{{ version.commit }}</code></dd></div><div><dt>下载</dt><dd><code>{{ formatBytes(version.download_bytes) }}</code><span class="detail-note">源码制品</span></dd></div><div><dt>磁盘</dt><dd><code>{{ formatBytes(version.source_bytes) }}</code><span class="detail-note">{{ version.installed ? '源码展开；运行环境另计' : '预计源码展开；运行环境另计' }}</span></dd></div><div v-if="version.installed"><dt>检查</dt><dd><span :class="{ 'check-warning': !version.source_ok }">源码{{ version.source_ok ? '完整' : '需修复' }}</span><span class="detail-separator">/</span><span :class="{ 'check-warning': !version.environment_ok }">环境{{ version.environment_ok ? '通过' : '需修复' }}</span></dd></div></dl><div class="version-actions"><button v-if="version.managed_recipe && version.installed" :disabled="mutationDisabled" @click="inspectSourceRepair(version)">源码修复清单</button><button :disabled="mutationDisabled" @click="install(version)">{{ version.installed ? '检查并补全安装' : '下载安装' }}</button><button :disabled="mutationDisabled || !version.installed || !version.source_ok || !version.environment_ok || version.current || version.id === report?.current_release" @click="select(version)">切换到此版本</button><button class="delete-button" :disabled="mutationDisabled || !version.installed || protectedRelease(version)" :title="protectedRelease(version) ? '当前版本及上一已健康版本需保留' : '删除受管版本目录'" @click="remove(version)">删除</button></div></article></section>
          <p class="scope-note">已安装表示版本目录存在，不代表可以运行。切换依据每个版本的实际检查；当前版本和上一已健康版本受删除保护。main / dev 使用发布线与提交区分，即使版本号相同也分别管理。</p>
          <section class="environment-actions" aria-label="准备版本安装文件"><button v-for="version in versions" :key="version.id" :disabled="mutationDisabled" @click="prefetch(version)">准备 {{ channelName(version.channel) }} 安装文件</button></section>
        </template>

        <template v-else>
          <div class="section-caption"><h2>主程序与基础工具</h2><button class="compact" :disabled="busy" @click="command('inspect', '检查安装状态')">重新检查</button></div>
          <p class="environment-scope">当前检查覆盖启动器基础工具、训练器主程序和网页资源。各独立训练引擎的 Python / Torch / GPU 诊断尚未接入。</p>
          <div v-if="report?.checks.length && sameRoot" class="checks" role="list" aria-label="环境检查明细"><div v-for="(check, index) in report.checks" :key="`${index}-${check.name}`" class="check-row" role="listitem"><span class="check-badge" :class="{ ok: check.ok }">{{ check.ok ? '通过' : '待处理' }}</span><div><strong>{{ check.name }}</strong><p>{{ check.detail }}</p></div></div></div>
          <p v-else class="scope-note">请先检查安装目录。训练器目录缺失或环境损坏时，桌面检查与修复入口仍可使用。</p>
          <details class="network-settings">
            <summary>网络与代理设置</summary>
            <p class="hint">自动模式按环境变量与系统代理选择连接方式。手动代理连接失败会报告错误；本机服务始终直接连接。</p>
            <button class="compact" :disabled="busy || !sameRoot" @click="readNetworkSettings">读取当前设置</button>
            <template v-if="networkView">
              <label>连接方式<select v-model="networkDraft.mode" :disabled="busy"><option value="auto">自动</option><option value="system">系统代理</option><option value="manual">手动代理</option><option value="direct">直接连接</option></select></label>
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
          </details>
          <section v-if="sameRoot" class="download-budget" aria-labelledby="download-budget-title">
            <div class="section-caption"><h2 id="download-budget-title">下载额度与计账</h2><button class="compact" :disabled="downloadBudgetRefreshing || downloadBudgetSaving" @click="refreshDownloadBudget(true)">{{ downloadBudgetRefreshing ? '正在读取…' : '重新读取保存的额度' }}</button></div>
            <p class="budget-measurement">HTTP 正文交付与保守扣账</p>
            <p class="hint">额度覆盖启动器下载的制品正文。累计扣账包含已交付正文与无法确认交付数时的保守扣账，未结预留暂占用余额。系统及其他程序的网络流量另计。</p>
            <p v-if="downloadBudgetError" class="gui-issue" role="alert">{{ downloadBudgetError }}{{ downloadBudget ? '。以下为上次成功读取的统计。' : '' }}</p>
            <template v-if="budget">
              <p v-if="!budget.enabled" class="hint">{{ budget.pending_reconciliation ? '下载计账初始化尚未完成，请先结清中断预留以恢复已保存的额度。' : '尚未启用下载计账。请自行填写有限额度；已验证的缓存和本地操作无需设置额度。' }}</p>
              <template v-else>
                <dl class="budget-statistics">
                  <div><dt>累计额度</dt><dd :title="`${budget.root_cap_body_bytes?.toLocaleString()} 字节`">{{ formatBudgetBytes(budget.root_cap_body_bytes) }}</dd></div>
                  <div><dt>累计扣账</dt><dd>{{ formatBudgetBytes(budget.counters.observed_body_bytes + budget.counters.uncertain_charge_bytes) }}</dd></div>
                  <div><dt>已交付正文</dt><dd>{{ formatBudgetBytes(budget.counters.observed_body_bytes) }}</dd></div>
                  <div><dt>保守扣账</dt><dd>{{ formatBudgetBytes(budget.counters.uncertain_charge_bytes) }}</dd></div>
                  <div><dt>未结预留</dt><dd>{{ formatBudgetBytes(budget.reserved_body_bytes) }}</dd></div>
                  <div><dt>可用余额</dt><dd>{{ formatBudgetBytes(budget.remaining_body_bytes) }}</dd></div>
                </dl>
                <p class="hint">{{ budget.coverage_prior_history === 'not_measured' ? '启用前的历史用量未计量；以上累计从启用时开始。' : '以上累计从启用时开始，启用前的历史用量无法据此还原。' }} · {{ budget.counters.requests.toLocaleString() }} 次请求 · {{ budget.counters.cache_hits.toLocaleString() }} 次已计入的缓存命中</p>
                <p v-if="budget.active_operation" class="budget-state" role="status">当前下载操作 <code>{{ budget.active_operation }}</code> · 本次剩余额度 {{ formatBudgetBytes(budget.operation_remaining_body_bytes) }}。操作结束前暂不能修改额度。</p>
                <p v-else-if="budget.pending_reconciliation" class="budget-state" role="status">存在尚未核对完成的计账，请先结清中断预留后再修改额度。</p>
                <p v-else-if="budget.remaining_body_bytes === 0" class="budget-state" role="status">下载额度已用尽。已验证缓存仍可使用；继续联网下载前需增加累计额度。</p>
              </template>
              <button v-if="budget.pending_reconciliation || budget.active_operation" class="compact" :disabled="mutationDisabled || downloadBudgetSaving || downloadBudgetRefreshing" @click="confirmBudgetReconciliation">结清中断预留</button>
              <div class="budget-cap-form">
                <label for="download-cap">此目录累计额度</label>
                <div class="budget-cap-input">
                  <input id="download-cap" v-model="downloadBudgetDraft.value" inputmode="numeric" maxlength="32" autocomplete="off" placeholder="填写正整数" :disabled="mutationDisabled || downloadBudgetSaving || budget.pending_reconciliation" aria-describedby="download-cap-hint" @input="editDownloadBudget" @keydown.enter="storeDownloadBudget" />
                  <select v-model="downloadBudgetDraft.unit" aria-label="下载额度单位" :disabled="mutationDisabled || downloadBudgetSaving || budget.pending_reconciliation" @change="editDownloadBudget"><option value="GiB">GiB</option><option value="MiB">MiB</option><option value="B">字节</option></select>
                  <button :disabled="budgetSaveDisabled" @click="storeDownloadBudget">{{ budget.enabled ? '保存累计额度' : '启用有限额度' }}</button>
                </div>
                <p id="download-cap-hint" class="hint">修改额度保留已有累计扣账。请输入正整数；0 不表示无限制。{{ downloadBudgetEdited ? '存在尚未保存的修改。' : '' }}</p>
                <p v-if="downloadBudgetSaveError" class="gui-issue" role="alert">{{ downloadBudgetSaveError }}</p>
                <p v-if="downloadBudgetNotice" class="hint" role="status">{{ downloadBudgetNotice }}</p>
              </div>
              <section v-if="latestDownloadReceipt" class="budget-receipt" aria-labelledby="download-receipt-title">
                <h3 id="download-receipt-title">最近下载计账<span>{{ receiptOutcome(latestDownloadReceipt.outcome) }} · {{ receiptTime(latestDownloadReceipt.finished_at_ms) }}</span></h3>
                <p><code>{{ latestDownloadReceipt.operation_id }}</code><span v-if="latestDownloadReceipt.retry_of"> · 重试自 <code>{{ latestDownloadReceipt.retry_of }}</code></span></p>
                <p>已交付正文 {{ formatBudgetBytes(latestDownloadReceipt.counters.observed_body_bytes) }} · 保守扣账 {{ formatBudgetBytes(latestDownloadReceipt.counters.uncertain_charge_bytes) }} · {{ latestDownloadReceipt.accounting_complete ? '本次计账已结清' : '本次计账尚未结清' }}</p>
                <p>{{ latestDownloadReceipt.counters.requests }} 次请求 · {{ latestDownloadReceipt.counters.retries }} 次重试 · {{ latestDownloadReceipt.counters.redirects }} 次跳转 · {{ latestDownloadReceipt.counters.cache_hits }} 次缓存命中</p>
                <details><summary>查看本次下载限制</summary><p>正文与保守扣账 {{ formatBudgetBytes(latestDownloadReceipt.limits.max_charged_body_bytes) }}；最多 {{ latestDownloadReceipt.limits.max_requests }} 次请求、{{ latestDownloadReceipt.limits.max_retries }} 次重试、{{ latestDownloadReceipt.limits.max_redirects }} 次跳转，总时限 {{ latestDownloadReceipt.limits.max_elapsed_ms / 1000 }} 秒。</p></details>
              </section>
              <p v-else class="hint">尚无已结束的下载计账记录。</p>
            </template>
            <p v-else-if="!downloadBudgetError" class="hint">正在读取此目录的下载额度与计账…</p>
          </section>
          <section v-if="sameRoot && registrationVersions.length" class="gui-diagnostics" aria-labelledby="registration-title">
            <div class="section-caption"><h2 id="registration-title">恢复安装登记</h2><button :disabled="mutationDisabled" @click="inspectGuiRegistration">只读检查登记</button></div>
            <p class="hint">源码和环境仍在、安装记录丢失时，可离线验证并补齐登记。检查不会执行解释器；确认后会使用独立临时资料验证真实入口。</p>
            <label>需要恢复的版本<select :value="registrationRelease?.id" :disabled="mutationDisabled" @change="registrationReleaseId = ($event.target as HTMLSelectElement).value; changeRegistrationRelease()"><option v-for="version in registrationVersions" :key="version.id" :value="version.id">{{ channelName(version.channel) }} · {{ version.version }} · {{ version.commit.slice(0, 8) }}</option></select></label>
            <template v-if="registrationPreview">
              <p v-if="registrationPreview.reason" class="gui-issue" role="alert">{{ registrationPreview.reason }}</p>
              <p v-if="registrationPreview.status === 'pending'" class="hint">存在待恢复登记事务：{{ registrationPreview.transaction }}</p>
              <label v-if="registrationPreview.candidates?.length">指定已有实例<select v-model="registrationInstanceId" :disabled="mutationDisabled" @change="guiEpoch += 1; registrationPreview = null"><option value="">按已有绑定检查</option><option v-for="candidate in registrationPreview.candidates" :key="`${candidate.id}:${candidate.storage_version}`" :value="candidate.id">{{ candidate.id }} · 路径格式 {{ candidate.storage_version }} · 代次 {{ candidate.generation }} · {{ candidate.status === 'clean' ? '已有验证记录' : candidate.status === 'missing_state' ? '实例记录缺失' : '需要先恢复原事务' }}</option></select><span class="hint">选择后请重新执行只读检查，确认环境与影响。</span></label>
              <p v-if="registrationPreview.plan">环境：<code>{{ registrationPreview.plan.proof.environment }}</code> · {{ registrationPreview.plan.proof.files.toLocaleString() }} 个可信文件</p>
              <button v-if="registrationPreview.status === 'ready'" :disabled="mutationDisabled" @click="confirmGuiRegistration()">审查并恢复登记</button>
              <button v-if="registrationPreview.status === 'pending'" :disabled="mutationDisabled" @click="confirmGuiRegistration(true)">继续未完成登记恢复</button>
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
          <section v-if="report?.profile_path && sameRoot" class="profile-info"><span>共享用户资料</span><code>{{ report.profile_path }}</code></section>
        </template>
      </div>

      <section class="runtime-panel" aria-label="操作日志"><div class="runtime-status" role="status" aria-live="polite"><span class="working-dot" :class="{ active: pending }" aria-hidden="true"></span><span>{{ message }}</span><span class="log-count">{{ logs.length }} 行日志</span></div><p v-if="error" class="error" role="alert">{{ error }}</p><pre ref="logPanel" tabindex="0" aria-label="日志内容">{{ logs.length ? logs.join('\n') : '等待操作。检查结果以实际文件和运行探测为准。' }}</pre></section>
    </main>

    <div v-if="confirmation" class="dialog-backdrop" @keydown.esc.prevent="dismissConfirmation" @keydown="trapDialogFocus"><section class="confirmation-dialog" :class="{ 'gui-confirmation': confirmation.paths }" role="dialog" aria-modal="true" aria-labelledby="confirmation-title" aria-describedby="confirmation-detail"><h2 id="confirmation-title">{{ confirmation.title }}</h2><p id="confirmation-detail">{{ confirmation.detail }}</p><pre v-if="confirmation.paths" class="gui-paths" tabindex="0" aria-label="确认修复的完整文件清单">{{ confirmation.paths.join('\n') }}</pre><div><button ref="confirmationCancel" @click="dismissConfirmation">取消</button><button :class="confirmation.destructive ? 'danger' : 'primary'" @click="confirmAction">{{ confirmation.action }}</button></div></section></div>
  </div>
</template>

<style scoped>
.version-actions { flex-wrap: wrap; }
.network-settings { margin: 15px 0; padding: 10px; border: 1px solid #e5e5e5; font-size: 11px; }
.network-settings summary { cursor: pointer; }
.network-settings label { display: flex; align-items: center; gap: 12px; margin: 10px 0; }
.network-settings input, .network-settings select { flex: 1; min-width: 0; padding: 6px; border: 1px solid #d4d4d4; background: white; font: inherit; }
.budget-setup-note { display: flex; align-items: center; justify-content: space-between; gap: 10px; border: 1px solid #e5e5e5; padding: 9px 10px; margin-bottom: 14px; }
.budget-setup-note p { color: #737373; font-size: 10px; line-height: 1.8; margin: 0; }
.download-budget { border: 1px solid #e5e5e5; padding: 12px; margin: 15px 0; }
.budget-measurement { font-size: 11px; color: #525252; margin: 8px 0; }
.budget-statistics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 15px 0 8px; }
.budget-statistics dt { color: #737373; font-size: 10px; margin-bottom: 4px; }
.budget-statistics dd { font-size: 12px; margin: 0; overflow-wrap: anywhere; }
.budget-state { font-size: 10px; line-height: 1.8; color: #8c7050; padding: 8px; background: #fdfbf7; border: 1px solid #e4d6c4; overflow-wrap: anywhere; }
.budget-cap-form { border-top: 1px solid #e5e5e5; margin-top: 12px; padding-top: 12px; }
.budget-cap-form > label { display: block; color: #525252; font-size: 11px; margin-bottom: 7px; }
.budget-cap-input { display: flex; gap: 7px; }
.budget-cap-input input, .budget-cap-input select { min-width: 0; padding: 6px 8px; border: 1px solid #d4d4d4; border-radius: 3px; background: white; font: inherit; }
.budget-cap-input input { width: 0; flex: 1; }
.budget-cap-input input:disabled, .budget-cap-input select:disabled { background: #fafafa; color: #737373; }
.budget-cap-input button { font-size: 11px; }
.budget-receipt { border-top: 1px solid #e5e5e5; margin-top: 15px; padding-top: 12px; color: #525252; font-size: 10px; line-height: 1.8; }
.budget-receipt h3 { flex-wrap: wrap; font-size: 11px; margin-bottom: 5px; }
.budget-receipt p { margin: 5px 0; overflow-wrap: anywhere; }
.budget-receipt summary { cursor: pointer; }
.gui-diagnostics { margin-top: 18px; border-top: 1px solid #e5e5e5; padding-top: 15px; }
.gui-diagnostics > .section-caption { align-items: flex-start; }
.gui-diagnostics > .section-caption button { font-size: 11px; flex-shrink: 0; }
.gui-instance { font-size: 10px; color: #525252; margin: 12px 0; }
.gui-instance > div { display: flex; gap: 12px; margin-top: 6px; }
.gui-instance dt { flex: 0 0 118px; color: #737373; }
.gui-instance dd { margin: 0; min-width: 0; overflow-wrap: anywhere; }
.gui-issue { font-size: 10px; line-height: 1.8; color: #404040; background: #f5f5f5; border: 1px solid #d4d4d4; padding: 8px 9px; margin: 8px 0; overflow-wrap: anywhere; }
.gui-issue strong { display: block; margin-bottom: 3px; }
.gui-recovery { border: 1px solid #d4d4d4; padding: 10px; margin: 10px 0; background: #fafafa; }
.gui-recovery p { font-size: 11px; color: #525252; line-height: 1.8; margin: 0 0 8px; }
.gui-recovery button { font-size: 11px; }
.gui-package-filter { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; font-size: 10px; color: #737373; margin: 15px 0 8px; }
.gui-package-filter label { display: inline-flex; align-items: center; gap: 4px; cursor: pointer; }
.gui-package-filter input { margin: 0; accent-color: #525252; }
.gui-package { border: 1px solid #e5e5e5; border-radius: 3px; padding: 10px; margin: 8px 0; }
.gui-package-heading { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
.gui-package-heading > div { display: flex; align-items: baseline; flex-wrap: wrap; gap: 7px; min-width: 0; }
.gui-package-heading strong { font-size: 11px; font-weight: 500; overflow-wrap: anywhere; }
.gui-package-heading span { color: #737373; font-size: 10px; }
.gui-package-heading button { font-size: 10px; padding: 5px 8px; }
.gui-file-details { margin-top: 8px; font-size: 10px; color: #525252; }
.gui-file-details summary { cursor: pointer; }
.gui-file-details pre, .gui-paths { font: 10px/1.75 Consolas, "Microsoft YaHei", monospace; white-space: pre-wrap; overflow-wrap: anywhere; max-height: 145px; overflow: auto; background: #fafafa; border: 1px solid #e5e5e5; padding: 8px; scrollbar-width: thin; }
.gui-preview { border: 1px solid #b5b5b5; padding: 12px; margin: 15px 0 10px; border-radius: 3px; }
.gui-preview > p { color: #525252; font-size: 11px; line-height: 1.8; }
.gui-preview > button { margin-top: 5px; font-size: 11px; }
.gui-confirmation { width: 560px; max-height: calc(100vh - 48px); overflow: auto; }
.gui-confirmation > p { margin-bottom: 10px; font-size: 11px; }
.gui-confirmation .gui-paths { max-height: min(180px, 30vh); margin-bottom: 16px; }
</style>
