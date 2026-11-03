import { computed, shallowReactive, shallowRef, watch } from 'vue'
import { invoke } from '@tauri-apps/api/core'
import { t } from './i18n'

export type EngineQueryAction = 'capabilities' | 'recipe' | 'inspect_readonly' | 'plan_install' | 'plan_repair' | 'preview_gui_rebuild'
export type EngineQueryScope = 'full' | 'files_only' | 'plan'
export interface EngineQueryTarget {
  root: string
  release_id: string
  engine_id: string
  action: EngineQueryAction
  rebuild: boolean
  scope: EngineQueryScope
}
export interface EngineQueryIdentity {
  target: EngineQueryTarget
  workspace_fence: string
  instance_id: string | null
  generation: number | null
  state_sha256: string | null
  receipt_sha256: string | null
  binding_sha256: string | null
  lock_sha256: string
  recipe_sha256: string
}
export type EngineQueryStatus = 'resolving' | 'queued' | 'running' | 'cancelling' | 'succeeded' | 'cancelled' | 'timed_out' | 'failed' | 'interrupted' | 'stale'
export interface EngineQuerySnapshot {
  schema_version: number
  task_id: string
  canonical_task_id: string
  target: EngineQueryTarget
  identity: EngineQueryIdentity | null
  status: EngineQueryStatus
  stage: string
  validity: 'unresolved' | 'current' | 'stale'
  cancel_requested: boolean
  event_seq: number
  started_at_ms: number
  updated_at_ms: number
  deadline_at_ms: number
  progress: { files: number | null; bytes: number | null; total_files: number | null; total_bytes: number | null; message: string }
  result_available: boolean
  error: { code: string; message: string } | null
  subscriber_count: number
}
interface QueryAcceptance {
  task_id: string
  canonical_task_id: string
  subscription_id: string
  shared: boolean
  snapshot: EngineQuerySnapshot
}
export interface EngineQueryEntry {
  id: number
  target: EngineQueryTarget
  taskId: string | null
  snapshot: EngineQuerySnapshot | null
  result: unknown
  finished: boolean
  shared: boolean
  error: string
  connectionError: string
  cancelling: boolean
  cancelError: string
  invalidated: boolean
}
interface Tracking {
  subscriptionId: string | null
  polling: boolean
  nextPollAt: number
  failures: number
}

// This module owns one subscription per accepted task for the application, not
// per page. Leaving/unmounting a page never cancels a shared check. Its progress
// remains observable in Logs and when the engine page is opened again.
const entries = shallowRef<EngineQueryEntry[]>([])
const tracking = new Map<number, Tracking>()
const admissions = new Map<string, Promise<EngineQueryEntry>>()
const terminal = new Set<EngineQueryStatus>(['succeeded', 'cancelled', 'timed_out', 'failed', 'interrupted', 'stale'])
const MAX_ACTIVE = 4, MAX_RETAINED = 32
let nextId = 0
let timer: ReturnType<typeof setTimeout> | undefined
let polling = false
export const engineQueries = computed(() => entries.value)
export const engineQueryRoot = (root: string) => root.trim().replace(/\\/g, '/').replace(/\/+$/, '').toLocaleLowerCase('en-US')
const sameTarget = (left: EngineQueryTarget, right: EngineQueryTarget) => engineQueryRoot(left.root) === engineQueryRoot(right.root) && left.release_id === right.release_id && left.engine_id === right.engine_id && left.action === right.action && left.rebuild === right.rebuild && left.scope === right.scope
const targetKey = (target: EngineQueryTarget) => JSON.stringify([engineQueryRoot(target.root), target.release_id, target.engine_id, target.action, target.rebuild, target.scope])
const cancellationPending = (entry: EngineQueryEntry) => !entry.finished && (entry.cancelling || entry.snapshot?.cancel_requested || entry.snapshot?.status === 'cancelling')

/** A closing preparation cannot be reused while its authoritative task drains. */
export function assertEngineQueryNotCancelling(entry: EngineQueryEntry): void {
  if (cancellationPending(entry)) throw Error(t('上一次检查正在取消，请稍候再试。'))
}

export function sameEngineQueryIdentity(left: EngineQueryIdentity | null, right: EngineQueryIdentity | null): boolean {
  if (!left || !right) return false
  return engineQueryRoot(left.target.root) === engineQueryRoot(right.target.root) && left.target.release_id === right.target.release_id && left.target.engine_id === right.target.engine_id &&
    (['workspace_fence', 'instance_id', 'generation', 'state_sha256', 'receipt_sha256', 'binding_sha256', 'lock_sha256', 'recipe_sha256'] as const).every(key => left[key] === right[key])
}

/** A mutation invalidates displayed checks as well as cached plans immediately. */
export function invalidateEngineQueryResults(root: string, releaseId: string, engineId?: string) {
  for (const entry of entries.value) {
    if (engineQueryRoot(entry.target.root) === engineQueryRoot(root) && entry.target.release_id === releaseId && (!engineId || entry.target.engine_id === engineId)) entry.invalidated = true
  }
}

