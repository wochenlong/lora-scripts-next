<script setup lang="ts">
import { t } from './i18n'
import { computed, nextTick, ref, watch } from 'vue'
import { invoke } from '@tauri-apps/api/core'
import type { OperationSnapshot } from './bridge'
import { formatBytes } from './localized-bytes'
import Icon from './LauncherIcon.vue'

const props = defineProps<{ root: string; releaseId: string; disabled: boolean; applyDisabled: boolean; refreshToken?: string }>()
const emit = defineEmits<{ operate: [label: string, action: () => Promise<OperationSnapshot>] }>()
type Issue = { message?: string; path?: string; kind?: string; code?: string; package?: string; unexpected?: boolean }
type Plan = { plan_sha256: string; engine_id: string; release_id: string; kind: string; instance_id: string; download_bytes: number; packages: string[]; source_paths: string[]; write_roots: string[]; issues: Issue[]; status: string; rebuild?: boolean }
type Inspection = { activity?: { busy: boolean; kind?: string; message?: string }; installation: string; instance_id?: string; generation?: number; dirty?: boolean; state?: { instance_id?: string; generation?: number; dirty?: boolean; pending?: unknown }; actions?: string[]; issues: Issue[]; layout?: { environment_root?: string; engine_source_root?: string; profile_root?: string } }
type Confirmation = 'install' | 'repair' | 'rebuild' | 'recover' | 'probe'
const engines = [
  { id: 'kohya', name: 'Kohya', emblem: 'K', description: 'SD · SDXL · LoRA 与全量微调', style: 'kohya' },
  { id: 'anima-fast', name: 'Anima Fast', emblem: 'A', description: 'Anima 模型训练环境', style: 'anima' },
  { id: 'ai-toolkit', name: 'AI Toolkit', emblem: 'AI', description: '多模型训练工作流', style: 'toolkit' },
  { id: 'diffsynth', name: 'DiffSynth', emblem: 'D', description: 'DiffSynth 模型训练环境', style: 'diffsynth' },
]
const selected = ref('kohya'), inspections = ref<Record<string, Inspection>>({}), plan = ref<Plan | null>(null)
const querying = ref(''), error = ref(''), notice = ref(''), expanded = ref(false), advanced = ref(false), confirmation = ref<Confirmation | null>(null)
const cancelButton = ref<HTMLButtonElement>()
const inspection = computed(() => inspections.value[selected.value])
const engineName = computed(() => engines.find(engine => engine.id === selected.value)?.name ?? selected.value)
const hasAnomaly = (value?: Inspection) => Boolean(value?.dirty || value?.state?.dirty || value?.state?.pending || ['pending', 'dirty'].includes(value?.installation ?? ''))
const canRecover = (value?: Inspection) => hasAnomaly(value) && Boolean(value?.state?.pending || value?.actions?.includes('recover') || value?.installation === 'pending')
const targetBusy = computed(() => Boolean(inspection.value?.activity?.busy))
const stateName = (value?: Inspection) => value?.activity?.busy ? t('正在使用') : hasAnomaly(value) ? t('安装异常') : t({ ready: '检查通过', missing: '尚未安装', damaged: '需要修复', broken: '需要修复', unknown: '无法确认' }[value?.installation ?? ''] ?? '待检查')
const primaryName = (value?: Inspection) => hasAnomaly(value) ? t('处理安装异常') : value?.installation === 'missing' ? t('安装') : t('检查并修复')
const confirmTitle = computed(() => t({ install: '安装 {name}', repair: '修复 {name}', rebuild: '重新安装 {name}', recover: '处理 {name} 安装异常', probe: '运行 {name} 检查' }[confirmation.value ?? 'install'], { name: engineName.value }))
const confirmAction = computed(() => t({ install: '确认安装', repair: '确认修复', rebuild: '确认重新安装', recover: '确认处理', probe: '确认运行检查' }[confirmation.value ?? 'install']))
const operationTargets = new Map<string, { root: string; release: string; engine: string }>()
let epoch = 0
let previousFocus: HTMLElement | null = null
function resetSelection() { epoch++; querying.value = ''; plan.value = null; confirmation.value = null; previousFocus = null; error.value = ''; notice.value = '' }
watch(() => [props.root, props.releaseId], () => { resetSelection(); inspections.value = {}; expanded.value = false; advanced.value = false; operationTargets.clear() }, { flush: 'sync' })
watch(selected, resetSelection, { flush: 'sync' })
watch(() => props.refreshToken, (token) => {
  if (!token || token.endsWith(':running')) return
  for (const [id, target] of operationTargets) {
    if (!token.startsWith(`${id}:`) || target.root !== props.root || target.release !== props.releaseId) continue
    operationTargets.delete(id); delete inspections.value[target.engine]
    if (selected.value === target.engine && !props.disabled) void checkEngine(target.engine, true)
  }
})
function context() {
  const serial = ++epoch, root = props.root, releaseId = props.releaseId, engineId = selected.value
  return { root, releaseId, engineId, current: () => serial === epoch && root === props.root && releaseId === props.releaseId && engineId === selected.value }
}
async function readInspection(ctx: ReturnType<typeof context>) {
  const value = await invoke<Inspection>('query_engine_control', { root: ctx.root, releaseId: ctx.releaseId, engineId: ctx.engineId, action: 'inspect_readonly', rebuild: false })
  if (ctx.current()) inspections.value[ctx.engineId] = value
  return value
}
function showConfirmation(value: Confirmation, returnFocus: HTMLElement | null) { previousFocus = returnFocus; confirmation.value = value }
// The dialog is rendered while inspection still disables its buttons. Wait for
// the query to finish and Vue to enable Cancel before assigning initial focus.
watch([confirmation, querying], ([value, pending]) => {
  if (value && !pending) cancelButton.value?.focus({ preventScroll: true })
}, { flush: 'post' })
function dismiss() {
  if (querying.value) return
  const returnFocus = previousFocus
  confirmation.value = null; plan.value = null; previousFocus = null
  void nextTick(() => {
    if (!confirmation.value && returnFocus?.isConnected && !returnFocus.matches(':disabled')) returnFocus.focus({ preventScroll: true })
  })
}
async function checkEngine(id: string, readonly = false, rebuild = false) {
  if (props.disabled || querying.value === id) return
  const returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
  selected.value = id
  const ctx = context(); querying.value = id; error.value = ''; notice.value = ''; plan.value = null; confirmation.value = null; expanded.value = true
  try {
    const value = await readInspection(ctx)
    if (!ctx.current()) return
    if (readonly) { notice.value = value.installation === 'ready' && !hasAnomaly(value) ? t('检查通过') : ''; return }
    if (rebuild) {
      const reviewed = await invoke<Plan>('query_engine_control', { root: ctx.root, releaseId: ctx.releaseId, engineId: id, action: 'plan_install', rebuild: true })
      if (ctx.current()) { plan.value = reviewed; showConfirmation('rebuild', returnFocus) }
      return
    }
    if (hasAnomaly(value)) {
      if (canRecover(value)) showConfirmation('recover', returnFocus)
      else notice.value = t('安装记录异常，请查看问题详情；无法回滚时可在高级选项中重新安装环境。')
      return
    }
    if (value.installation === 'ready') { notice.value = t('检查通过'); return }
    const action = value.installation === 'missing' ? 'plan_install' : ['damaged', 'broken'].includes(value.installation) ? 'plan_repair' : null
    if (!action) { notice.value = t('无法自动修复当前状态，请查看问题详情后使用高级选项。'); return }
    const reviewed = await invoke<Plan>('query_engine_control', { root: ctx.root, releaseId: ctx.releaseId, engineId: id, action, rebuild: false })
    if (!ctx.current()) return
    if (reviewed.engine_id !== id || reviewed.release_id !== ctx.releaseId || !reviewed.plan_sha256) throw Error(t('检查结果已变化，请重新检查。'))
    plan.value = reviewed
    showConfirmation(action === 'plan_install' ? 'install' : 'repair', returnFocus)
  } catch (reason) { if (ctx.current()) error.value = String(reason) }
  finally { if (ctx.current()) querying.value = '' }
}
async function requestProbe() {
  if (props.disabled || querying.value) return
  const returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
  const ctx = context(); querying.value = ctx.engineId; error.value = ''
  try { const value = await readInspection(ctx); if (ctx.current() && value.installation === 'ready' && !hasAnomaly(value)) showConfirmation('probe', returnFocus); else if (ctx.current()) notice.value = t('请先安装或修复环境，再运行检查。') }
  catch (reason) { if (ctx.current()) error.value = String(reason) }
  finally { if (ctx.current()) querying.value = '' }
}
async function apply() {
  const action = confirmation.value, reviewed = plan.value
  if (!action || props.applyDisabled || props.disabled || querying.value) return
  const ctx = context(); querying.value = ctx.engineId; error.value = ''
  try {
    const value = await readInspection(ctx)
    if (!ctx.current()) return
    if (props.applyDisabled || value.activity?.busy) { notice.value = value.activity?.message || t('该引擎正在使用或变更，暂不可修改。'); return }
    if (action === 'recover' && !canRecover(value)) throw Error(t('安装状态已变化，请重新检查后再处理。'))
    if (action !== 'recover' && action !== 'probe' && (!reviewed || reviewed.engine_id !== ctx.engineId || reviewed.release_id !== ctx.releaseId)) throw Error(t('检查结果已变化，请重新检查。'))
    if ((action === 'install' || action === 'repair' || action === 'probe') && hasAnomaly(value)) throw Error(t('安装状态已变化，请重新检查后再处理。'))
    confirmation.value = null; plan.value = null
    emit('operate', confirmTitleFor(action, engineName.value), async () => {
      if (!ctx.current() || props.applyDisabled || props.disabled) throw Error(t('检查结果已变化，请重新检查。'))
      const result = await invoke<OperationSnapshot>('apply_engine_control', { root: ctx.root, releaseId: ctx.releaseId, engineId: ctx.engineId, action: action === 'recover' ? 'recover' : action === 'probe' ? 'probe_execute' : 'repair_apply', plan: action === 'recover' || action === 'probe' ? null : reviewed })
      if (ctx.current()) { delete inspections.value[ctx.engineId]; notice.value = t('操作已开始，可在日志中查看进度。') }
      operationTargets.set(result.id, { root: ctx.root, release: ctx.releaseId, engine: ctx.engineId })
      return result
    })
  } catch (reason) { if (ctx.current()) error.value = String(reason) }
  finally { if (ctx.current()) querying.value = '' }
}
function confirmTitleFor(action: Confirmation, name: string) { return t({ install: '正在安装 {name}', repair: '正在修复 {name}', rebuild: '正在重新安装 {name}', recover: '正在处理 {name} 安装异常', probe: '正在运行 {name} 检查' }[action], { name }) }
function trapDialogFocus(event: KeyboardEvent) {
  if (event.key !== 'Tab') return
  const dialog = (event.currentTarget as HTMLElement).querySelector('[role="dialog"]')
  const controls = Array.from(dialog?.querySelectorAll<HTMLElement>('button:not(:disabled), summary, [tabindex="0"]') ?? [])
  const first = controls[0], last = controls.at(-1)
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
}
</script>

