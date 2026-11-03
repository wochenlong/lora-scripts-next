<script setup lang="ts">
import AcrylicSelect from './AcrylicSelect.vue'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowReactive, shallowRef, watch } from 'vue'
import { getCurrentWindow } from '@tauri-apps/api/window'
import { getVersion } from '@tauri-apps/api/app'
import { invoke } from '@tauri-apps/api/core'
import { runtimeStatus, listenToRuntime, startTrainer, installationSnapshot, resumeLegacyInstall, repairLegacyEnvironment, recoverLegacyEnvironment } from './bridge'
import type { InstallationSnapshot, InstallationVersionView, SourceRepairPreview, LegacyEnvironmentRepairPlan } from './bridge'
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
import { formatBytes as formatFileSize } from './localized-bytes'
import { previewGuiRegistration, restoreGuiRegistration, recoverGuiRegistration } from './bridge'
import type { GuiRegistrationPreview } from './bridge'

import { previewGuiLifecycle, guiLifecycleHistory, applyGuiLifecycle } from './bridge'
import type { GuiLifecyclePreview, GuiLifecycleHistory, GuiLifecycleAction } from './bridge'
import EnginePanel from './EnginePanel.vue'
import TrustPanel from './TrustPanel.vue'
import ImportPanel from './ImportPanel.vue'
import ShellPanel from './ShellPanel.vue'
import MainReinstallDialog from './MainReinstallDialog.vue'
import { beginEngineQuery, cancelEngineQuery, cancelEngineQueryTarget, invalidateEngineQueryResults, queryStageLabel, sameEngineQueryIdentity, waitEngineQuery } from './engine-query'
import type { EngineQueryEntry, EngineQueryIdentity, EngineQueryTarget } from './engine-query'
import { locale, t } from './i18n'
import type { LauncherLocale } from './i18n'

type Page = 'launch' | 'versions' | 'environment' | 'logs' | 'settings'
type Setting = 'general' | 'appearance' | 'network' | 'profiles' | 'security' | 'about'
interface Confirmation {
  title: string
  detail: string
  action: string
  destructive?: boolean
  scope?: 'gui'
  paths?: string[]
  actionId?: string
  execute: () => Promise<void>
}
type DisplayVersion = Omit<VersionView, 'source_ok' | 'environment_ok'> & {
  source_ok?: boolean
  environment_ok?: boolean
  structure?: InstallationVersionView['structure']
}
interface MainRepairPlan {
  root: string
  releaseId: string
  source: SourceRepairPreview | null
  base: BasePythonRepairPreview | null
  package: PackageIntegrity | null
}
interface MainReinstallRequest {
  kind: 'rebuild' | 'legacy-repair'
  epoch: number
  root: string
  releaseId: string
  version: string
  selectedInstance: string
  observedBinding: string
  phase: 'preparing' | 'ready' | 'blocked' | 'error' | 'cancelled'
  reason: string
  invalidated: boolean
  cancelled: boolean
  queryTarget: EngineQueryTarget | null
  query: EngineQueryEntry | null
  identity: EngineQueryIdentity | null
  preview: GuiLifecyclePreview | null
  legacyPlan: LegacyEnvironmentRepairPlan | null
}

const page = ref<Page>('launch')
const path = ref(localStorage.getItem('next-trainer-launcher-root') ?? localStorage.getItem('launcher-probe-root') ?? '')
const report = ref<Report | null>(null)
const inventory = ref<InstallationSnapshot | null>(null)
const inventoryLoading = ref(false)
let inventoryEpoch = 0
let acceptingRoot = false
let inventoryTimer: ReturnType<typeof setTimeout> | undefined
const mainRepairPlan = ref<MainRepairPlan | null>(null)
const mainCheckResult = ref<'unchecked' | 'healthy' | 'repair' | 'advanced' | 'unsupported'>('unchecked')
const mainCheckSummary = ref('')
const repairSequenceRunning = ref(false)
const pending = ref('')
const error = ref('')
const message = ref(t('正在检查安装状态…'))
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
const setting = ref<Setting>('general')
const closeToTray = ref(true)
const preferencesLoaded = ref(false)
const preferencesSaving = ref(false)
const preferencesError = ref('')
interface LauncherPreferences { close_to_tray: boolean; language: LauncherLocale }
function acceptPreferences(value: LauncherPreferences) {
  closeToTray.value = value.close_to_tray
  locale.value = value.language === 'en-US' ? 'en-US' : 'zh-CN'
}
async function readLauncherPreferences() {
  try {
    acceptPreferences(await invoke<LauncherPreferences>('load_launcher_preferences'))
    preferencesLoaded.value = true
    preferencesError.value = ''
  } catch (reason) {
    preferencesError.value = errorText(reason)
  }
}
async function updateLauncherPreference(key: 'close_to_tray' | 'language', value: boolean | string) {
  if (preferencesSaving.value) return
  preferencesSaving.value = true
  preferencesError.value = ''
  const previous = { close_to_tray: closeToTray.value, language: locale.value }
  const preferences = { ...previous, [key]: value } as LauncherPreferences
  // Apply the language immediately; a failed write restores the persisted selection.
  acceptPreferences(preferences)
  try {
    acceptPreferences(await invoke<LauncherPreferences>('save_launcher_preferences', { preferences }))
    preferencesLoaded.value = true
  } catch (reason) {
    acceptPreferences(previous)
    preferencesError.value = errorText(reason)
  } finally { preferencesSaving.value = false }
}
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
const mainReinstall = shallowRef<MainReinstallRequest | null>(null)
let mainReinstallReturnFocus: HTMLElement | null = null
const operation = ref<OperationSnapshot | null>(null)
const engineOperationId = ref<string | null>(null)
const startingEngineOperation = ref(false)
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
let operationEventRequest: { id: string; root: string } | null = null
let unlisten: (() => void) | undefined
let previousFocus: HTMLElement | null = null

const sameRoot = computed(() => Boolean((report.value && samePath(path.value, report.value.root)) || (inventory.value && samePath(path.value, inventory.value.root))))
const versions = computed<DisplayVersion[]>(() => report.value && samePath(path.value, report.value.root) ? report.value.versions : inventory.value && samePath(path.value, inventory.value.root) ? inventory.value.versions : [])
const currentReleaseId = computed(() => report.value ? report.value.current_release : inventory.value?.current_release)
const previousReleaseId = computed(() => report.value ? report.value.previous_known_good : inventory.value?.previous_known_good)
const profilePath = computed(() => report.value?.profile_path ?? inventory.value?.profile_path ?? '')
const currentVersion = computed(() => versions.value.find((version) => version.id === currentReleaseId.value) ?? versions.value.find((version) => version.current))
const pendingLegacyVersions = computed(() => versions.value.filter(version => version.legacy_recovery))
const defaultRelease = computed(() => versions.value.find(version => version.channel === 'dev' && installSupported(version)) ?? versions.value.find(installSupported) ?? versions.value[0])
const installTarget = computed(() => currentVersion.value ?? defaultRelease.value)
function sourceSupported(version: DisplayVersion) { return version.source_supported !== false }
function maintenanceSupported(version: DisplayVersion) { return Boolean(version.managed_recipe && version.maintenance_supported !== false) }
function installSupported(version: DisplayVersion) { return version.install_supported !== false }
const currentSourceUnsupported = computed(() => Boolean(sameRoot.value && currentVersion.value && !sourceSupported(currentVersion.value)))
const currentMaintenanceUnsupported = computed(() => Boolean(sameRoot.value && currentVersion.value?.managed_recipe && !maintenanceSupported(currentVersion.value)))
const needsVersionManagement = computed(() => currentSourceUnsupported.value || currentMaintenanceUnsupported.value)
const titlebarVersion = computed(() => {
  const version = currentVersion.value ?? installTarget.value
  return version ? `${version.version} · ${channelName(version.channel)}` : t('启动器 {value0}', { value0: appVersion.value })
})
const rollbackVersion = computed(() => versions.value.find((version) => version.id === previousReleaseId.value))
const ready = computed(() => Boolean(sameRoot.value && report.value?.uv && report.value?.python && report.value?.source && report.value?.environment && report.value?.frontend))
const busy = computed(() => Boolean(pending.value) || operation.value?.status === 'running')
const phaseText = computed<Record<OperationSnapshot['phase'], string>>(() => ({ preparing: t('准备中'), downloading: t('正在下载'), executing: t('正在执行'), verifying: t('正在校验'), committing: t('正在保存'), recovering: t('正在恢复') }))
const operationStatusText = computed<Record<OperationSnapshot['status'], string>>(() => ({ running: t('进行中'), succeeded: t('已完成'), failed: t('失败'), cancelled: t('已取消'), interrupted: t('上次操作未完整结束') }))
const runtimePhase = computed<RuntimePhase>(() => optimisticPhase.value ?? (samePath(runtime.value?.root ?? '', path.value) ? runtime.value?.phase : null) ?? (sameRoot.value && report.value?.healthy ? 'ready' : sameRoot.value && report.value?.running ? 'degraded' : 'stopped'))
const healthy = computed(() => runtimePhase.value === 'ready')
const transitioning = computed(() => ['checking', 'starting', 'stopping'].includes(runtimePhase.value))
const running = computed(() => ['starting', 'ready', 'degraded', 'stopping', 'stop_failed'].includes(runtimePhase.value))
const serviceUrl = computed(() => healthy.value ? runtime.value?.url ?? (report.value?.port ? `http://127.0.0.1:${report.value.port}` : '') : '')
const mutationDisabled = computed(() => busy.value || !sameRoot.value || running.value || transitioning.value || Boolean(serviceAction.value))
const engineMutationDisabled = computed(() => busy.value || !sameRoot.value)
const engineReadDisabled = computed(() => !sameRoot.value || (busy.value && !startingEngineOperation.value && !(operation.value?.status === 'running' && operation.value.id === engineOperationId.value)))
const installed = computed(() => Boolean(currentVersion.value?.installed || report.value?.source))
const rollbackAvailable = computed(() => Boolean(rollbackVersion.value?.installed && rollbackVersion.value.id !== currentVersion.value?.id))
const startAvailable = computed(() => sameRoot.value && (report.value ? ready.value : inventory.value?.start_available === true))
const mainInstallationMissing = computed(() => {
  if (!sameRoot.value) return false
  if (!currentVersion.value?.installed) return true
  const structural = inventory.value?.versions.find(version => version.id === currentVersion.value?.id)
  return Boolean(structural && !structural.environment_present && structural.environment_bound === false && !report.value)
})
const channels = computed(() => {
  const listed = ['main', 'dev', ...versions.value.map((version) => version.channel)]
  return [...new Set(listed)].map((channel) => ({ channel, versions: versions.value.filter((version) => version.channel === channel) }))
})
const runtimeLabels = computed<Record<RuntimePhase, string>>(() => ({ stopped: t('服务已停止'), checking: t('正在检查启动条件'), starting: t('正在启动，等待服务'), ready: t('服务已就绪'), degraded: t('进程运行，服务暂不可达'), stopping: t('正在停止服务'), exited: t('服务已退出'), start_failed: t('启动失败'), stop_failed: t('停止失败，请查看日志') }))
const stateText = computed(() => {
  if (transitioning.value || running.value || ['exited', 'start_failed', 'stop_failed'].includes(runtimePhase.value)) return runtimeLabels.value[runtimePhase.value]
  if (inventoryLoading.value) return t('正在读取安装信息…')
  if (!report.value && !inventory.value) return t('等待检查')
  if (!sameRoot.value) return t('目录待检查')
  if (ready.value) return t('可以启动')
  if (!report.value && startAvailable.value) return t('已安装，完整性未检查')
  if (currentSourceUnsupported.value) return t('本包未提供校验清单')
  if (currentMaintenanceUnsupported.value) return t('请管理版本')
  return installed.value ? t('需要修复') : t('尚未安装')
})
const stateGood = computed(() => sameRoot.value && (healthy.value || (ready.value && !transitioning.value)))
const primaryLabel = computed(() => {
  if (!sameRoot.value) return t('读取安装信息')
  if ((!startAvailable.value && needsVersionManagement.value) || (!installed.value && installTarget.value && !installSupported(installTarget.value))) return t('管理版本')
  if (!installed.value) return t('安装训练器')
  if (!startAvailable.value) return t('检查并修复')
  return t('启动训练器')
})
const primaryDisabled = computed(() => busy.value || running.value || transitioning.value || Boolean(serviceAction.value) || (sameRoot.value && !installed.value && !installTarget.value))
const managedCurrent = computed(() => Boolean(sameRoot.value && currentVersion.value && maintenanceSupported(currentVersion.value)))
const registrationVersions = computed(() => versions.value.filter(maintenanceSupported))
const registrationRelease = computed(() => registrationVersions.value.find((version) => version.id === registrationReleaseId.value)
  ?? (currentVersion.value && maintenanceSupported(currentVersion.value) ? currentVersion.value : registrationVersions.value[0]))
const activeManagedRelease = computed(() => currentVersion.value?.managed_recipe ? currentVersion.value : registrationRelease.value)
const guiRecoveryNeeded = computed(() => Boolean(guiDiagnosis.value?.dirty || guiDiagnosis.value?.recovery_pending || (guiDiagnosis.value && guiDiagnosis.value.generation !== guiDiagnosis.value.binding_generation)))
const affectedPackages = computed(() => guiDiagnosis.value?.integrity.packages.filter(packageNeedsAttention) ?? [])
const visiblePackages = computed(() => showAllPackages.value ? guiDiagnosis.value?.integrity.packages ?? [] : affectedPackages.value)
const guiPlanBlocked = computed(() => Boolean(guiRecoveryNeeded.value || guiDiagnosis.value?.source_error || guiDiagnosis.value?.installed_metadata_error))