function acceptSnapshot(entry: EngineQueryEntry, snapshot: EngineQuerySnapshot) {
  if (snapshot.schema_version !== 1 || snapshot.task_id !== entry.taskId || !sameTarget(snapshot.target, entry.target)) throw Error(t('检查响应与当前目标不一致，请重新检查。'))
  const previous = entry.snapshot
  // An alias may join a canonical task whose event sequence starts lower. Only
  // compare sequence numbers within the same canonical stream.
  if (previous?.canonical_task_id === snapshot.canonical_task_id && snapshot.event_seq < previous.event_seq) return
  entry.snapshot = snapshot
  if (snapshot.cancel_requested || snapshot.status === 'cancelling' || terminal.has(snapshot.status)) entry.cancelError = ''
  // Sharing can be discovered after admission when a resolver joins another
  // canonical task. Keep the warning once shown, even if other views leave.
  entry.shared ||= snapshot.canonical_task_id !== snapshot.task_id || snapshot.subscriber_count > 1
}

async function release(entry: EngineQueryEntry) {
  const state = tracking.get(entry.id)
  const subscriptionId = state?.subscriptionId
  if (!state || !subscriptionId || !entry.taskId) return
  state.subscriptionId = null
  try { await invoke('leave_engine_query', { taskId: entry.taskId, subscriptionId }) }
  catch { /* The bounded backend subscription expires; leave never cancels. */ }
}

function schedule(delay = 250) {
  if (timer || polling || !entries.value.some(entry => !entry.finished && entry.taskId)) return
  timer = setTimeout(() => { timer = undefined; void poll() }, delay)
}

async function pollEntry(entry: EngineQueryEntry) {
  const state = tracking.get(entry.id)
  if (!state || state.polling || entry.finished || !entry.taskId || Date.now() < state.nextPollAt) return
  state.polling = true
  try {
    if (!state.subscriptionId) {
      const joined = await invoke<QueryAcceptance>('join_engine_query', { taskId: entry.taskId })
      state.subscriptionId = joined.subscription_id
      acceptSnapshot(entry, joined.snapshot)
    }
    let snapshot: EngineQuerySnapshot
    try {
      snapshot = await invoke<EngineQuerySnapshot>('engine_query_snapshot', { taskId: entry.taskId, subscriptionId: state.subscriptionId })
    } catch (reason) {
      if (String(reason).includes('query_subscription_expired')) state.subscriptionId = null
      throw reason
    }
    acceptSnapshot(entry, snapshot)
    entry.connectionError = ''; state.failures = 0
    if (entry.snapshot && terminal.has(entry.snapshot.status)) {
      if (entry.snapshot.status === 'succeeded' && entry.snapshot.result_available && entry.snapshot.validity === 'current') {
        const completed = await invoke<{ snapshot: EngineQuerySnapshot; result: unknown }>('engine_query_result', { taskId: entry.taskId })
        acceptSnapshot(entry, completed.snapshot)
        if (entry.snapshot.status === 'succeeded' && entry.snapshot.validity === 'current' && entry.snapshot.result_available && completed.result !== null) entry.result = completed.result
        else entry.error = t('检查结果已变化，请重新检查。')
      } else entry.error = entry.snapshot.error?.message || (entry.snapshot.status === 'succeeded' ? t('检查结果已变化，请重新检查。') : queryStatusLabel(entry.snapshot.status))
      entry.cancelError = ''; entry.finished = true
      await release(entry)
    }
    state.nextPollAt = Date.now() + 250
  } catch (reason) {
    // A transport failure is not a backend terminal state. Keep observing the
    // original task, with bounded backoff, rather than launching a second scan.
    entry.connectionError = String(reason)
    if (String(reason).includes('query_expired')) {
      entry.error = t('检查记录已过期，请重新检查。'); entry.cancelError = ''; entry.finished = true
      await release(entry)
      return
    }
    state.failures = Math.min(state.failures + 1, 5)
    state.nextPollAt = Date.now() + Math.min(5000, 250 * 2 ** state.failures)
  } finally { state.polling = false }
}

async function poll() {
  if (polling) return
  polling = true
  try { await Promise.allSettled(entries.value.filter(entry => !entry.finished && entry.taskId).slice(0, MAX_ACTIVE).map(pollEntry)) }
  finally { polling = false; schedule() }
}

function prune() {
  const removed = entries.value.filter(entry => entry.finished).slice(0, Math.max(0, entries.value.length - MAX_RETAINED + 1))
  const ids = new Set(removed.map(entry => entry.id))
  entries.value = entries.value.filter(entry => !ids.has(entry.id))
  for (const id of ids) tracking.delete(id)
}