<template>
  <section class="engine-list" :aria-label="t('四个训练引擎独立环境')">
    <article v-for="engine in engines" :key="engine.id" class="engine-row" :data-engine="engine.id">
      <div class="engine-emblem" :class="engine.style">{{ engine.emblem }}</div>
      <div class="engine-copy"><h2>{{ engine.name }}<span class="engine-state" :class="{ good: inspections[engine.id]?.installation === 'ready' && !hasAnomaly(inspections[engine.id]) }">{{ querying === engine.id ? t('正在检查…') : stateName(inspections[engine.id]) }}</span></h2><p>{{ t(engine.description) }}</p><p v-if="inspections[engine.id]?.activity?.busy" class="engine-busy" role="status">{{ inspections[engine.id]?.activity?.message || t('该引擎正在使用或变更，暂不可修改。') }}</p></div>
      <div class="engine-actions"><button :disabled="disabled || querying === engine.id" @click="checkEngine(engine.id)"><Icon v-if="querying === engine.id" name="refresh" class="spin" />{{ querying === engine.id ? t('正在检查…') : primaryName(inspections[engine.id]) }}</button></div>
    </article>
    <div v-if="expanded" class="engine-management">
      <div class="section-caption"><h2>{{ t('{name} · 检查结果', { name: engineName }) }}</h2><button class="text-button" :disabled="Boolean(querying)" @click="expanded = false; advanced = false">{{ t('收起') }}</button></div>
      <p v-if="notice" class="engine-notice" role="status">{{ notice }}</p><p v-if="error" role="alert" class="gui-issue">{{ error }}</p>
      <p v-if="targetBusy" class="gui-issue">{{ inspection?.activity?.message || t('该引擎正在使用或变更，暂不可修改。') }} {{ t('只读检查仍可进行，执行前会再次确认占用状态。') }}</p>
      <ul v-if="inspection?.issues?.length" class="engine-issues"><li v-for="(issue, index) in inspection.issues.slice(0, 5)" :key="index">{{ issue.message ?? issue.path ?? issue.kind ?? issue.code }}</li></ul>
      <details :open="advanced" @toggle="advanced = ($event.target as HTMLDetailsElement).open"><summary>{{ t('高级选项') }}</summary><p class="hint">{{ t('运行检查会启动该引擎的独立解释器；重新安装会创建新环境，原环境按恢复记录保留。') }}</p><div class="actions"><button :disabled="disabled || Boolean(querying)" @click="checkEngine(selected, true)">{{ t('仅检查文件') }}</button><button :disabled="disabled || Boolean(querying)" @click="checkEngine(selected, false, true)">{{ t('重新安装环境') }}</button><button :disabled="disabled || Boolean(querying) || inspection?.installation !== 'ready' || hasAnomaly(inspection)" @click="requestProbe">{{ t('运行检查') }}</button></div><p v-if="inspection?.layout?.environment_root" class="hint">{{ t('环境路径：') }}<code>{{ inspection.layout.environment_root }}</code></p><p v-if="inspection?.state?.instance_id || inspection?.instance_id" class="hint">{{ t('独立实例 {id}', { id: inspection?.state?.instance_id ?? inspection?.instance_id ?? '' }) }}<span v-if="inspection?.state?.generation !== undefined || inspection?.generation !== undefined"> · {{ t('代次 {count}', { count: inspection?.state?.generation ?? inspection?.generation ?? 0 }) }}</span></p><ul v-if="inspection?.issues?.length > 5" class="engine-issues"><li v-for="(issue, index) in inspection?.issues.slice(5)" :key="index">{{ issue.message ?? issue.path ?? issue.kind ?? issue.code }}</li></ul></details>
    </div>
    <div v-if="confirmation" class="engine-confirm-backdrop" @keydown.esc.prevent="dismiss" @keydown="trapDialogFocus"><section class="engine-confirm" role="dialog" aria-modal="true" aria-labelledby="engine-confirm-title" aria-describedby="engine-confirm-description"><h2 id="engine-confirm-title">{{ confirmTitle }}</h2><template v-if="confirmation === 'recover'"><p id="engine-confirm-description">{{ t('将核对未完成操作并尝试回滚到此前已验证的环境。此操作不会继续下载；首次安装没有可回滚环境时，会保留现场，需要重新安装。') }}</p></template><template v-else-if="confirmation === 'probe'"><p id="engine-confirm-description">{{ t('将启动独立解释器检查依赖能否载入，不进行训练，也不验证模型或显存。') }}</p></template><template v-else><p id="engine-confirm-description">{{ confirmation === 'repair' ? t('仅修复本次检查发现的缺损。') : confirmation === 'rebuild' ? t('创建新的独立环境，保留原环境的恢复记录。') : t('为该训练引擎安装独立环境。') }}</p><p class="engine-download">{{ t('需要下载 {bytes}', { bytes: formatBytes(plan?.download_bytes ?? 0) }) }}</p><div v-if="confirmation === 'repair'" class="engine-defects"><p v-if="plan?.packages.length">{{ t('缺损依赖：{packages}', { packages: plan.packages.join(', ') }) }}</p><p v-if="plan?.source_paths.length">{{ t('缺损训练源码：{count} 个文件', { count: plan.source_paths.length }) }}</p><p v-for="(issue, index) in plan?.issues.slice(0, 5)" :key="index">{{ issue.message ?? issue.path ?? issue.kind ?? issue.code }}</p></div><details><summary>{{ t('查看文件与依赖详情') }}</summary><p v-if="plan?.packages.length">{{ t('依赖：{packages}', { packages: plan.packages.join(', ') }) }}</p><ul><li v-for="directory in plan?.write_roots" :key="directory">{{ directory }}</li><li v-for="source in plan?.source_paths" :key="source">{{ source }}</li></ul></details></template><p v-if="targetBusy" class="gui-issue" role="status">{{ inspection?.activity?.message || t('该引擎正在使用或变更，暂不可修改。') }}</p><p v-if="notice" role="status">{{ notice }}</p><p v-if="error" role="alert" class="gui-issue">{{ error }}</p><div class="engine-confirm-actions"><button ref="cancelButton" :disabled="Boolean(querying)" @click="dismiss">{{ t('取消') }}</button><button class="primary" :disabled="applyDisabled || disabled || Boolean(querying) || targetBusy" @click="apply">{{ querying ? t('正在检查…') : confirmAction }}</button></div></section></div>
  </section>