watch([path, () => currentVersion.value?.id], clearGuiState, { flush: 'sync' })
watch([
  () => registrationRelease.value?.id, registrationInstanceId,
  () => runtime.value?.instance_id, () => runtime.value?.binding_generation,
  () => guiDiagnosis.value?.instance_id, () => guiDiagnosis.value?.generation,
  () => mainReinstall.value?.query?.invalidated,
  () => mainReinstall.value?.query?.snapshot?.validity,
  () => mainReinstall.value?.query?.snapshot?.identity,
  mutationDisabled,
], () => {
  const request = mainReinstall.value
  if (request && (mutationDisabled.value || !mainReinstallContextCurrent(request) || request.query?.invalidated || request.query?.snapshot?.validity === 'stale')) invalidateMainReinstall()
}, { flush: 'sync' })
watch(path, () => {
  runtime.value = null; optimisticPhase.value = null; serviceEpoch += 1; serviceAction.value = ''; requestedRunId.value = null
  networkView.value = null; networkInherit.value = []; networkDraft.value = { mode: 'auto', http_proxy: '', https_proxy: '', no_proxy: '' }
  if (!acceptingRoot) {
    inventoryEpoch += 1; report.value = null; inventory.value = null
    if (inventoryTimer) clearTimeout(inventoryTimer)
    inventoryTimer = setTimeout(() => { void refreshInstallation() }, 250)
  }
  void syncRuntime()
}, { flush: 'sync' })
function acceptNetworkSettings(view: NetworkSettingsView) {
  networkView.value = view
  networkInherit.value = []
  networkDraft.value = { mode: view.settings.mode ?? 'auto', http_proxy: view.settings.http_proxy ?? '', https_proxy: view.settings.https_proxy ?? '', no_proxy: view.settings.no_proxy ?? '' }
}
async function readNetworkSettings() {
  const root = path.value.trim()
  await perform(t('读取网络设置'), async () => {
    const view = await loadNetworkSettings(root)
    if (path.value.trim() === root) acceptNetworkSettings(view)
  })
}
async function storeNetworkSettings() {
  const root = path.value.trim()
  if (!networkView.value) return
  const settings = settingsForSave(networkView.value.settings, networkDraft.value, networkInherit.value)
  await perform(t('保存网络设置'), async () => {
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
  invalidateMainReinstall()
  guiDiagnosis.value = null
  guiPreview.value = null
  basePythonPreview.value = null
  registrationPreview.value = null
  registrationInstanceId.value = ''
  lifecyclePreview.value = null
  lifecycleHistory.value = null
  lifecycleTransaction.value = ''
  showAllPackages.value = false
  mainRepairPlan.value = null
  mainCheckResult.value = 'unchecked'
  mainCheckSummary.value = ''
  if (confirmation.value?.scope === 'gui') dismissConfirmation()
}
function packageNeedsAttention(item: PackageIntegrity) {
  return item.status !== 'verified_original_files' || item.issues.length > 0 || item.generated.some((file) => file.kind === 'optional_derived_bytecode_unverified' && file.present)
}
function packageStatus(item: PackageIntegrity) {
  if (item.generated.some((file) => file.kind === 'optional_derived_bytecode_unverified' && file.present)) return t('存在未验证字节码')
  return ({ verified_original_files: t('原文件通过'), missing: t('文件缺失'), damaged: t('内容改变'), unsupported: t('需要进一步诊断') })[item.status] ?? t('待检查')
}
function packagePlanDisabled(item: PackageIntegrity) {
  return mutationDisabled.value || guiPlanBlocked.value || item.unsupported.length > 0 || item.issues.length > 0
    || item.generated.some((file) => file.kind === 'optional_derived_bytecode_unverified' && file.present)
    || item.generated.some((file) => file.kind === 'rewritten_record' && (!file.present || item.damaged.includes(file.path)))
}

function formatBytes(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) return t('未提供')
  const units = ['B', 'KiB', 'MiB', 'GiB', 'TiB']
  let value = bytes
  let index = 0
  while (value >= 1024 && index < units.length - 1) { value /= 1024; index += 1 }
  return `${value.toFixed(index > 0 ? 1 : 0)} ${units[index]}`
}
function channelName(channel: string) {
  if (channel === 'main') return t('main（稳定线）')
  if (channel === 'dev') return t('dev（开发线）')
  return channel
}
function releaseState(version: DisplayVersion) {
  if (!version.installed) return t('未安装')
  if (!sourceSupported(version)) return t('本包未提供校验清单')
  if (version.source_ok === undefined || version.environment_ok === undefined) return version.structure === 'attention' ? t('安装信息需处理') : t('已安装，完整性未检查')
  if (!version.source_ok) return t('源码需修复')
  if (!version.environment_ok) return t('环境需修复')
  return t('检查通过')
}
function protectedRelease(version: DisplayVersion) {
  return version.current || version.id === currentReleaseId.value || version.id === previousReleaseId.value
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
    addLog(t('[信息] {value0}{value1}', { value0: runtimeLabels.value[value.phase], value1: value.url ? ` · ${value.url}` : '' }), 'launcher')
    if (!busy.value) message.value = runtimeLabels.value[value.phase]
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
/** Opening the window and changing directories never execute a full inspection. */
async function refreshInstallation(root = path.value.trim()) {
  const epoch = ++inventoryEpoch
  inventoryLoading.value = true
  try {
    const value = await installationSnapshot(root)
    if (disposed || epoch !== inventoryEpoch) return
    acceptingRoot = true
    try { path.value = value.root } finally { acceptingRoot = false }
    report.value = null
    inventory.value = value
    localStorage.setItem('next-trainer-launcher-root', value.root)
    error.value = value.workspace === 'invalid' ? value.issues.map(issue => issue.message).join('\n') : ''
    message.value = t('安装信息已读取；完整检查将在启动或手动检查时执行。')
    void syncRuntime()
  } catch (reason) { if (epoch === inventoryEpoch) error.value = errorText(reason) }
  finally { if (epoch === inventoryEpoch) inventoryLoading.value = false }
}
function acceptReport(value: Report) {
  // A late inventory must never replace a newer complete check or its repair plan.
  inventoryEpoch += 1
  inventoryLoading.value = false
  if (inventoryTimer) clearTimeout(inventoryTimer)
  const rootChanged = report.value?.root !== value.root
  report.value = { ...value, versions: value.versions ?? [], interrupted: value.interrupted ?? [] }
  acceptingRoot = true
  try { path.value = value.root } finally { acceptingRoot = false }
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
async function refreshOperationEvents(next: OperationSnapshot, root: string) {
  if (operationEventRequest?.id === next.id && operationEventRequest.root === root) return
  const request = { id: next.id, root }
  operationEventRequest = request
  const stillCurrent = () => !disposed && operation.value?.id === next.id && path.value.trim() === root
  try {
    const events = await operationEvents(next.id, operationCursor)
    if (!stillCurrent()) return
    events.forEach((event) => { addLog(event.message, 'environment'); operationCursor = Math.max(operationCursor, event.seq) })
  } catch (reason) {
    if (!stillCurrent()) return
    if (errorText(reason).includes('事件游标已过期')) {
      operationCursor = Math.max(operationCursor, next.event_seq)
      addLog(t('部分较早事件已过期，已重新读取完整状态。'))
    } else if (!operation.value?.error) error.value = errorText(reason)
  } finally {
    if (operationEventRequest === request) operationEventRequest = null
  }
}
async function pollOperation() {
  const current = operation.value
  if (!current || disposed) return
  const root = path.value.trim()
  const stillCurrent = () => !disposed && operation.value?.id === current.id && path.value.trim() === root
  try {
    const next = await operationSnapshot(current.id)
    if (!stillCurrent()) return
    // 状态先绘制；日志读取延迟或失败不阻挡阶段变化与终态按钮。
    operation.value = next
    message.value = `${phaseText.value[next.phase]} · ${operationStatusText.value[next.status]}`
    if (next.error) error.value = next.error.message
    void refreshOperationEvents(next, root)
    if (next.status !== 'running') {
      clearGuiState()
      await refreshHistory()
      if (next.kind !== 'download' && stillCurrent()) await refreshInstallation(root)
      return
    }
  } catch (reason) { if (stillCurrent()) error.value = errorText(reason) }
  if (stillCurrent() && operation.value?.status === 'running') operationTimer = setTimeout(() => { void pollOperation() }, 250)
}

async function prefetch(version: DisplayVersion, install = false) {
  if (!installSupported(version)) { notify(t('本启动器未提供此版本的安装配方，请安装受支持的新版本。')); page.value = 'versions'; return }
  if (busy.value) return
  pending.value = t('准备下载')
  error.value = ''
  try {
    operation.value = await (install ? installManagedRelease(path.value.trim(), version.id) : prefetchRelease(path.value.trim(), version.id))
    operationCursor = 0
    message.value = install ? t('正在安装主程序') : t('正在准备安装文件')
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
    message.value = receipt === 'commit_in_progress' ? t('正在保存操作结果，请等待本次保存完成。') : receipt === 'already_finished' ? t('本次操作已经结束，正在刷新状态。') : t('已请求取消，正在等待任务结束与必要的恢复校验…')
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
  try { await action(); message.value = t('{value0}完成', { value0: label }) }
  catch (reason) {
    error.value = errorText(reason)
    message.value = t('{value0}失败，可查看日志后重试', { value0: label })
    addLog(t('[失败] {value0}', { value0: error.value }), 'launcher')
  } finally { pending.value = '' }
}
async function command(command: ReportCommand, label: string) {
  if (command !== 'inspect' && needsVersionManagement.value) { page.value = 'versions'; notify(t('本启动器未提供此版本的精准修复配方。')); return }
  return perform(label, async () => acceptReport(await runCommand(command, path.value.trim())))
}
async function releaseCommand(command: ReleaseCommand, version: DisplayVersion, label: string) {
  if (command === 'install_release' && !installSupported(version)) { page.value = 'versions'; notify(t('本启动器未提供此版本的安装配方，请安装受支持的新版本。')); return }
  return perform(label, async () => acceptReport(await runReleaseCommand(command, path.value.trim(), version.id)))
}
async function ask(value: Confirmation, returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null) {
  previousFocus = returnFocus
  confirmation.value = value
  await nextTick()
  confirmationCancel.value?.focus()
}
function dismissConfirmation() {
  const returnFocus = previousFocus
  confirmation.value = null
  previousFocus = null
  void nextTick(() => {
    if (!confirmation.value && returnFocus?.isConnected && !returnFocus.matches(':disabled')) returnFocus.focus({ preventScroll: true })
  })
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
function install(version: DisplayVersion) {
  if (!installSupported(version)) { page.value = 'versions'; notify(t('本启动器未提供此版本的安装配方，请安装受支持的新版本。')); return }
  if (version.managed_recipe) return prefetch(version, true)
  return releaseCommand('install_release', version, t('安装 {value0} {value1}', { value0: channelName(version.channel), value1: version.version }))
}
function resumeInstallation(version: DisplayVersion) {
  const recovery = version.legacy_recovery
  if (!recovery || mutationDisabled.value) return
  const root = path.value.trim()
  const journalSha256 = recovery.journal_sha256
  return ask({
    title: t('检查并完成安装'),
    detail: t('将验证此版本已有的源码、基础 Python 和依赖。全部通过后完成上次安装记录；不会下载、重装或切换版本。检查失败时保留现场，供进一步处理。'),
    action: t('开始检查'),
    execute: async () => {
      if (root !== path.value.trim() || versions.value.find(item => item.id === version.id)?.legacy_recovery?.journal_sha256 !== journalSha256) {
        error.value = t('安装记录已变化，请刷新后重试。')
        return
      }
      await startGuiOperation(t('正在检查未完成安装'), () => resumeLegacyInstall(root, version.id, journalSha256))
    },
  })
}
async function prepareLegacyEnvironment(version: DisplayVersion) {
  if (!version.legacy_recovery || version.legacy_environment_repair || mutationDisabled.value || mainReinstall.value) return
  const request = shallowReactive<MainReinstallRequest>({
    kind: 'legacy-repair', epoch: guiEpoch, root: path.value.trim(), releaseId: version.id,
    version: `${version.version} · ${version.commit.slice(0, 8)}`, selectedInstance: '',
    observedBinding: version.legacy_recovery.journal_sha256, phase: 'preparing', reason: '',
    invalidated: false, cancelled: false, queryTarget: null, query: null, identity: null, preview: null, legacyPlan: null,
  })
  mainReinstallReturnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
  mainReinstall.value = request
  error.value = ''
  await nextTick()
  try {
    if (request.cancelled || request.invalidated || mainReinstall.value !== request) return
    request.queryTarget = { root: request.root, release_id: request.releaseId, engine_id: 'gui', action: 'preview_legacy_environment_repair', rebuild: false, scope: 'plan' }
    const query = await beginEngineQuery(request.queryTarget)
    request.query = query
    if (disposed || request.cancelled || request.invalidated || mainReinstall.value !== request) { await cancelEngineQuery(query); return }
    const { result: plan, snapshot } = await waitEngineQuery<LegacyEnvironmentRepairPlan>(query)
    if (disposed || request.cancelled || request.invalidated || mainReinstall.value !== request) return
    if (!mainReinstallContextCurrent(request)) { invalidateMainReinstall(); return }
    if (![1, 2].includes(plan.schema_version) || plan.operation !== 'independent_legacy_environment_repair' || !samePath(plan.root, request.root) || plan.release_id !== request.releaseId || plan.journal_sha256 !== request.observedBinding || !/^[0-9a-f]{64}$/.test(plan.plan_sha256)) throw Error(t('安装计划不完整，请关闭后重试。'))
    request.identity = snapshot.identity
    request.legacyPlan = plan
    request.phase = plan.ready ? 'ready' : 'blocked'
    request.reason = plan.blockers.join('\n')
  } catch (reason) {
    if (!request.query) request.queryTarget = null
    if (disposed || request.cancelled || request.invalidated || mainReinstall.value !== request) return
    request.phase = request.query?.snapshot?.status === 'cancelled' ? 'cancelled' : 'error'
    request.reason = errorText(reason)
  }
}
function recoverLegacyRepair(version: DisplayVersion) {
  const transaction = version.legacy_environment_repair
  if (!transaction || mutationDisabled.value) return
  const root = path.value.trim()
  return ask({ title: t('恢复环境修复'), detail: t('先确认上次修复进程已退出，再验证并恢复原环境。原安装记录与当前版本保持不变。'), action: t('确认恢复'),
    execute: async () => {
      if (!samePath(root, path.value) || versions.value.find(item => item.id === version.id)?.legacy_environment_repair !== transaction) throw Error(t('安装记录已变化，请刷新后重试。'))
      await startGuiOperation(t('正在恢复运行环境'), () => recoverLegacyEnvironment(root, version.id, transaction))
    },
  })
}
function select(version: DisplayVersion) {
  if (version.channel === 'dev') return ask({
    title: t('切换到 dev 开发线'),
    detail: t('将切换到 {value0}（{value1}）。开发线可能包含尚未稳定的改动，训练任务与插件的兼容性需要自行确认。当前版本会保留，上一已健康版本可用于回退。', { value0: version.version, value1: version.commit.slice(0, 8) }),
    action: t('确认切换到 dev'),
    execute: () => releaseCommand('select_release', version, t('切换到 dev 开发线')),
  })
  return releaseCommand('select_release', version, t('切换到 {value0}', { value0: channelName(version.channel) }))
}
function remove(version: DisplayVersion) {
  return ask({
    title: t('删除已安装版本'),
    detail: t('将删除 {value0} {value1}（{value2}）的受管版本目录。共享用户资料目录 {value3} 会保留。之后使用此版本需要重新安装。', { value0: channelName(version.channel), value1: version.version, value2: version.commit.slice(0, 8), value3: profilePath.value }),
    action: t('删除此版本'),
    destructive: true,
    execute: () => releaseCommand('remove_release', version, t('删除已安装版本')),
  })
}
function rollback() {
  if (!rollbackVersion.value) return
  return perform(t('回退到上一已健康版本'), async () => acceptReport(await rollbackRelease(path.value.trim())))
}
function primary() {
  if (!sameRoot.value) return refreshInstallation()
  if ((!startAvailable.value && needsVersionManagement.value) || (!installed.value && installTarget.value && !installSupported(installTarget.value))) { page.value = 'versions'; return }
  if (!installed.value && installTarget.value) return install(installTarget.value)
  if (!startAvailable.value) { page.value = 'environment'; return checkAndRepairMain() }
  return start()
}
function browse() {
  return perform(t('选择目录'), async () => {
    const selected = await chooseDirectory()
    if (selected) await refreshInstallation(selected)
  })
}
async function start() {
  if (primaryDisabled.value) return
  const epoch = ++serviceEpoch, root = path.value.trim(), runId = `start-${crypto.randomUUID()}`
  requestedRunId.value = runId
  serviceAction.value = 'start'; optimisticPhase.value = 'checking'; error.value = ''; message.value = t('正在检查启动条件…')
  try {
    const value = await startTrainer(root, runId)
    if (epoch === serviceEpoch && samePath(root, path.value)) { acceptReport(value); await syncRuntime() }
  } catch (reason) {
    if (epoch === serviceEpoch && samePath(root, path.value)) { error.value = errorText(reason); optimisticPhase.value = 'start_failed'; addLog(t('[失败] {value0}', { value0: error.value }), 'launcher'); await syncRuntime() }
  } finally { if (epoch === serviceEpoch) serviceAction.value = '' }
}
async function stop() {
  if (runtimePhase.value === 'stopping' || serviceAction.value === 'stop') return
  const epoch = ++serviceEpoch, root = path.value.trim()
  serviceAction.value = 'stop'; optimisticPhase.value = 'stopping'; error.value = ''; message.value = t('正在停止服务并回收进程…')
  try {
    const value = await stopTrainer(requestedRunId.value ?? runtime.value?.run_id ?? null)
    if (epoch === serviceEpoch && samePath(root, path.value)) {
      acceptRuntime(value)
      // The start report only verifies the active version. Restore the lightweight
      // inventory so inactive versions are not treated as failed checks after stop.
      void refreshInstallation(root)
    }
  }
  catch (reason) { if (epoch === serviceEpoch) { error.value = errorText(reason); optimisticPhase.value = 'stop_failed'; addLog(t('[失败] {value0}', { value0: error.value }), 'launcher'); await syncRuntime() } }
  finally { if (epoch === serviceEpoch) { serviceAction.value = ''; requestedRunId.value = null } }
}
async function open() {
  try { await openTrainer() } catch (reason) { error.value = errorText(reason); addLog(t('[失败] {value0}', { value0: error.value }), 'launcher'); await syncRuntime() }
}
async function openProjectLink(target: 'project' | 'releases' | 'blog' | 'bilibili' | 'modelscope' | 'issues' | 'license') { try { await invoke('open_project_link', { target }) } catch (reason) { notify(errorText(reason)) } }
async function copyAddress() { try { await navigator.clipboard.writeText(serviceUrl.value); notify(t('已复制服务地址')) } catch { notify(t('复制失败，请在日志中选择地址复制')) } }
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
  catch { notify(t('外观设置未保存：本地存储空间不足，请换用较小的背景图片。')) }
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
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 8 * 1024 * 1024) { notify(t('请选择 8 MiB 以内的 PNG、JPEG 或 WebP 图片')); input.value = ''; return }
  try {
    const bitmap = await createImageBitmap(file)
    const ratio = Math.min(1, 1920 / bitmap.width, 1080 / bitmap.height)
    const canvas = document.createElement('canvas'); canvas.width = Math.round(bitmap.width * ratio); canvas.height = Math.round(bitmap.height * ratio)
    canvas.getContext('2d')?.drawImage(bitmap, 0, 0, canvas.width, canvas.height); bitmap.close()
    const background = canvas.toDataURL('image/webp', .86)
    // 先确保存储成功，再应用；重启后不会突然丢失背景。
    localStorage.setItem('next-trainer-launcher-appearance', JSON.stringify({ ...appearance.value, background }))
    appearance.value.background = background; notify(t('已应用本地背景'))
  } catch { notify(t('无法读取或保存这张图片，请选择较小的有效图片。')) }
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

function needsAdvancedMainRepair(summary = t('这次无法只修复损坏部分，可重新安装主程序环境。')) {
  mainRepairPlan.value = null
  mainCheckResult.value = 'advanced'
  mainCheckSummary.value = summary
}
async function checkAndRepairMain() {
  if (busy.value || transitioning.value || serviceAction.value || !sameRoot.value) return
  if (pendingLegacyVersions.value.length) {
    page.value = 'versions'
    notify(t('有未完成的历史安装，请在版本管理中检查并完成安装。'))
    return
  }
  const returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
  if (mainInstallationMissing.value) {
    const target = installTarget.value
    if (target) await install(target)
    return
  }
  clearGuiState()
  const root = path.value.trim()
  await perform(t('正在检查主程序'), async () => {
    const inspected = await runCommand('inspect', root)
    if (!samePath(root, path.value)) return
    acceptReport(inspected)
    if (ready.value) {
      mainCheckResult.value = 'healthy'
      mainCheckSummary.value = t('主程序检查正常，无需修复。')
      return
    }
    const version = currentVersion.value
    if (!version || !maintenanceSupported(version)) {
      mainCheckResult.value = 'unsupported'
      mainCheckSummary.value = t('本启动器未提供此版本的精准修复配方。需要修复时，请在版本管理安装受支持的新版本，确认后切换。当前版本和资料会保留。')
      return
    }
    const plan: MainRepairPlan = { root, releaseId: version.id, source: null, base: null, package: null }
    const epoch = guiEpoch
    const current = () => epoch === guiEpoch && samePath(root, path.value) && version.id === currentVersion.value?.id
    if (!inspected.source || !inspected.frontend) {
      pending.value = t('正在检查主程序文件')
      plan.source = await previewSourceRepair(root, version.id)
      if (!current()) return
    }
    if (!inspected.python) {
      pending.value = t('正在检查基础 Python')
      plan.base = await previewBasePythonRepair(root)
      if (!current()) return
      basePythonPreview.value = plan.base
      if (!plan.base.repair_available || plan.base.recovery_available || plan.base.blockers.length) {
        needsAdvancedMainRepair(); return
      }
    }
    if (!inspected.environment) {
      pending.value = t('正在检查主程序依赖')
      try { guiDiagnosis.value = await diagnoseGui(root, version.id) }
      catch (reason) { addLog(errorText(reason), 'environment'); needsAdvancedMainRepair(); return }
      if (!current()) return
      const diagnosis = guiDiagnosis.value
      const affected = diagnosis.integrity.packages.filter(packageNeedsAttention)
      const unsafe = diagnosis.dirty || diagnosis.recovery_pending || diagnosis.generation !== diagnosis.binding_generation
        || Boolean(diagnosis.installed_metadata_error)
        || diagnosis.integrity.packages.some(item => item.unsupported.length || item.issues.length
          || item.generated.some(file => file.kind === 'optional_derived_bytecode_unverified' && file.present)
          || item.generated.some(file => file.kind === 'rewritten_record' && (!file.present || item.damaged.includes(file.path))))
      if (unsafe || affected.length > 1 || (!affected.length && !plan.base)) {
        needsAdvancedMainRepair(); return
      }
      if (affected.length === 1) {
        plan.package = affected[0]!
        if (!plan.source && !plan.base) {
          try { guiPreview.value = await planGuiRepair(root, version.id, plan.package.name) }
          catch (reason) { addLog(errorText(reason), 'environment'); needsAdvancedMainRepair(); return }
          if (!current()) return
        }
      }
    }
    if (!inspected.uv || (!plan.source && !plan.base && !plan.package)) { needsAdvancedMainRepair(); return }
    mainRepairPlan.value = plan
    mainCheckResult.value = 'repair'
    mainCheckSummary.value = t('发现需要修复的项目：{items}', { items: mainRepairLabels(plan).join(locale.value === 'en-US' ? ', ' : '、') })
  })
  if (mainRepairPlan.value && !running.value) await confirmMainRepair(returnFocus)
}
function mainRepairLabels(plan: MainRepairPlan) {
  return [...(plan.source ? [t('主程序文件')] : []), ...(plan.base ? [t('基础 Python')] : []), ...(plan.package ? [t('依赖包 {name}', { name: plan.package.name })] : [])]
}
function confirmMainRepair(returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null) {
  const plan = mainRepairPlan.value
  if (!plan || mutationDisabled.value) return
  return ask({
    scope: 'gui', actionId: 'confirm-main-repair', title: t('修复主程序'),
    detail: t('将修复：{items}。按需下载固定组件，仅替换本次列出的主程序文件或依赖。训练引擎、模型和用户资料会保留；无法安全修复时将停止并说明原因。', { items: mainRepairLabels(plan).join(locale.value === 'en-US' ? ', ' : '、') }),
    paths: [
      ...(plan.source ? [t('主程序文件：{count} 项，源码下载至多 {size}', { count: plan.source.expected_source_files.length, size: formatFileSize(currentVersion.value?.download_bytes ?? 0) }), plan.source.replacement_root] : []),
      ...(plan.base ? [t('基础 Python：{count} 个固定文件，按需下载；{references} 个引用环境需复验', { count: plan.base.expected_files.length, references: plan.base.references.length })] : []),
      ...(plan.package ? [t('依赖：{name} {version}，使用已校验的本地安装文件', { name: plan.package.name, version: plan.package.version })] : []),
    ], action: t('确认修复'), execute: () => executeMainRepair(plan),
  }, returnFocus)
}
async function runRepairStep(label: string, action: () => Promise<OperationSnapshot>) {
  pending.value = label
  message.value = label
  const next = await action()
  operation.value = next
  operationCursor = 0
  while (!disposed) {
    const value = await operationSnapshot(next.id)
    operation.value = value
    message.value = `${label} · ${phaseText.value[value.phase]}`
    void refreshOperationEvents(value, path.value.trim())
    if (value.status !== 'running') {
      await refreshHistory()
      if (value.status !== 'succeeded') throw new Error(value.error?.message ?? t('修复已停止，请查看日志后重试。'))
      return
    }
    await new Promise(resolve => setTimeout(resolve, 250))
  }
  throw new Error(t('修复已停止，请查看日志后重试。'))
}
async function executeMainRepair(plan: MainRepairPlan) {
  if (mutationDisabled.value) return
  const epoch = guiEpoch
  const ensureCurrent = () => {
    if (disposed || epoch !== guiEpoch || !samePath(plan.root, path.value) || currentVersion.value?.id !== plan.releaseId) throw new Error(t('目录或版本已变化，请重新检查。'))
  }
  await perform(t('正在修复主程序'), async () => {
    repairSequenceRunning.value = true
    try {
      ensureCurrent()
      if (plan.source) await runRepairStep(t('正在修复主程序文件'), () => repairManagedSource(plan.root, plan.releaseId))
      ensureCurrent()
      if (plan.base) {
        const fresh = await previewBasePythonRepair(plan.root)
        ensureCurrent()
        if (fresh.integrity_error) {
          if (!fresh.repair_available || fresh.recovery_available || fresh.blockers.length || fresh.target !== plan.base.target
            || JSON.stringify(fresh.expected_files) !== JSON.stringify(plan.base.expected_files)
            || JSON.stringify(fresh.references.map(item => [item.release_id, item.instance_id]).sort()) !== JSON.stringify(plan.base.references.map(item => [item.release_id, item.instance_id]).sort())) throw new Error(t('修复范围发生变化，请重新检查并确认。'))
          await runRepairStep(t('正在修复基础 Python'), () => repairBasePython(plan.root, plan.releaseId, fresh.plan_sha256))
        }
      }
      ensureCurrent()
      if (plan.package) {
        const fresh = await diagnoseGui(plan.root, plan.releaseId)
        ensureCurrent()
        const affected = fresh.integrity.packages.filter(packageNeedsAttention)
        if (affected.length) {
          if (affected.length !== 1 || affected[0]!.name !== plan.package.name || affected[0]!.version !== plan.package.version) throw new Error(t('修复范围发生变化，请重新检查并确认。'))
          const preview = await planGuiRepair(plan.root, plan.releaseId, plan.package.name)
          ensureCurrent()
          if (preview.paths.some(file => !plan.package!.paths.includes(file))) throw new Error(t('修复范围发生变化，请重新检查并确认。'))
          await runRepairStep(t('正在修复主程序依赖'), () => repairGuiPackage(plan.root, plan.releaseId, plan.package!.name, preview.plan_sha256))
        }
      }
      ensureCurrent()
      pending.value = t('正在验证修复结果')
      acceptReport(await runCommand('inspect', plan.root))
      mainRepairPlan.value = null
      mainCheckResult.value = ready.value ? 'healthy' : 'advanced'
      mainCheckSummary.value = ready.value ? t('主程序检查正常，无需修复。') : t('本次修复已完成，仍有其他问题需要处理。可查看详情或重新安装主程序环境。')
    } finally { repairSequenceRunning.value = false }
  })
  if (error.value) { mainRepairPlan.value = null; needsAdvancedMainRepair(t('修复未完成。请查看日志，或在高级选项中恢复上次变更。')) }
}
function openMainAdvanced() {
  advanced.value = true
  void nextTick(() => document.getElementById('main-advanced')?.scrollIntoView({ block: 'start' }))
}
function openVersionMaintenance(version: DisplayVersion) {
  if (!maintenanceSupported(version)) return
  registrationReleaseId.value = version.id
  changeRegistrationRelease()
  page.value = 'environment'
  openMainAdvanced()
}
async function reinstallMainEnvironment(version = currentVersion.value) {
  if (!version || !maintenanceSupported(version) || mutationDisabled.value || mainReinstall.value) return
  const returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
  registrationReleaseId.value = version.id
  changeRegistrationRelease()
  const request = shallowReactive<MainReinstallRequest>({
    kind: 'rebuild', epoch: guiEpoch, root: path.value.trim(), releaseId: version.id,
    version: `${version.version} · ${version.commit.slice(0, 8)}`,
    selectedInstance: registrationInstanceId.value,
    observedBinding: mainReinstallObservedBinding(path.value.trim(), version.id), phase: 'preparing', reason: '',
    invalidated: false, cancelled: false, queryTarget: null, query: null, identity: null, preview: null, legacyPlan: null,
  })
  mainReinstallReturnFocus = returnFocus
  // Publish the cancellable dialog before starting any IPC or disk work.
  mainReinstall.value = request
  error.value = ''
  await nextTick()
  if (disposed || request.cancelled || request.invalidated || mainReinstall.value !== request) return
  try {
    request.queryTarget = { root: request.root, release_id: request.releaseId, engine_id: 'gui', action: 'preview_gui_rebuild', rebuild: true, scope: 'plan' }
    const query = await beginEngineQuery(request.queryTarget)
    request.query = query
    // Closing or changing selection during admission still cancels the accepted task.
    if (disposed || request.cancelled || request.invalidated || mainReinstall.value !== request) { await cancelEngineQuery(query); return }
    const { result: preview, snapshot } = await waitEngineQuery<GuiLifecyclePreview>(query)
    if (disposed || request.cancelled || request.invalidated || mainReinstall.value !== request) return
    if (!mainReinstallContextCurrent(request)) { invalidateMainReinstall(); return }
    if (preview.plan?.root_absolute && !samePath(request.root, preview.plan.root_absolute)) throw new Error(t('安装计划与当前目录不一致，请重新检查。'))
    if (preview.status !== 'ready') {
      request.phase = 'blocked'
      request.reason = preview.reason || t('当前环境暂时无法重新安装，请先处理提示的问题。')
      return
    }
    if (!preview.plan || !preview.plan_sha256 || !/^[0-9a-f]{64}$/.test(preview.plan_sha256)) throw new Error(t('安装计划不完整，请关闭后重试。'))
    request.identity = snapshot.identity
    if (!mainReinstallContextCurrent(request)) { invalidateMainReinstall(); return }
    request.preview = preview
    request.phase = 'ready'
  } catch (reason) {
    if (!request.query) request.queryTarget = null
    if (disposed || request.cancelled || request.invalidated || mainReinstall.value !== request) return
    request.phase = request.query?.snapshot?.status === 'cancelled' ? 'cancelled' : 'error'
    request.reason = errorText(reason)
    addLog(t('主程序重装准备未完成：{reason}', { reason: request.reason }), 'environment')
  }
}

function mainReinstallContextCurrent(request: MainReinstallRequest) {
  if (request.kind === 'legacy-repair') {
    const version = versions.value.find(item => item.id === request.releaseId)
    return !disposed && samePath(request.root, path.value) && version?.legacy_recovery?.journal_sha256 === request.observedBinding && !version.legacy_environment_repair && (!request.identity || sameEngineQueryIdentity(request.identity, request.query?.snapshot?.identity ?? null))
  }
  if (disposed || request.epoch !== guiEpoch || !samePath(request.root, path.value) || request.releaseId !== registrationRelease.value?.id || request.selectedInstance !== registrationInstanceId.value) return false
  if (request.observedBinding !== mainReinstallObservedBinding(request.root, request.releaseId)) return false
  return !request.identity || sameEngineQueryIdentity(request.identity, request.query?.snapshot?.identity ?? null)
}
function mainReinstallObservedBinding(root: string, releaseId: string) {
  const runtimeIdentity = runtime.value
  const diagnosis = guiDiagnosis.value
  // Cached stopped-runtime/diagnosis records may describe an older instance.
  // Detect changes to the observations, then use the query's validated identity
  // and the unchanged backend plan validation as the authority for submission.
  return JSON.stringify([
    runtimeIdentity && samePath(runtimeIdentity.root, root) && runtimeIdentity.release_id === releaseId ? [runtimeIdentity.instance_id, runtimeIdentity.binding_generation] : null,
    diagnosis && samePath(diagnosis.root, root) && diagnosis.release_id === releaseId ? [diagnosis.instance_id, diagnosis.generation] : null,
  ])
}
function cancelMainReinstallQuery(request: MainReinstallRequest) {
  // Record the intent before admission returns, so an immediate reopen cannot
  // reuse the closing query or start another scan while it is being cancelled.
  const cancellation = request.query
    ? cancelEngineQuery(request.query)
    : request.queryTarget ? cancelEngineQueryTarget(request.queryTarget) : null
  void cancellation?.catch(reason => {
    addLog(t('取消安装准备失败：{reason}', { reason: errorText(reason) }), 'environment')
  })
}
function invalidateMainReinstall() {
  const request = mainReinstall.value
  if (!request || request.cancelled || request.invalidated) return
  request.invalidated = true
  request.phase = 'blocked'
  request.preview = null
  request.reason = t('目录、版本或环境已变化，请关闭后重新准备安装。')
  cancelMainReinstallQuery(request)
}
function closeMainReinstall() {
  const request = mainReinstall.value
  if (!request) return
  request.cancelled = true
  request.phase = 'cancelled'
  request.preview = null
  cancelMainReinstallQuery(request)
  mainReinstall.value = null
  const returnFocus = mainReinstallReturnFocus
  mainReinstallReturnFocus = null
  void nextTick(() => {
    if (!mainReinstall.value && !confirmation.value && returnFocus?.isConnected && !returnFocus.matches(':disabled')) returnFocus.focus({ preventScroll: true })
  })
}
async function confirmMainReinstall() {
  const request = mainReinstall.value
  const preview = request?.preview
  if (request?.kind === 'legacy-repair') {
    const plan = request.legacyPlan
    if (request.phase !== 'ready' || !plan?.ready || mutationDisabled.value) return
    if (request.invalidated || !mainReinstallContextCurrent(request) || !request.query || request.query.invalidated || request.query.snapshot?.validity !== 'current' || !sameEngineQueryIdentity(request.identity, request.query.snapshot.identity)) { invalidateMainReinstall(); return }
    closeMainReinstall()
    invalidateEngineQueryResults(request.root, request.releaseId, 'gui')
    await startGuiOperation(t('正在修复运行环境'), () => repairLegacyEnvironment(request.root, request.releaseId, plan.journal_sha256, plan.plan_sha256))
    return
  }
  if (!request || request.phase !== 'ready' || !preview?.plan_sha256 || mutationDisabled.value) return
  if (request.invalidated || !mainReinstallContextCurrent(request) || !request.query || request.query.invalidated || request.query.snapshot?.validity !== 'current' || !sameEngineQueryIdentity(request.identity, request.query.snapshot.identity)) { invalidateMainReinstall(); return }
  // Closing synchronously consumes the confirmation, so double clicks cannot submit twice.
  closeMainReinstall()
  invalidateEngineQueryResults(request.root, request.releaseId, 'gui')
  await startGuiOperation(t('正在重新安装主程序环境'), () => applyGuiLifecycle(request.root, request.releaseId, 'rebuild', preview.plan_sha256!, null, null))
}

async function diagnoseManagedGui() {
  if (!managedCurrent.value || mutationDisabled.value || !currentVersion.value) return
  clearGuiState()
  const root = path.value.trim()
  const releaseId = currentVersion.value.id
  const epoch = guiEpoch
  await perform(t('只读诊断 GUI 依赖'), async () => {
    const value = await diagnoseGui(root, releaseId)
    if (epoch !== guiEpoch || root !== path.value.trim() || releaseId !== currentVersion.value?.id) return
    guiDiagnosis.value = value
    addLog(t('只读诊断完成：{value0} 个包，实例代次 {value1}。生成脚本的内容验证范围见诊断说明。', { value0: value.integrity.packages.length, value1: value.generation }))
  })
}
async function inspectBasePythonRepair() {
  if (!managedCurrent.value || mutationDisabled.value) return
  const root = path.value.trim()
  const epoch = guiEpoch
  basePythonPreview.value = null
  await perform(t('只读检查基础 Python 与引用环境'), async () => {
    const preview = await previewBasePythonRepair(root)
    if (epoch !== guiEpoch || root !== path.value.trim()) return
    basePythonPreview.value = preview
  })
}
async function inspectGuiRegistration() {
  const version = registrationRelease.value
  if (!version || !maintenanceSupported(version) || mutationDisabled.value) return
  const root = path.value.trim()
  const epoch = guiEpoch
  const selectedInstance = registrationInstanceId.value || null
  registrationPreview.value = null
  await perform(t('只读检查安装登记'), async () => {
    const value = await previewGuiRegistration(root, version.id, selectedInstance)
    if (epoch !== guiEpoch || root !== path.value.trim() || version.id !== registrationRelease.value?.id) return
    registrationPreview.value = value
  })
}
function changeRegistrationRelease() {
  guiEpoch += 1
  invalidateMainReinstall()
  registrationPreview.value = null
  registrationInstanceId.value = ''
  if (confirmation.value?.scope === 'gui') dismissConfirmation()
}
function confirmGuiRegistration(recovery = false) {
  const preview = registrationPreview.value
  const version = registrationRelease.value
  if (!preview || !version || !maintenanceSupported(version) || mutationDisabled.value || (recovery ? preview.status !== 'pending' : preview.status !== 'ready' || !preview.plan || !preview.plan_sha256)) return
  const root = path.value.trim()
  const epoch = guiEpoch
  const candidate = preview.plan?.candidate
  return ask({
    scope: 'gui', title: recovery ? t('继续恢复安装登记') : t('恢复安装登记'),
    detail: t('将离线核验固定文件、解释器和全部依赖，并在独立临时资料目录验证真实入口，再补齐缺失的安装记录。已有环境与用户资料须保持不变；登记恢复完成后，仍需选择版本并正常启动才能建立本次启动健康记录。'),
    paths: preview.plan ? [t('版本：{value0}', { value0: version.id }), t('环境：{value0}', { value0: preview.plan.proof.environment }), t('实例：{value0} · 路径格式 {value1} · 已知代次 {value2}', { value0: candidate?.id ?? '', value1: candidate?.storage_version ?? 0, value2: candidate?.generation ?? 0 }), t('可信文件：{value0} 个', { value0: preview.plan.proof.files.toLocaleString() }), t('固定文件索引：{value0}', { value0: preview.plan.proof.trusted_index_sha256 })] : [t('事务：{value0}', { value0: preview.transaction ?? '' })],
    action: recovery ? t('继续核验与补齐登记') : t('确认核验并恢复登记'),
    execute: async () => {
      if (epoch !== guiEpoch || root !== path.value.trim() || version.id !== registrationRelease.value?.id) { error.value = t('目录或版本已改变，请重新检查安装登记。'); return }
      await startGuiOperation(t('正在验证并恢复安装登记'), () => recovery ? recoverGuiRegistration(root, version.id)
        : restoreGuiRegistration(root, version.id, candidate!.id, preview.plan_sha256!))
    },
  })
}
async function inspectLifecycle(action: 'rebuild' | 'rollback') {
  const version = registrationRelease.value
  if (!version || !maintenanceSupported(version) || mutationDisabled.value) return
  const root = path.value.trim(), epoch = guiEpoch
  lifecyclePreview.value = null
  await perform(t('检查实例重建与回退计划'), async () => {
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
  if (!version || !maintenanceSupported(version) || busy.value || !sameRoot.value) return
  const root = path.value.trim(), epoch = guiEpoch
  await perform(t('读取实例操作记录'), async () => {
    const value = await guiLifecycleHistory(root, version.id)
    if (epoch === guiEpoch && root === path.value.trim()) lifecycleHistory.value = value
  })
}
function confirmLifecycle(action: GuiLifecycleAction, transaction: string | null = null, instance: string | null = null) {
  const version = registrationRelease.value, preview = lifecyclePreview.value
  if (!version || !maintenanceSupported(version) || mutationDisabled.value) return
  if ((action === 'rebuild' || action === 'rollback') && (preview?.status !== 'ready' || !preview.plan_sha256)) return
  const root = path.value.trim(), epoch = guiEpoch
  const title = action === 'rebuild' ? t('在新路径重建环境') : action === 'rollback' ? t('回退到同版本旧实例') : t('恢复实例事务')
  return ask({ scope: 'gui', title,
    detail: action === 'rebuild'
      ? t('在新的固定路径创建环境，原实例和资料保留。只有固定依赖及独立入口验证通过后才切换绑定；未完成的候选保持不可启动。')
      : t('重新验证目标实例和当前绑定，恢复时保留原事务、资料与非目标文件。恢复完成并不代表训练或模型已验证。'),
    paths: [t('版本：{value0}', { value0: version.id }), t('安装目录：{value0}', { value0: root }), ...(transaction ? [t('操作记录：{value0}', { value0: transaction })] : []), ...(instance ? [t('实例：{value0}', { value0: instance })] : [])],
    action: action === 'rebuild' ? t('确认创建新实例') : action === 'rollback' ? t('确认验证并回退') : t('确认恢复事务'),
    execute: async () => {
      if (epoch !== guiEpoch || root !== path.value.trim() || version.id !== registrationRelease.value?.id) { error.value = t('目录或版本已变化，请重新检查。'); return }
      await startGuiOperation(title, () => applyGuiLifecycle(root, version.id, action, preview?.plan_sha256 ?? null, transaction, instance))
      lifecyclePreview.value = null
      lifecycleHistory.value = null
    },
  })
}
function confirmBasePythonRepair(recovery = false) {
  const preview = basePythonPreview.value
  const version = currentVersion.value ?? defaultRelease.value
  if (!managedCurrent.value || !preview || !version || !maintenanceSupported(version) || mutationDisabled.value || (recovery ? !preview.recovery_available : !preview.repair_available)) return
  const root = path.value.trim()
  const epoch = guiEpoch
  return ask({
    scope: 'gui', title: recovery ? t('继续基础 Python 组件恢复') : t('恢复基础 Python 组件'),
    detail: t('将恢复 {value0} 的完整固定组件，共 {value1} 个文件。{value2} 个引用环境会统一暂停使用，逐个验证通过后再保存新代次；环境安装文件、源码与用户资料须保持不变。本来待恢复的实例不会因此变成可用。', { value0: preview.target, value1: preview.expected_files.length.toLocaleString(), value2: preview.references.length }),
    paths: [...preview.references.map((reference) => t('引用：{value0} / {value1} · 代次 {value2} · {value3}{value4}', { value0: reference.release_id, value1: reference.instance_id, value2: reference.generation, value3: reference.environment, value4: reference.initial_dirty ? t(' · 原本待恢复') : '' })), ...preview.expected_files],
    action: recovery ? t('继续恢复与逐环境校验') : t('确认恢复完整组件'),
    execute: async () => {
      if (epoch !== guiEpoch || root !== path.value.trim()) { error.value = t('目录或版本已改变，请重新检查基础 Python。'); return }
      await startGuiOperation(t('正在恢复基础 Python 与引用环境'), () => recovery ? recoverBasePython(root, version.id) : repairBasePython(root, version.id, preview.plan_sha256))
    },
  })
}
async function previewPackage(item: PackageIntegrity) {
  if (!managedCurrent.value || !currentVersion.value || !guiDiagnosis.value || packagePlanDisabled(item)) return
  guiPreview.value = null
  const root = path.value.trim()
  const releaseId = currentVersion.value.id
  const epoch = guiEpoch
  await perform(t('生成 {value0} 修复清单', { value0: item.name }), async () => {
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
  if (!managedCurrent.value || !preview || !version || mutationDisabled.value || guiPlanBlocked.value) return
  const root = path.value.trim()
  const epoch = guiEpoch
  return ask({
    scope: 'gui', title: t('确认修复 {value0}', { value0: preview.package }),
    detail: t('将按以下 {value0} 个文件路径修复 {value1} {value2}。仅离线重装此包，先保存独立快照，再验证完整依赖与关键导入。快照恢复后若仍不通过验证，实例会保持待恢复状态。安装器生成脚本只检查路径与存在性。', { value0: preview.paths.length.toLocaleString(), value1: preview.package, value2: preview.version }),
    paths: preview.paths, action: t('确认修复此包'),
    execute: async () => {
      if (epoch !== guiEpoch || root !== path.value.trim() || version.id !== currentVersion.value?.id) { error.value = t('目录或版本已改变，请重新诊断生成清单。'); return }
      await startGuiOperation(t('正在修复指定包'), () => repairGuiPackage(root, version.id, preview.package, preview.plan_sha256))
    },
  })
}
function confirmGuiRecovery() {
  const version = currentVersion.value
  const diagnosis = guiDiagnosis.value
  if (!managedCurrent.value || !version || !diagnosis || mutationDisabled.value || !guiRecoveryNeeded.value) return
  const root = path.value.trim()
  const epoch = guiEpoch
  return ask({
    scope: 'gui', title: t('恢复未完成的单包修复'),
    detail: t('将读取实例 {value0} 的持久修复记录，恢复独立快照或完成已验证代次的登记，并重新检查依赖与关键导入。原快照已损坏时会继续保留待恢复状态，恢复操作不保证环境通过验证。', { value0: diagnosis.instance_id }),
    action: t('开始恢复与校验'),
    execute: async () => {
      if (epoch !== guiEpoch || root !== path.value.trim() || version.id !== currentVersion.value?.id) { error.value = t('目录或版本已改变，请重新诊断。'); return }
      await startGuiOperation(t('正在恢复未完成修复'), () => recoverGuiRepair(root, version.id))
    },
  })
}
async function inspectSourceRepair(version: DisplayVersion) {
  if (!maintenanceSupported(version) || mutationDisabled.value) return
  const returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
  const root = path.value.trim()
  await perform(t('查看源码修复清单'), async () => {
    const preview = await previewSourceRepair(root, version.id)
    if (root !== path.value.trim()) return
    await ask({
      scope: 'gui', title: t('确认修复固定版本源码'),
      detail: t('将替换 {value0} 中的 {value1} 个固定源码和前端文件，原目录移至备份。环境实例和用户资料须保持不变。{value2}', { value0: preview.replacement_root, value1: preview.expected_source_files.length, value2: preview.source_integrity_error ? t('当前源码检查未通过。') : t('当前源码完整，执行时将再次检查。') }),
      paths: [...preview.expected_source_files, ...preview.generated_files],
      action: t('确认修复源码'),
      execute: async () => {
        if (root !== path.value.trim()) { error.value = t('目录已改变，请重新查看清单。'); return }
        await startGuiOperation(t('正在修复固定源码'), () => repairManagedSource(root, version.id))
      },
    }, returnFocus)
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
    message.value = t('操作未能开始，请重新诊断后重试。')
  } finally { pending.value = '' }
}
async function startEngineOperation(label: string, action: () => Promise<OperationSnapshot>) {
  if (busy.value) return
  startingEngineOperation.value = true
  try {
    await startGuiOperation(label, async () => {
      const next = await action()
      engineOperationId.value = next.id
      return next
    })
  } finally { startingEngineOperation.value = false }
}
onMounted(async () => {
  void readLauncherPreferences()
  try { unlisten = await listenToLogEntries(acceptLogEntry); runtimeUnlisten = await listenToRuntime(acceptRuntime) }
  catch { addLog(t('桌面事件接口尚未连接；请通过桌面启动器打开此页面。')) }
  void syncRuntime()
  runtimeTimer = setInterval(() => { void syncRuntime() }, 1500)
  void getVersion().then(value => { appVersion.value = value }).catch(() => undefined)
  void refreshInstallation().then(() => refreshHistory()).catch(reason => { error.value = errorText(reason) })
})
onBeforeUnmount(() => { disposed = true; if (operationTimer) clearTimeout(operationTimer); if (inventoryTimer) clearTimeout(inventoryTimer); if (runtimeTimer) clearInterval(runtimeTimer); unlisten?.(); runtimeUnlisten?.() })
</script>

<template>
  <div class="app-shell" :class="{ 'home-view': page === 'launch', 'reduce-motion': appearance.reduceMotion, 'home-title-dark': homeInk.titleDark, 'home-heading-dark': homeInk.headingDark, 'home-controls-dark': homeInk.controlsDark }" data-material="acrylic" :data-verification="report && sameRoot ? 'complete' : 'not_run'" :data-snapshot-state="inventory?.workspace ?? 'loading'" :data-repair-sequence="repairSequenceRunning" :data-page="page" :data-runtime-phase="runtimePhase" :data-runtime-run-id="runtime?.run_id ?? ''" :data-runtime-seq="runtime?.seq ?? 0" :style="{ '--wallpaper': 'url(' + (appearance.background || '/assets/launcher-wallpaper.png') + ')', '--content-blur': `${appearance.blur}px`, '--mask-opacity': String(appearance.mask / 100) }">
    <svg class="material-definitions" aria-hidden="true" focusable="false"><defs><filter id="fluent-acrylic" x="0" y="0" width="100%" height="100%" color-interpolation-filters="sRGB"><feGaussianBlur in="SourceGraphic" :stdDeviation="appearance.blur" edgeMode="duplicate" result="blur" /><feFlood flood-color="#202020" :flood-opacity="acrylicOpacity.luminosity" result="luminosity" /><feBlend in="luminosity" in2="blur" mode="luminosity" result="lit" /><feFlood flood-color="#1c1c1c" :flood-opacity="acrylicOpacity.tint" result="tint" /><feBlend in="tint" in2="lit" mode="color" /></filter></defs></svg>
    <Transition name="wallpaper" appear><div :key="appearance.background" class="wallpaper" :style="{ backgroundImage: 'url(' + (appearance.background || '/assets/launcher-wallpaper.png') + ')' }" aria-hidden="true"></div></Transition><div class="wallpaper-shade" aria-hidden="true"></div><div class="acrylic-layer" aria-hidden="true"></div>
    <aside id="launcher-sidebar" class="sidebar" :class="{ expanded: sidebarExpanded }" :aria-label="t('启动器导航')" @keydown.esc="sidebarExpanded && (sidebarExpanded = false, sidebarToggle?.focus())">
      <button ref="sidebarToggle" class="sidebar-toggle" :aria-label="sidebarExpanded ? t('收起侧边栏') : t('展开侧边栏')" :title="sidebarExpanded ? t('收起侧边栏') : t('展开侧边栏')" :aria-expanded="sidebarExpanded" aria-controls="launcher-sidebar" @click="sidebarExpanded = !sidebarExpanded"><Icon name="menu" /><span class="nav-label" aria-hidden="true">{{ t('收起导航') }}</span></button>
      <nav :aria-label="t('主导航')"><button v-for="item in ([{ id: 'launch', icon: 'home', label: t('首页') }, { id: 'versions', icon: 'versions', label: t('版本管理') }, { id: 'environment', icon: 'environment', label: t('环境管理') }, { id: 'logs', icon: 'logs', label: t('日志') }] as const)" :key="item.id" :class="{ selected: page === item.id }" :aria-current="page === item.id ? 'page' : undefined" :aria-label="item.label" :title="item.label" @click="page = item.id"><Icon :name="item.icon" /><span class="nav-label" aria-hidden="true">{{ item.label }}</span></button></nav>
      <div class="sidebar-foot"><button :class="{ selected: page === 'settings' }" :aria-current="page === 'settings' ? 'page' : undefined" :aria-label="t('启动器设置')" :title="t('启动器设置')" @click="page = 'settings'"><Icon name="settings" /><span class="nav-label" aria-hidden="true">{{ t('设置') }}</span></button></div>
    </aside>
    <header class="titlebar" @mousedown="dragTitlebar" @dblclick="windowControl('maximize')"><span class="titlebar-name">{{ titlebarVersion }}</span><span class="titlebar-state" :class="{ good: stateGood, working: transitioning }" role="status" aria-live="polite"><i></i>{{ stateText }}</span><div class="window-controls"><button :aria-label="t('最小化')" :title="t('最小化')" @dblclick.stop @click="windowControl('minimize')"><Icon name="minimize" /></button><button :aria-label="t('最大化或还原')" :title="t('最大化 / 还原')" @dblclick.stop @click="windowControl('maximize')"><Icon name="maximize" /></button><button class="window-close" :aria-label="t('关闭启动器')" :title="t('关闭')" @dblclick.stop @click="windowControl('close')"><Icon name="close" /></button></div></header>
    <main class="launcher-main" @pointerdown.capture="sidebarExpanded = false">
      <section v-show="page === 'launch'" class="home-page" :aria-label="t('首页')">
        <div class="home-heading"><img src="/assets/home-logo.webp" :alt="t('Next Trainer 项目标志')" /><div><h1>NextTrainer</h1></div></div>
        <article class="release-float" :aria-label="t('项目信息')">
          <button class="release-art" data-link-target="releases" :aria-label="t('打开 Next Trainer 项目发布页')" @click="openProjectLink('releases')"><img class="release-cover" src="/assets/next-trainer-cover.png" :alt="t('Next Trainer 项目封面')" /></button>
          <div class="release-body">
            <div class="release-tabs" role="tablist" :aria-label="t('项目信息栏目')">
              <button id="project-releases-tab" role="tab" :aria-selected="informationTab === 'releases'" aria-controls="project-releases" :class="{ selected: informationTab === 'releases' }" @click="informationTab = 'releases'">{{ t('项目发布') }}</button>
              <button id="friend-links-tab" role="tab" :aria-selected="informationTab === 'friends'" aria-controls="friend-links" :class="{ selected: informationTab === 'friends' }" @click="informationTab = 'friends'">{{ t('友情链接') }}</button>
            </div>
            <div v-show="informationTab === 'releases'" id="project-releases" class="release-copy release-detail" role="tabpanel" aria-labelledby="project-releases-tab"><p>{{ t('版本更新、功能说明与项目发布记录。') }}</p><button class="text-row" data-link-target="releases" @click="openProjectLink('releases')"><span>{{ t('前往 GitHub Releases') }}</span><Icon name="external" /></button></div>
            <div v-show="informationTab === 'friends'" id="friend-links" class="friend-links" role="tabpanel" aria-labelledby="friend-links-tab">
              <button data-link-target="blog" @click="openProjectLink('blog')"><span>{{ t('Displace 博客') }}</span><Icon name="external" /></button>
              <button data-link-target="bilibili" @click="openProjectLink('bilibili')"><span>{{ t('Bilibili 个人空间') }}</span><Icon name="external" /></button>
              <button data-link-target="modelscope" @click="openProjectLink('modelscope')"><span>{{ t('ModelScope 魔搭') }}</span><Icon name="external" /></button>
            </div>
          </div>
        </article>
        <div v-if="error || runtime?.error" class="home-error" role="alert"><Icon name="info" /><span>{{ error || runtime?.error }}</span><button @click="showLogs(true)">{{ t('查看日志') }}<Icon name="arrow" /></button></div>
        <div class="home-bottom"><div v-if="operation?.status === 'running'" class="home-operation-actions"><span>{{ phaseText[operation.phase] }}</span><button @click="showLogs()">{{ t('查看日志') }}</button><button :disabled="operation.cancel_requested" @click="cancelCurrentOperation">{{ operation.cancel_requested ? t('正在收尾') : t('取消操作') }}</button></div><div v-if="healthy && serviceUrl" class="service-caption"><span>{{ serviceUrl }}</span><button class="icon-button" :aria-label="t('复制服务地址')" :title="t('复制服务地址')" @click="copyAddress"><Icon name="copy" /></button></div><div class="launch-row"><button v-if="['checking', 'starting', 'ready', 'degraded', 'stop_failed'].includes(runtimePhase)" class="secondary-pill" :disabled="serviceAction === 'stop'" @click="stop"><Icon :name="transitioning ? 'close' : 'stop'" />{{ ['checking', 'starting'].includes(runtimePhase) ? t('取消启动') : t('停止服务') }}</button><button v-else class="secondary-pill" @click="openSetting('profiles')"><Icon name="folder" />{{ t('安装位置') }}</button><button v-if="healthy" class="launch-button" data-action="open-trainer" @click="open"><Icon name="external" />{{ t('打开训练器') }}</button><button v-else class="launch-button" data-action="start-trainer" :disabled="primaryDisabled" @click="primary"><Icon :name="transitioning || pending ? 'refresh' : 'home'" :class="{ spin: transitioning || pending }" />{{ transitioning ? runtimeLabels[runtimePhase] : pending || primaryLabel }}</button></div></div>
      </section>
      <section v-show="page === 'versions'" class="content-page" :aria-label="t('版本管理')">
        <header class="page-title"><h1>{{ t('版本管理') }}</h1><p>{{ t('在本机版本之间切换，资料始终保留。') }}</p></header>
        <div class="section-toolbar"><span class="context-label">{{ versions.filter(version => version.installed).length }} {{ t('个已安装版本') }}</span><button :disabled="busy || inventoryLoading" data-action="refresh-versions" @click="refreshInstallation()"><Icon name="refresh" />{{ t('刷新本机版本') }}</button></div>
        <p v-if="pendingLegacyVersions.length" class="inline-note" role="note">{{ t('有未完成的历史安装，请在对应版本选择“检查并完成安装”。检查通过前继续保留启动保护。') }}</p>
        <div v-if="currentVersion" class="version-installed"><img src="/assets/home-logo.webp" alt="Next Trainer" /><div><h2>Next Trainer <span>{{ currentVersion.version }}</span></h2><div class="inline-tags"><span class="tag active-tag">{{ t('当前使用') }}</span><span class="tag">{{ channelName(currentVersion.channel) }}</span><code>{{ currentVersion.commit.slice(0, 8) }}</code></div><p>{{ releaseState(currentVersion) }}</p></div></div>
        <section class="rollback-panel"><div><strong>{{ t('上一已健康版本') }}</strong><p v-if="rollbackVersion"><span>{{ channelName(rollbackVersion.channel) }} · {{ rollbackVersion.version }}</span><code>{{ rollbackVersion.commit.slice(0, 8) }}</code></p><p v-else>{{ t('尚无可回退记录。版本成功启动并通过健康检查后会记录。') }}</p></div><button :disabled="mutationDisabled || !rollbackAvailable" @click="rollback">{{ t('回退到此版本') }}</button></section>
        <section v-for="group in channels" :key="group.channel" class="channel-section" :aria-label="channelName(group.channel)">
          <h3>{{ channelName(group.channel) }}<span>{{ group.channel === 'dev' ? t('包含开发中的改动') : group.channel === 'main' ? t('稳定发布线') : t('内置版本') }}</span></h3>
          <p v-if="!group.versions.length" class="empty-channel">{{ t('内置清单尚未提供此发布线的版本。') }}</p>
          <article v-for="version in group.versions" :key="version.id" class="version-card" :aria-label="`${version.channel} ${version.version} ${version.commit.slice(0, 8)}`">
            <div class="version-top"><div><strong>{{ version.version }}</strong><span v-if="version.current || version.id === currentReleaseId" class="current-tag">{{ t('当前使用') }}</span><span v-else-if="version.id === previousReleaseId" class="healthy-tag">{{ t('回退保留') }}</span><span v-else-if="version.known_good" class="healthy-tag">{{ t('曾健康启动') }}</span></div><span class="release-state" :class="{ good: version.source_ok === true && version.environment_ok === true }">{{ releaseState(version) }}</span></div>
            <details class="gui-file-details"><summary>{{ t('版本详情') }}</summary><button v-if="version.installed && maintenanceSupported(version)" :disabled="busy" @click="openVersionMaintenance(version)">{{ t('修复此版本') }}</button><dl class="version-details"><div><dt>{{ t('提交') }}</dt><dd><code>{{ version.commit }}</code></dd></div><div><dt>{{ t('下载') }}</dt><dd><code>{{ formatBytes(version.download_bytes) }}</code><span class="detail-note">{{ t('源码制品') }}</span></dd></div><div><dt>{{ t('磁盘') }}</dt><dd><code>{{ formatBytes(version.source_bytes) }}</code><span class="detail-note">{{ version.installed ? t('源码展开；运行环境另计') : t('预计源码展开；运行环境另计') }}</span></dd></div></dl></details>
            <div class="version-actions"><button v-if="version.legacy_environment_repair" data-action="recover-legacy-environment" :data-release-id="version.id" :disabled="mutationDisabled" @click="recoverLegacyRepair(version)">{{ t('恢复环境修复') }}</button><button v-else-if="version.legacy_recovery" data-action="repair-legacy-environment" :data-release-id="version.id" :disabled="mutationDisabled" @click="prepareLegacyEnvironment(version)">{{ t('修复运行环境') }}</button><button v-if="version.legacy_recovery" data-action="resume-legacy-install" :data-release-id="version.id" :disabled="mutationDisabled || !!version.legacy_environment_repair" @click="resumeInstallation(version)">{{ t('检查并完成安装') }}</button><button v-if="!version.installed" :disabled="mutationDisabled || !installSupported(version)" :title="!installSupported(version) ? t('本启动器未提供此版本的安装配方，请安装受支持的新版本。') : undefined" @click="install(version)">{{ t('下载安装') }}</button><button :disabled="mutationDisabled || !!version.legacy_recovery || !!version.legacy_environment_repair || !version.installed || version.source_ok === false || version.environment_ok === false || version.structure === 'attention' || version.current || version.id === currentReleaseId" @click="select(version)">{{ t('切换到此版本') }}</button><button class="delete-button" :disabled="mutationDisabled || !!version.legacy_recovery || !!version.legacy_environment_repair || !version.installed || protectedRelease(version)" :title="protectedRelease(version) ? t('当前版本及上一已健康版本需保留') : t('删除受管版本目录')" @click="remove(version)">{{ t('删除') }}</button></div>
          </article>
        </section>
        <p class="scope-note">{{ t('版本列表只读取安装信息。切换与启动时会完整校验；修复请前往环境管理。当前版本和上一已健康版本受删除保护。') }}</p>
      </section>
      <section v-show="page === 'environment'" class="content-page environment-page" :aria-label="t('环境管理')">
        <header class="page-title"><h1>{{ t('环境管理') }}</h1><p>{{ t('检查主程序和各训练引擎，按需修复损坏部分。') }}</p></header>
        <div class="section-toolbar"><div class="context-label">Next Trainer <b>{{ currentVersion?.version ?? t('尚未选择版本') }}</b><span v-if="currentVersion" class="tag">{{ t('当前版本') }}</span></div></div>
        <p v-if="error" class="gui-issue" role="alert">{{ error }}</p>
        <article class="main-environment"><div class="main-env-icon"><Icon name="environment" /></div><div class="main-env-copy"><h2>{{ t('主程序环境') }} <span class="engine-state" :class="{ good: ready }"><i v-if="ready"></i>{{ ready ? t('检查正常') : mainCheckResult === 'repair' ? t('需要修复') : mainCheckResult === 'advanced' ? t('需要进一步处理') : t('未检查') }}</span></h2><p>{{ t('基础 Python · 主程序依赖 · 网页资源') }}</p></div><div class="main-env-actions"><button data-action="check-repair-main" :disabled="busy || !sameRoot || transitioning || !!serviceAction" @click="checkAndRepairMain"><Icon v-if="pending" name="refresh" class="spin" />{{ pending || (mainInstallationMissing ? t('安装') : t('检查并修复')) }}</button><button @click="advanced = !advanced">{{ advanced ? t('收起高级选项') : t('高级选项') }}<Icon name="arrow" /></button></div></article>
        <div v-if="mainCheckSummary" class="scope-note" role="status" data-main-check-result="true"><p>{{ mainCheckSummary }}</p><template v-if="mainRepairPlan && !repairSequenceRunning"><p v-if="running">{{ t('需要修改主程序。请先停止服务，再确认修复。') }}</p><button v-if="running" @click="stop">{{ t('停止服务') }}</button><button data-action="review-main-repair" :disabled="mutationDisabled" @click="confirmMainRepair()">{{ t('确认修复') }}</button></template><button v-if="mainCheckResult === 'advanced' && managedCurrent" data-action="reinstall-main-environment" :disabled="mutationDisabled" @click="reinstallMainEnvironment()">{{ t('重新安装环境') }}</button><button v-if="mainCheckResult === 'advanced'" class="text-button" @click="openMainAdvanced">{{ t('查看高级选项') }}</button></div>
        <p v-if="currentMaintenanceUnsupported" class="inline-note" role="note">{{ t('本启动器未提供此版本的精准修复配方。需要修复时，请在版本管理安装受支持的新版本，确认后切换。当前版本和资料会保留。') }}<button class="text-button" @click="page = 'versions'">{{ t('前往版本管理') }}<Icon name="arrow" /></button></p>
        <p v-if="currentSourceUnsupported" class="inline-note" role="note">{{ t('本包未提供校验清单，无法判断此版本源码是否完整。请在版本管理选择受支持的版本。') }}<button class="text-button" @click="page = 'versions'">{{ t('前往版本管理') }}<Icon name="arrow" /></button></p>
        <EnginePanel v-if="sameRoot && activeManagedRelease" :root="path.trim()" :release-id="activeManagedRelease.id" :disabled="engineReadDisabled" :apply-disabled="engineMutationDisabled" :refresh-token="`${operation?.id ?? ''}:${operation?.status ?? ''}`" @operate="startEngineOperation" /><p v-else class="empty-note">{{ t('检查安装目录并选择训练器版本后，可分别管理四个训练引擎。') }}</p>
        <div id="main-advanced" v-show="advanced && registrationVersions.length > 0" class="advanced-recovery"><section v-if="registrationRelease" class="gui-diagnostics" aria-labelledby="maintenance-target-title"><h2 id="maintenance-target-title">{{ t('维护指定版本') }}</h2><label>{{ t('目标版本') }}<AcrylicSelect :aria-label="t('维护目标版本')" :model-value="registrationRelease.id" :disabled="mutationDisabled" :options="registrationVersions.filter(version => version.installed).map(version => ({ value: version.id, label: `${channelName(version.channel)} · ${version.version} · ${version.commit.slice(0, 8)}` }))" @change="registrationReleaseId = $event.target.value; changeRegistrationRelease()" /></label><p class="hint">{{ t('操作只针对所选版本，完成后不会自动切换当前版本。') }}</p><button v-if="registrationRelease.installed" :disabled="mutationDisabled" @click="inspectSourceRepair(registrationRelease)">{{ t('检查主程序文件修复') }}</button><button v-if="registrationRelease.installed" :disabled="mutationDisabled" @click="reinstallMainEnvironment(registrationRelease)">{{ t('重新安装主程序环境') }}</button></section><h2>{{ t('主程序检查与高级恢复') }}</h2><p class="hint">{{ t('完整性检查与恢复按实际文件验证。执行修改前请先停止训练器。') }}</p><div v-if="report?.checks.length && sameRoot" class="checks" role="list" :aria-label="t('环境检查明细')"><div v-for="(check, index) in report.checks" :key="`${index}-${check.name}`" class="check-row" role="listitem"><span class="check-badge" :class="{ ok: check.ok }">{{ check.ok ? t('通过') : t('待处理') }}</span><div><strong>{{ check.name }}</strong><p>{{ check.detail }}</p></div></div></div>
      <section v-if="sameRoot && registrationVersions.length && (mainCheckResult === 'advanced' || !startAvailable || registrationPreview)" class="gui-diagnostics" aria-labelledby="registration-title">
            <div class="section-caption"><h2 id="registration-title">{{ t('恢复安装登记') }}</h2><button :disabled="mutationDisabled" @click="inspectGuiRegistration">{{ t('只读检查登记') }}</button></div>
            <p class="hint">{{ t('源码和环境仍在、安装记录丢失时，可离线验证并补齐登记。检查不会执行解释器；确认后会使用独立临时资料验证真实入口。') }}</p>
            <label>{{ t('需要恢复的版本') }}<AcrylicSelect :aria-label="t('需要恢复的版本')" :model-value="registrationRelease?.id" :disabled="mutationDisabled" :options="registrationVersions.map(version => ({ value: version.id, label: `${channelName(version.channel)} · ${version.version} · ${version.commit.slice(0, 8)}` }))" @change="registrationReleaseId = $event.target.value; changeRegistrationRelease()" /></label>
            <template v-if="registrationPreview">
              <p v-if="registrationPreview.reason" class="gui-issue" role="alert">{{ registrationPreview.reason }}</p>
              <p v-if="registrationPreview.status === 'pending'" class="hint">{{ t('存在待恢复登记事务：') }}{{ registrationPreview.transaction }}</p>
              <label v-if="registrationPreview.candidates?.length">{{ t('指定已有实例') }}<AcrylicSelect :aria-label="t('指定已有实例')" v-model="registrationInstanceId" :disabled="mutationDisabled" :options="[{ value: '', label: t('按已有绑定检查') }, ...registrationPreview.candidates.map(candidate => ({ value: candidate.id, label: t('{value0} · 路径格式 {value1} · 代次 {value2} · {value3}', { value0: candidate.id, value1: candidate.storage_version, value2: candidate.generation, value3: candidate.status === 'clean' ? t('已有验证记录') : candidate.status === 'missing_state' ? t('实例记录缺失') : t('需要先恢复原事务') }) }))]" @change="guiEpoch += 1; registrationPreview = null" /><span class="hint">{{ t('选择后请重新执行只读检查，确认环境与影响。') }}</span></label>
              <p v-if="registrationPreview.plan">{{ t('环境：') }}<code>{{ registrationPreview.plan.proof.environment }}</code> · {{ registrationPreview.plan.proof.files.toLocaleString() }} {{ t('个可信文件') }}</p>
              <button v-if="registrationPreview.status === 'ready'" :disabled="mutationDisabled" @click="confirmGuiRegistration()">{{ t('审查并恢复登记') }}</button>
              <button v-if="registrationPreview.status === 'pending'" :disabled="mutationDisabled" @click="confirmGuiRegistration(true)">{{ t('继续未完成登记恢复') }}</button>
            </template>
          </section>
          <section v-if="sameRoot && registrationRelease" class="gui-diagnostics" aria-labelledby="lifecycle-title" data-action="main-lifecycle">
            <div class="section-caption"><h2 id="lifecycle-title">{{ t('独立环境重建与回退') }}</h2><button data-action="read-main-instance-history" :disabled="busy || !sameRoot" @click="inspectLifecycleHistory">{{ t('读取实例记录') }}</button></div>
            <p class="hint">{{ t('环境无法精准修复时，可在新路径重建。旧实例保留，切换前会验证依赖和独立入口；同版本回退使用已保存的重建记录。') }}</p>
            <p>{{ t('目标版本：') }}{{ registrationRelease.version }} · {{ registrationRelease.commit.slice(0, 8) }}</p>
            <button :disabled="mutationDisabled" @click="inspectLifecycle('rebuild')">{{ t('预览新实例重建') }}</button>
            <template v-if="lifecycleHistory">
              <label>{{ t('可回退的重建记录') }}<AcrylicSelect :aria-label="t('可回退的重建记录')" v-model="lifecycleTransaction" :disabled="mutationDisabled" :options="[{ value: '', label: t('请选择记录') }, ...lifecycleHistory.records.filter(item => item.rollback_available).map(record => ({ value: record.transaction, label: `${record.transaction} · ${record.candidate_id}` }))]" @change="lifecyclePreview = null" /></label>
              <button :disabled="mutationDisabled || !lifecycleTransaction" @click="inspectLifecycle('rollback')">{{ t('预览同版本实例回退') }}</button>
              <div v-for="pending in lifecycleHistory.pending_transactions" :key="pending.transaction" class="gui-recovery"><p>{{ t('未完成实例事务：') }}{{ pending.transaction }} · {{ pending.status }}</p><button :disabled="mutationDisabled" @click="confirmLifecycle(pending.kind === 'binding_switch' ? 'recover_rollback' : 'recover_rebuild', pending.transaction)">{{ t('复验并恢复此事务') }}</button></div>
              <div v-for="instance in lifecycleHistory.preserved_pending" :key="instance.instance_id" class="gui-recovery"><p>{{ t('已保留的旧事务实例：') }}{{ instance.instance_id }}</p><button :disabled="mutationDisabled" @click="confirmLifecycle('recover_preserved', null, instance.instance_id)">{{ t('恢复旧实例事务') }}</button></div>
              <button v-if="lifecycleHistory.status === 'rollback_pending'" :disabled="mutationDisabled" @click="confirmLifecycle('recover_rollback')">{{ t('继续未完成的实例回退') }}</button>
            </template>
            <template v-if="lifecyclePreview">
              <p v-if="lifecyclePreview.reason" class="gui-issue" role="alert">{{ lifecyclePreview.reason }}</p>
              <p v-if="lifecyclePreview.plan" class="hint">{{ t('旧实例：') }}{{ (lifecycleAction === 'rollback' ? lifecyclePreview.plan.target_binding : lifecyclePreview.plan.old_binding)?.instance_id ?? t('尚无绑定') }} {{ t('· 预计下载') }} {{ formatFileSize(lifecyclePreview.plan.estimated_network_bytes ?? 0) }}</p>
              <button v-if="lifecyclePreview.status === 'ready'" :disabled="mutationDisabled" @click="confirmLifecycle(lifecycleAction, lifecycleAction === 'rollback' ? lifecycleTransaction : null)">{{ lifecycleAction === 'rebuild' ? t('审查并创建新实例') : t('审查并回退旧实例') }}</button>
            </template>
          </section>
          <section v-if="managedCurrent && (basePythonPreview || (report && !report.python))" class="gui-diagnostics" aria-labelledby="base-python-title">
            <div class="section-caption"><h2 id="base-python-title">{{ t('基础 Python 组件') }}</h2><button :disabled="mutationDisabled" @click="inspectBasePythonRepair">{{ t('检查组件与引用环境') }}</button></div>
            <p class="hint">{{ t('检查只读取文件，Python 缺失或损坏时仍可查看。恢复会替换完整基础组件，并验证所有受管引用环境。') }}</p>
            <template v-if="basePythonPreview">
              <p v-if="basePythonPreview.integrity_error" class="gui-issue" role="alert">{{ basePythonPreview.integrity_error }}</p>
              <p v-else class="hint">{{ t('基础组件固定文件完整。') }}</p>
              <p>{{ basePythonPreview.references.length }} {{ t('个引用环境 ·') }} {{ basePythonPreview.expected_files.length.toLocaleString() }} {{ t('个固定组件文件') }}</p>
              <ul v-if="basePythonPreview.references.length"><li v-for="reference in basePythonPreview.references" :key="`${reference.release_id}:${reference.instance_id}`"><code>{{ reference.release_id }} / {{ reference.instance_id }}</code> {{ t('· 代次') }} {{ reference.generation }} · {{ reference.initial_dirty ? t('原本待恢复') : t('需逐环境复验') }}<p class="hint">{{ reference.environment }}</p></li></ul>
              <p v-for="(blocker, index) in basePythonPreview.blockers" :key="index" class="gui-issue">{{ blocker }}</p>
              <p v-if="basePythonPreview.recovery_error" class="gui-issue">{{ basePythonPreview.recovery_error }}</p>
              <p v-if="basePythonPreview.pending_transaction" class="hint">{{ t('存在未完成的基础组件事务：') }}{{ basePythonPreview.pending_transaction }}</p>
              <details class="gui-file-details"><summary>{{ t('完整组件文件清单（{count}）', { count: basePythonPreview.expected_files.length.toLocaleString() }) }}</summary><pre tabindex="0" :aria-label="t('基础 Python 组件完整文件清单')">{{ basePythonPreview.expected_files.join('\n') }}</pre></details>
              <button v-if="basePythonPreview.repair_available" :disabled="mutationDisabled" @click="confirmBasePythonRepair()">{{ t('审查并恢复基础组件') }}</button>
              <button v-if="basePythonPreview.recovery_available" :disabled="mutationDisabled" @click="confirmBasePythonRepair(true)">{{ t('继续未完成组件恢复') }}</button>
            </template>
          </section>
          <section v-if="managedCurrent && (guiDiagnosis || (report && !report.environment))" class="gui-diagnostics" aria-labelledby="gui-diagnostics-title">
            <div class="section-caption"><h2 id="gui-diagnostics-title">{{ t('固定 GUI 依赖诊断与单包修复') }}</h2><button :disabled="mutationDisabled" @click="diagnoseManagedGui">{{ pending === t('只读诊断 GUI 依赖') ? t('正在诊断…') : t('只读诊断依赖') }}</button></div>
            <p class="hint">{{ t('诊断依据固定 wheel 的真实文件摘要。选择单个包后，先审查文件清单，再确认离线修复。请先停止运行中的训练器。') }}</p>
            <template v-if="guiDiagnosis">
              <dl class="gui-instance"><div><dt>{{ t('实例') }}</dt><dd><code>{{ guiDiagnosis.instance_id }}</code></dd></div><div><dt>{{ t('实例代次 / 登记代次') }}</dt><dd>{{ guiDiagnosis.generation }} / {{ guiDiagnosis.binding_generation }}</dd></div><div><dt>{{ t('状态') }}</dt><dd>{{ guiDiagnosis.dirty ? t('待恢复，禁止启动') : guiDiagnosis.recovery_pending ? t('存在待收尾修复记录') : guiDiagnosis.generation !== guiDiagnosis.binding_generation ? t('登记代次不一致') : t('可继续诊断') }}</dd></div></dl>
              <p v-if="guiDiagnosis.source_error" class="gui-issue" role="alert"><strong>{{ t('源码检查未通过') }}</strong>{{ guiDiagnosis.source_error }}</p>
              <p v-if="guiDiagnosis.installed_metadata_error" class="gui-issue" role="alert"><strong>{{ t('安装元数据检查未通过') }}</strong>{{ guiDiagnosis.installed_metadata_error }}</p>
              <div v-if="guiRecoveryNeeded" class="gui-recovery"><p>{{ t('存在未完成的修复或实例代次不一致。恢复会读取持久记录并重新验证；原快照已损坏时会保留待恢复状态。') }}</p><button :disabled="mutationDisabled" @click="confirmGuiRecovery">{{ t('恢复未完成修复') }}</button></div>
              <div class="gui-package-filter"><span>{{ guiDiagnosis.integrity.packages.length }} {{ t('个固定包 ·') }} {{ affectedPackages.length }} {{ t('个待处理') }}</span><label><input v-model="showAllPackages" type="checkbox" />{{ t('显示全部包') }}</label></div>
              <p v-if="!visiblePackages.length" class="scope-note">{{ t('固定包原文件和记录集合未发现缺坏。生成入口脚本只检查路径与存在性；解释器归属、pip check 与关键导入会在安装或修复验证时执行。') }}</p>
              <article v-for="item in visiblePackages" :key="item.name" class="gui-package" :aria-label="`${item.name} ${packageStatus(item)}`">
                <div class="gui-package-heading"><div><strong>{{ item.name }}</strong><code>{{ item.version }}</code><span>{{ packageStatus(item) }}</span></div><button :disabled="packagePlanDisabled(item)" @click="previewPackage(item)">{{ t('查看修复清单') }}</button></div>
                <p v-if="item.missing.length || item.damaged.length" class="hint">{{ t('缺失') }} {{ item.missing.length }} {{ t('项 · 内容或记录异常') }} {{ item.damaged.length }} {{ t('项') }}</p>
                <details v-if="item.missing.length" class="gui-file-details"><summary>{{ t('缺失文件（{count}）', { count: item.missing.length }) }}</summary><pre tabindex="0" :aria-label="t('{value0} 缺失文件完整路径', { value0: item.name })">{{ item.missing.join('\n') }}</pre></details>
                <details v-if="item.damaged.length" class="gui-file-details"><summary>{{ t('内容或记录异常（{count}）', { count: item.damaged.length }) }}</summary><pre tabindex="0" :aria-label="t('{value0} 异常文件完整路径', { value0: item.name })">{{ item.damaged.join('\n') }}</pre></details>
                <p v-for="(issue, index) in [...item.issues, ...item.unsupported]" :key="index" class="gui-issue">{{ issue }}</p>
                <p v-if="item.generated.some((file) => file.kind === 'optional_derived_bytecode_unverified' && file.present)" class="gui-issue">{{ t('发现未验证字节码。需要进一步诊断，固定无字节码运行合同禁止直接执行此环境。') }}</p>
                <p v-if="packagePlanDisabled(item) && !mutationDisabled" class="hint">{{ t('请先处理源码、元数据、文件记录异常或未完成的实例事务；单包修复清单由启动器重新验证后生成。') }}</p>
              </article>
              <section v-if="guiPreview" id="gui-repair-preview" class="gui-preview" aria-labelledby="gui-preview-title">
                <div class="section-caption"><h2 id="gui-preview-title">{{ t('待审修复清单：') }}{{ guiPreview.package }}</h2><button class="compact" :disabled="busy" @click="guiPreview = null">{{ t('关闭清单') }}</button></div>
                <p>{{ guiPreview.version }} {{ t('· 实例代次') }} {{ guiPreview.generation }} · {{ guiPreview.paths.length.toLocaleString() }} {{ t('个允许文件路径') }}</p>
                <p class="hint">{{ t('包含包原文件、安装器生成项、入口脚本及由原文件推导的可选缓存路径。生成路径进入清单不代表其内容已经验证。') }}</p>
                <p class="hint">{{ guiPreview.before_original_files_verified ? t('修复前原文件已通过静态检查，执行前会继续验证运行状态。') : t('修复前发现原文件缺坏，已阻止执行受影响环境；修复后再验证完整依赖与关键导入。') }}</p>
                <pre class="gui-paths" tabindex="0" :aria-label="t('单包修复完整允许路径清单')">{{ guiPreview.paths.join('\n') }}</pre>
                <button class="primary" :disabled="mutationDisabled || guiPlanBlocked" @click="confirmGuiRepair">{{ t('审查并确认修复此包') }}</button>
              </section>
              <p class="scope-note">{{ t('本次诊断只读取文件。固定包的原文件摘要与记录集合、安装器生成项的验证范围分别展示；诊断结果不代表训练器已健康启动。') }}</p>
            </template>
          </section>
          <template v-else-if="!currentVersion?.managed_recipe">
            <div class="environment-actions"><button :disabled="mutationDisabled" @click="command('bootstrap', t('准备基础工具'))">{{ t('准备基础工具') }}</button><button :disabled="mutationDisabled" @click="command('restore_trainer', t('恢复当前版本源码'))">{{ t('恢复当前版本源码') }}</button><button :disabled="mutationDisabled" @click="command('install_environment', t('安装或修复运行环境'))">{{ t('安装 / 修复运行环境') }}</button></div>
            <p class="hint">{{ t('源码恢复会将原目录移至备份；请留意日志中的路径和数据处理结果。运行中的训练器需先停止，才能安装或修复。') }}</p>
          </template>

        </div><p class="page-note"><Icon name="info" />{{ t('模型与训练任务在训练网页中管理。') }}<button class="text-button" @click="showLogs()">{{ t('查看环境日志') }}<Icon name="arrow" /></button></p>
      </section>
      <LogPanel v-show="page === 'logs'" :active="page === 'logs'" :entries="logs" :current-session-id="logSessionId" :root="path.trim()" :focus-request="logFocus" :font-size="appearance.logFontSize">
        <template #operation>
          <div v-if="report?.interrupted.length || history.some(item => item.status === 'interrupted')" class="operation-warning" role="region" :aria-label="t('未完成操作')"><Icon name="info" /><span>{{ t('存在未完成操作，请在环境管理中检查并恢复。') }}</span><button @click="page = 'environment'; advanced = true">{{ t('查看恢复') }}</button></div>
          <div v-if="operation?.status === 'running'" class="operation-monitor" role="region" :aria-label="t('当前安装与修复任务')"><div><strong>{{ t('当前操作') }}</strong><span>{{ phaseText[operation.phase] }} · {{ operation.cancel_requested ? t('正在取消，等待收尾') : operationStatusText[operation.status] }}</span></div><button data-action="cancel-operation" :disabled="operation.cancel_requested" @click="cancelCurrentOperation">{{ operation.cancel_requested ? t('正在收尾') : t('取消操作') }}</button></div>
          <div v-if="error" class="operation-error" role="alert"><span>{{ error }}</span><button class="icon-button" :aria-label="t('关闭错误提示')" @click="error = ''"><Icon name="close" /></button></div>
        </template>
      </LogPanel>
      <section v-show="page === 'settings'" class="settings-page" :aria-label="t('设置')"><nav class="settings-nav" :aria-label="t('设置分类')"><h1>{{ t('启动器设置') }}</h1><button v-for="item in ([{ id: 'general', icon: 'settings', label: t('常规') }, { id: 'appearance', icon: 'image', label: t('外观') }, { id: 'network', icon: 'network', label: t('网络') }, { id: 'profiles', icon: 'folder', label: t('用户资料') }, { id: 'security', icon: 'shield', label: t('安全与更新') }, { id: 'about', icon: 'info', label: t('关于') }] as const)" :key="item.id" :class="{ selected: setting === item.id }" :aria-current="setting === item.id ? 'page' : undefined" @click="openSetting(item.id)"><Icon :name="item.icon" />{{ item.label }}</button></nav><div class="settings-content">
        <section v-show="setting === 'general'" class="general-settings"><h2>{{ t('常规') }}</h2>
          <div class="setting-row"><h3>{{ t('语言') }}</h3><p class="setting-description">{{ t('选择启动器显示语言，更改后立即生效。') }}</p><AcrylicSelect :model-value="locale" :disabled="preferencesSaving" :aria-label="t('启动器语言')" :options="[{ value: 'zh-CN', label: t('简体中文') }, { value: 'en-US', label: 'English' }]" @update:model-value="updateLauncherPreference('language', $event)" /></div>
          <div class="setting-row"><h3>{{ t('关闭主窗口时') }}</h3><p class="setting-description">{{ t('最小化到系统托盘后，可通过托盘图标重新打开窗口；右键菜单可完全退出启动器。') }}</p><AcrylicSelect :model-value="closeToTray ? 'tray' : 'exit'" :disabled="preferencesSaving" :aria-label="t('关闭主窗口时')" :options="[{ value: 'tray', label: t('最小化到系统托盘') }, { value: 'exit', label: t('完全退出启动器') }]" @update:model-value="updateLauncherPreference('close_to_tray', $event === 'tray')" /></div>
          <p class="setting-description">{{ t('设置会自动保存在这台设备上。') }}</p>
          <p v-if="preferencesError" class="gui-issue" role="alert">{{ preferencesLoaded ? t('设置未能保存，请重试。') : t('无法读取启动器设置，暂时使用默认值。') }} {{ preferencesError }}<button :disabled="preferencesSaving" @click="readLauncherPreferences">{{ t('重新读取设置') }}</button></p>
        </section>
        <section v-show="setting === 'appearance'" class="appearance-settings"><h2>{{ t('外观') }}</h2><div class="setting-row"><h3>{{ t('背景图片') }}</h3><p class="setting-description">{{ t('默认使用项目 Qwen-Image-2.1 海报。可以选择本地图片，保存在这台设备上。') }}</p><input ref="backgroundInput" type="file" accept="image/png,image/jpeg,image/webp" hidden @change="chooseBackground" /><div class="actions"><button @click="backgroundInput?.click()"><Icon name="image" />{{ t('选择本地背景') }}</button><button :disabled="!appearance.background" @click="appearance.background = ''">{{ t('恢复默认') }}</button></div></div><div class="setting-row"><label for="background-mask">{{ t('亚克力着色强度') }} <span>{{ appearance.mask }}%</span></label><input id="background-mask" v-model.number="appearance.mask" type="range" min="0" max="80" /></div><div class="setting-row"><label for="background-blur">{{ t('亚克力模糊') }} <span>{{ appearance.blur }}px</span></label><input id="background-blur" v-model.number="appearance.blur" type="range" min="0" max="60" /></div><label class="switch-line"><input v-model="appearance.reduceMotion" type="checkbox" />{{ t('减少动态效果') }}</label><div class="setting-row"><label for="log-font-size">{{ t('日志字号') }}</label><AcrylicSelect :aria-label="t('日志字号')" id="log-font-size" v-model="appearance.logFontSize" :options="[12, 13, 14, 16, 18].map(size => ({ value: size, label: `${size} px` }))" /></div><p class="setting-description">{{ t('外观更改会自动保存。首页保留清晰海报，其他页面与侧栏使用连续的亚克力材质。') }}</p></section>
        <section v-show="setting === 'network'"><h2>{{ t('网络') }}</h2><section class="network-settings">

            <p class="hint">{{ t('自动模式按环境变量与系统代理选择连接方式。手动代理连接失败会报告错误；本机服务始终直接连接。') }}</p>
            <button class="compact" :disabled="busy || !sameRoot" @click="readNetworkSettings">{{ t('读取当前设置') }}</button>
            <template v-if="networkView">
              <label>{{ t('连接方式') }}<AcrylicSelect :aria-label="t('连接方式')" v-model="networkDraft.mode" :disabled="busy" :options="[{ value: 'auto', label: t('自动') }, { value: 'system', label: t('系统代理') }, { value: 'manual', label: t('手动代理') }, { value: 'direct', label: t('直接连接') }]" /></label>
              <template v-if="networkDraft.mode === 'manual' || networkDraft.mode === 'auto'">
                <label>{{ t('HTTP 代理') }}<input v-model="networkDraft.http_proxy" type="password" autocomplete="off" spellcheck="false" placeholder="http://127.0.0.1:11809" :disabled="busy" @input="editNetworkField('http_proxy')"><button :disabled="busy" @click="inheritNetworkField('http_proxy')">{{ t('恢复继承') }}</button></label>
                <label>{{ t('HTTPS 代理') }}<input v-model="networkDraft.https_proxy" type="password" autocomplete="off" spellcheck="false" :placeholder="t('手动模式可复用 HTTP 代理')" :disabled="busy" @input="editNetworkField('https_proxy')"><button :disabled="busy" @click="inheritNetworkField('https_proxy')">{{ t('恢复继承') }}</button></label>
              </template>
              <label v-if="networkDraft.mode !== 'direct'">{{ t('绕过代理') }}<input v-model="networkDraft.no_proxy" spellcheck="false" placeholder="example.org,10.0.0.0/8" :disabled="busy" @input="editNetworkField('no_proxy')"><button :disabled="busy" @click="inheritNetworkField('no_proxy')">{{ t('恢复继承') }}</button></label>
              <p class="hint">{{ t('自动模式中，清空已填写的代理会禁用对应协议的代理；“恢复继承”会重新采用环境或系统设置。未编辑的空值设置会原样保留。') }}</p>
              <p class="hint">{{ t('生效来源：') }}{{ ({ environment: t('环境变量'), system: t('系统设置'), manual: t('手动设置'), direct: t('直接连接') } as Record<string, string>)[networkView.diagnostic.source] ?? networkView.diagnostic.source }}。{{ networkView.diagnostic.warning }}</p>
              <p class="hint">{{ t('设置仅保存在当前安装目录；修改后用于后续操作。代理凭据会保存在本机，日志中的代理地址会隐藏凭据。') }}</p>
              <button :disabled="mutationDisabled" @click="storeNetworkSettings">{{ t('保存网络设置') }}</button>
            </template>
          </section></section>
        <section v-show="setting === 'profiles'"><h2>{{ t('用户资料') }}</h2><p class="setting-description">{{ t('训练器版本与用户资料独立保存。更换安装目录前请先停止当前服务。') }}</p><section class="directory-panel" aria-labelledby="directory-label"><label id="directory-label" for="install-root">{{ t('安装目录') }}</label><div class="directory-input"><input id="install-root" v-model="path" :disabled="busy || running || transitioning" :placeholder="t('首次检查将使用默认目录')" spellcheck="false" @keydown.enter="refreshInstallation()" /><button :disabled="busy || running || transitioning" @click="browse">{{ t('选择…') }}</button><button :disabled="busy || transitioning" @click="refreshInstallation()">{{ t('刷新') }}</button></div></section><section v-if="profilePath && sameRoot" class="profile-info"><span>{{ t('当前共享用户资料') }}</span><code>{{ profilePath }}</code></section><ImportPanel v-if="sameRoot && activeManagedRelease" :root="path.trim()" :release-id="activeManagedRelease.id" :disabled="mutationDisabled" @operate="startGuiOperation" /></section>
        <section v-show="setting === 'security'"><h2>{{ t('安全与更新') }}</h2><TrustPanel v-if="sameRoot && activeManagedRelease" :root="path.trim()" :release-id="activeManagedRelease.id" :disabled="mutationDisabled" @changed="command('inspect', t('刷新发布清单'))" /><ShellPanel v-if="sameRoot && activeManagedRelease" :root="path.trim()" :release-id="activeManagedRelease.id" :disabled="mutationDisabled" /><p v-else class="setting-description">{{ t('检查安装目录并选择训练器版本后，可管理更新来源与启动器恢复。') }}</p></section>
        <section v-show="setting === 'about'" class="about-page"><img class="about-symbol" src="/assets/home-logo.webp" :alt="t('Next Trainer 项目标志')" /><h2>Next Trainer</h2><p class="setting-description">{{ t('桌面启动器') }}</p><p class="about-version">{{ t('启动器') }} {{ appVersion }}<br />{{ t('训练器') }} {{ currentVersion?.version ?? report?.version ?? t('尚未选择') }}<span v-if="currentVersion"> · {{ currentVersion.commit.slice(0, 8) }}</span></p><p class="setting-description">{{ t('独立环境、集中日志，让创作从容开始。') }}</p><div class="setting-links"><button class="text-button" @click="openProjectLink('project')">{{ t('项目主页 ↗') }}</button><button class="text-button" @click="openProjectLink('issues')">{{ t('问题反馈 ↗') }}</button><button class="text-button" @click="openProjectLink('license')">{{ t('开源许可 ↗') }}</button></div><p class="setting-description">{{ t('界面布局参考 Starward（星穹启动器）。默认背景与品牌使用本项目资源。') }}</p></section>
      </div></section>

    </main>
    <div v-if="toast" class="toast" role="status">{{ toast }}</div>
        <MainReinstallDialog v-if="mainReinstall" :legacy-repair="mainReinstall.kind === 'legacy-repair'" :phase="mainReinstall.phase" :root="mainReinstall.root" :version="mainReinstall.version" :reason="mainReinstall.reason" :progress="mainReinstall.query?.snapshot?.progress.message || queryStageLabel(mainReinstall.query?.snapshot?.stage ?? '')" :shared="mainReinstall.query?.shared ?? false" :connection-error="Boolean(mainReinstall.query?.connectionError)" :download="formatFileSize(mainReinstall.preview?.plan?.estimated_network_bytes ?? 0)" @cancel="closeMainReinstall" @confirm="confirmMainReinstall" />
        <div v-if="confirmation" class="dialog-backdrop" @keydown.esc.prevent="dismissConfirmation" @keydown="trapDialogFocus"><section class="confirmation-dialog" :class="{ 'gui-confirmation': confirmation.paths }" role="dialog" aria-modal="true" aria-labelledby="confirmation-title" aria-describedby="confirmation-detail"><h2 id="confirmation-title">{{ confirmation.title }}</h2><p id="confirmation-detail">{{ confirmation.detail }}</p><pre v-if="confirmation.paths" class="gui-paths" tabindex="0" :aria-label="t('确认修复的完整文件清单')">{{ confirmation.paths.join('\n') }}</pre><div><button ref="confirmationCancel" @click="dismissConfirmation">{{ t('取消') }}</button><button :class="confirmation.destructive ? 'danger' : 'primary'" :data-action="confirmation.actionId" @click="confirmAction">{{ confirmation.action }}</button></div></section></div>
  </div>
</template>