export async function beginEngineQuery(target: EngineQueryTarget): Promise<EngineQueryEntry> {
  // Include invalidated entries: losing permission to apply a plan does not
  // release the cancelling worker or permit a parallel replacement scan.
  const cancelling = entries.value.find(entry => sameTarget(entry.target, target) && cancellationPending(entry))
  if (cancelling) assertEngineQueryNotCancelling(cancelling)
  const active = entries.value.find(entry => !entry.finished && !entry.invalidated && sameTarget(entry.target, target))
  const key = targetKey(target), pending = admissions.get(key)
  if (pending) {
    // Mark before awaiting admission so the initial shared=false response cannot
    // erase that another local view is already using this preparation.
    if (active) active.shared = true
    return pending
  }
  if (active) { active.shared = true; return active }
  if (entries.value.filter(entry => !entry.finished).length >= MAX_ACTIVE) throw Error(t('已有检查正在进行，请等待或取消后重试。'))
  prune()
  const entry = shallowReactive<EngineQueryEntry>({ id: ++nextId, target: { ...target }, taskId: null, snapshot: null, result: undefined, finished: false, shared: false, error: '', connectionError: '', cancelling: false, cancelError: '', invalidated: false })
  entries.value = [...entries.value, entry]
  tracking.set(entry.id, { subscriptionId: null, polling: false, nextPollAt: 0, failures: 0 })
  const admission = (async () => {
    try {
      const accepted = target.action === 'preview_gui_rebuild'
        ? await invoke<QueryAcceptance>('begin_gui_rebuild_preview', { root: target.root, releaseId: target.release_id, timeoutSeconds: 1800 })
        : await invoke<QueryAcceptance>('begin_engine_query', { root: target.root, releaseId: target.release_id, engineId: target.engine_id, action: target.action, rebuild: target.rebuild, scope: target.scope, timeoutSeconds: 1800 })
      entry.taskId = accepted.task_id; entry.shared ||= accepted.shared
      tracking.get(entry.id)!.subscriptionId = accepted.subscription_id
      acceptSnapshot(entry, accepted.snapshot)
      schedule(0)
      // The dialog may have closed before IPC admission returned its task ID.
      // Keep that cancellation intent and stop this accepted task once only.
      if (entry.cancelling) void requestCancellation(entry).catch(() => { /* Reported on the entry; polling continues. */ })
      return entry
    } catch (reason) {
      entry.error = String(reason); entry.cancelError = ''; entry.finished = true
      await release(entry)
      throw reason
    } finally { admissions.delete(key) }
  })()
  admissions.set(key, admission)
  return admission
}

export async function waitEngineQuery<T>(entry: EngineQueryEntry): Promise<{ result: T; snapshot: EngineQuerySnapshot }> {
  if (!entry.finished) await new Promise<void>(resolve => {
    const stop = watch(() => entry.finished, value => { if (value) { stop(); resolve() } }, { flush: 'sync' })
  })
  const snapshot = entry.snapshot
  if (entry.invalidated || entry.error || !snapshot || snapshot.status !== 'succeeded' || snapshot.validity !== 'current' || !snapshot.identity || entry.result === undefined) throw Error(entry.error || t('检查结果已变化，请重新检查。'))
  return { result: entry.result as T, snapshot }
}

async function requestCancellation(entry: EngineQueryEntry): Promise<void> {
  try {
    await invoke<'accepted' | 'already_requested' | 'already_terminal'>('cancel_engine_query', { taskId: entry.taskId })
    entry.cancelError = ''
  } catch (reason) {
    // A missing acknowledgement cannot revoke the user's cancellation intent:
    // the backend may already have received it. Keep the task fenced until its
    // authoritative terminal state, and allow an explicit retry if still needed.
    if (!entry.finished && !entry.snapshot?.cancel_requested && entry.snapshot?.status !== 'cancelling' && (!entry.snapshot || !terminal.has(entry.snapshot.status))) entry.cancelError = String(reason)
    throw reason
  } finally {
    const state = tracking.get(entry.id)
    if (state) state.nextPollAt = 0
    schedule(0)
  }
}

export async function cancelEngineQuery(entry: EngineQueryEntry): Promise<void> {
  if (entry.finished || entry.snapshot?.cancel_requested || entry.snapshot?.status === 'cancelling' || (entry.snapshot && terminal.has(entry.snapshot.status)) || (entry.cancelling && !entry.cancelError)) return
  entry.cancelling = true
  entry.cancelError = ''
  if (entry.taskId) await requestCancellation(entry)
}

/** Records cancellation immediately, including while admission has no task ID. */
export async function cancelEngineQueryTarget(target: EngineQueryTarget): Promise<void> {
  await Promise.all(entries.value.filter(entry => !entry.finished && sameTarget(entry.target, target)).map(cancelEngineQuery))
}

export function queryStatusLabel(status: EngineQueryStatus): string {
  return t({ resolving: '正在准备检查', queued: '等待检查', running: '正在检查…', cancelling: '正在取消并回收检查进程…', succeeded: '检查完成', cancelled: '检查已取消', timed_out: '检查超时，请重试', failed: '检查失败', interrupted: '检查已中断', stale: '检查结果已变化，请重新检查。' }[status])
}

export function queryStageLabel(stage: string): string {
  return t(({ identity: '核对安装记录', queued: '等待检查', python: '校验基础解释器', tools: '校验检查工具', worker: '启动检查进程', receipt: '读取安装清单', environment: '核对依赖文件', source: '核对训练源码', extra_files: '核对额外文件', reaping: '回收检查进程', complete: '检查完成' } as Record<string, string>)[stage] ?? '正在准备检查')
}