</template>

<style scoped>
.engine-row{display:flex;align-items:center;gap:17px;min-height:88px;padding:12px 16px 12px 9px;border-bottom:1px solid var(--line)}.engine-row:last-of-type{border-bottom:0}.engine-row:hover{background:var(--text-hover-bg)}.engine-emblem{height:43px;width:43px;display:grid;place-items:center;flex-shrink:0;border-radius:10px;font-size:25px;font-weight:400;border:1px solid var(--line)}.kohya{background:var(--engine-kohya-bg);color:var(--engine-kohya-fg)}.anima{background:var(--engine-anima-bg);color:var(--engine-anima-fg)}.toolkit{background:var(--engine-toolkit-bg);color:var(--engine-toolkit-fg);font-size:18px}.diffsynth{background:var(--engine-diffsynth-bg);color:var(--engine-diffsynth-fg)}.engine-copy{flex:1;min-width:0}.engine-copy h2{font-size:14px;font-weight:550;margin:0;display:flex;align-items:center;gap:15px}.engine-copy p{font-size:12px;color:var(--text-secondary);margin:5px 0}.engine-copy .engine-busy{color:var(--warning,#dfb56f)}.engine-actions button{min-width:118px;font-size:13px}.engine-actions svg{width:14px;height:14px;margin-right:5px}.engine-management{margin:15px 0;padding:17px;border:1px solid var(--line);border-radius:6px;background:var(--panel-soft)}.engine-management h2{font-size:14px;margin:0}.engine-management details{margin-top:13px}.engine-management summary{cursor:pointer;color:var(--text-secondary);font-size:12px;padding:7px 0}.engine-management .actions{display:flex;gap:8px;flex-wrap:wrap}.engine-management code{overflow-wrap:anywhere}.engine-issues{font-size:12px;line-height:1.7;color:var(--text-secondary);padding-left:20px}.engine-notice{font-size:13px}.engine-download{font-weight:600}.engine-defects{font-size:12px;overflow-wrap:anywhere}.engine-confirm li{font-size:12px;overflow-wrap:anywhere}@media(max-width:1080px){.engine-row{min-height:80px;gap:14px;padding-right:12px}.engine-copy h2{font-size:13px;gap:12px}.engine-actions button{min-width:108px}}@media(min-height:800px){.engine-row{min-height:105px}}
</style>
