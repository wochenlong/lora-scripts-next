<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { invoke } from '@tauri-apps/api/core'
import type { OperationSnapshot } from './bridge'
import { formatBytes } from './bytes'

const props = defineProps<{ root: string; releaseId: string; disabled: boolean }>()
const emit = defineEmits<{ operate: [label: string, action: () => Promise<OperationSnapshot>]; changed: [] }>()
interface ImportRequest { release_id: string; source_root: string; profile_id: string; include_credentials: boolean; external_paths: { kind: string; path: string }[] }
interface CopyItem { source_relative: string; target_relative: string; bytes: number; target_bytes: number; transformation: string }
interface Reference { kind: string; absolute_path: string; exists: boolean; is_directory: boolean; metadata_bytes: number }
interface ImportPlan { request: ImportRequest; scan: { source_root: string; files: CopyItem[]; directories: string[]; references: Reference[]; excluded: string[]; unsupported: string[]; copy_bytes: number }; target_profile: string; conflicts: string[]; peak_copy_bytes: number; plan_sha256: string }
interface Binding { release_id: string; profile_id: string; environment_instance_ids: Record<string, string>; environment_generations: Record<string, number>; healthy_at: number | null }
interface BindingRequest { binding: Binding; expected_generation: number }
interface BindingPlan { request: BindingRequest; old_bindings: { current: Binding | null; previous_known_good: Binding | null } | null; plan_sha256: string }
const source = ref(''), profile = ref('imported'), selectedProfile = ref(''), importPlan = ref<ImportPlan | null>(null), bindingPlan = ref<BindingPlan | null>(null)
const confirmed = ref(false), bindingConfirmed = ref(false), busy = ref(false), error = ref(''), recoveryTransaction = ref(''), recoveryKind = ref<'import' | 'binding'>('import'), recoveryConfirmed = ref(false)
const isRollback = ref(false)
const locked = computed(() => props.disabled || busy.value || !props.root.trim() || !props.releaseId)
const transformed = computed(() => importPlan.value?.scan.files.filter((file) => file.transformation !== 'copy') ?? [])
let epoch = 0
function resetPlans() { importPlan.value = null; bindingPlan.value = null; confirmed.value = false; bindingConfirmed.value = false; error.value = '' }
watch(() => [props.root, props.releaseId, source.value, profile.value, selectedProfile.value], () => { epoch++; busy.value = false; resetPlans(); recoveryConfirmed.value = false }, { flush: 'sync' })
watch(() => [recoveryKind.value, recoveryTransaction.value], () => { recoveryConfirmed.value = false }, { flush: 'sync' })
onBeforeUnmount(() => { epoch++ })
async function chooseSource() {
  if (locked.value) return
  try { const path = await invoke<string | null>('choose_directory'); if (path) source.value = path }
  catch (reason) { error.value = String(reason) }
}
async function previewImport() {
  if (locked.value || !source.value.trim() || !profile.value.trim()) return
  const serial = ++epoch, root = props.root
  busy.value = true; resetPlans()
  const request: ImportRequest = { release_id: props.releaseId, source_root: source.value.trim(), profile_id: profile.value.trim(), include_credentials: false, external_paths: [] }
  try { const result = await invoke<ImportPlan>('preview_data_import', { root, request }); if (serial === epoch) importPlan.value = result }
  catch (reason) { if (serial === epoch) error.value = String(reason) }
  finally { if (serial === epoch) busy.value = false }
}
function operate(label: string, action: () => Promise<OperationSnapshot>) {
  error.value = ''
  emit('operate', label, async () => { const result = await action(); emit('changed'); return result })
}
function applyImport() {
  const plan = importPlan.value, root = props.root, releaseId = props.releaseId
  if (locked.value || !plan || !confirmed.value || plan.conflicts.length) return
  importPlan.value = null; confirmed.value = false
  selectedProfile.value = plan.request.profile_id
  operate('复制旧资料到新资料集', () => invoke<OperationSnapshot>('apply_data_import', { root, releaseId, request: plan.request, planSha256: plan.plan_sha256 }))
}
async function previewBinding(rollback = false) {
  if (locked.value || (!rollback && !selectedProfile.value.trim())) return
  const serial = ++epoch, root = props.root, releaseId = props.releaseId
  busy.value = true; error.value = ''; bindingPlan.value = null; bindingConfirmed.value = false
  try {
    const result = await invoke<BindingPlan>('preview_profile_binding', { root, releaseId, profileId: rollback ? '' : selectedProfile.value.trim(), rollback })
    if (serial === epoch) { bindingPlan.value = result; isRollback.value = rollback }
  } catch (reason) { if (serial === epoch) error.value = String(reason) }
  finally { if (serial === epoch) busy.value = false }
}
function applyBinding() {
  const plan = bindingPlan.value, root = props.root, releaseId = props.releaseId
  if (locked.value || !plan || !bindingConfirmed.value) return
  bindingPlan.value = null; bindingConfirmed.value = false
  operate(isRollback.value ? '恢复上一完整资料组合' : '选用资料与环境组合', () => invoke<OperationSnapshot>('apply_profile_binding', { root, releaseId, request: plan.request, planSha256: plan.plan_sha256 }))
}
function recover() {
  if (locked.value || !recoveryTransaction.value.trim() || !recoveryConfirmed.value) return
  const root = props.root, releaseId = props.releaseId, kind = recoveryKind.value, transaction = recoveryTransaction.value.trim()
  recoveryConfirmed.value = false
  operate('恢复未完成的资料操作', () => invoke<OperationSnapshot>('recover_data_operation', { root, releaseId, kind, transaction }))
}
</script>

<template>
  <section class="import-panel" aria-labelledby="import-panel-title">
    <h2 id="import-panel-title">导入旧资料与切换资料集</h2>
    <p class="hint">选择旧安装目录，先查看可复制的设置、预设和资料。模型、数据集及输出目录保留为原位置的引用；账号凭据默认排除。导入完成后可单独选择新资料集。</p>
    <div class="form-row"><label for="import-source">旧安装目录</label><div class="input-row"><input id="import-source" v-model="source" :disabled="locked" placeholder="选择需要读取的旧安装根目录" /><button :disabled="locked" @click="chooseSource">选择目录</button></div></div>
    <div class="form-row"><label for="import-profile">新资料集名称</label><input id="import-profile" v-model="profile" :disabled="locked" placeholder="例如 imported，不覆盖已有名称" /></div>
    <div class="actions"><button :disabled="locked || !source.trim() || !profile.trim()" @click="previewImport">扫描并预览导入</button></div>
    <p v-if="busy" role="status">正在读取并核对资料…</p><p v-if="error" class="issue" role="alert">{{ error }}</p>
    <div v-if="importPlan" class="review">
      <h3>待复制资料</h3><dl><div><dt>复制文件</dt><dd>{{ importPlan.scan.files.length }} 个 · {{ formatBytes(importPlan.scan.copy_bytes) }}</dd></div><div><dt>预计峰值占用</dt><dd>{{ formatBytes(importPlan.peak_copy_bytes) }}</dd></div><div class="wide"><dt>新资料集位置</dt><dd><code>{{ importPlan.target_profile }}</code></dd></div></dl>
      <p class="hint">峰值包含暂存副本。后端会检查剩余空间，执行前再次核对扫描结果；源资料有变化时需重新预览。</p>
      <details><summary>查看 {{ importPlan.scan.files.length }} 个文件的复制位置</summary><div class="table-scroll"><table><thead><tr><th>源文件</th><th>新资料中的位置</th><th>处理方式</th></tr></thead><tbody><tr v-for="file in importPlan.scan.files" :key="file.source_relative"><td>{{ file.source_relative }}</td><td>{{ file.target_relative }}</td><td>{{ file.transformation === 'copy' ? '原样复制' : '转换配置中的绝对路径' }}</td></tr></tbody></table></div></details>
      <p v-if="transformed.length" class="hint">{{ transformed.length }} 份配置会转换其中的绝对路径，原配置保留在旧目录。</p>
      <details v-if="importPlan.scan.references.length"><summary>保留在原位置的外部资料（{{ importPlan.scan.references.length }} 项）</summary><ul><li v-for="reference in importPlan.scan.references" :key="reference.absolute_path"><code>{{ reference.absolute_path }}</code> · {{ reference.exists ? reference.is_directory ? '目录可访问' : '文件可访问' : '路径不存在，需处理' }}</li></ul></details>
      <details v-if="importPlan.scan.excluded.length"><summary>排除的内容（{{ importPlan.scan.excluded.length }} 项）</summary><ul><li v-for="item in importPlan.scan.excluded" :key="item">{{ item }}</li></ul></details>
      <details v-if="importPlan.scan.unsupported.length" open><summary>需手动处理的内容（{{ importPlan.scan.unsupported.length }} 项）</summary><p class="hint">这些项目未列入自动复制清单，请保留旧安装供后续核对。</p><ul><li v-for="item in importPlan.scan.unsupported" :key="item">{{ item }}</li></ul></details>
      <div v-if="importPlan.conflicts.length" class="issue" role="alert"><strong>请先处理以下冲突，再重新扫描</strong><ul><li v-for="item in importPlan.conflicts" :key="item">{{ item }}</li></ul></div>
      <label class="consent"><input v-model="confirmed" type="checkbox" :disabled="locked || Boolean(importPlan.conflicts.length)" />我已审查复制清单、排除项和外部引用，确认复制到这个新资料集</label><button class="primary" :disabled="locked || !confirmed || Boolean(importPlan.conflicts.length)" @click="applyImport">确认复制资料</button>
    </div>
    <div class="binding-section"><h3>选用资料集</h3><p class="hint">切换会同时核对版本、独立环境和资料集的组合。请先停止训练器；通过启动检查后才会保存新的健康组合。</p><div class="input-row"><input v-model="selectedProfile" :disabled="locked" aria-label="要选用的资料集名称" placeholder="输入已导入的资料集名称" /><button :disabled="locked || !selectedProfile.trim()" @click="previewBinding()">预览切换</button><button :disabled="locked" @click="previewBinding(true)">预览恢复上一健康组合</button></div>
      <div v-if="bindingPlan" class="review"><h3>{{ isRollback ? '待恢复的完整组合' : '待选用的完整组合' }}</h3><dl><div><dt>资料集</dt><dd>{{ bindingPlan.request.binding.profile_id }}</dd></div><div class="wide"><dt>训练器版本</dt><dd><code>{{ bindingPlan.request.binding.release_id }}</code></dd></div></dl><p class="hint">将一起核对 {{ Object.keys(bindingPlan.request.binding.environment_instance_ids).length }} 个环境，避免资料与环境组合错配。</p><label class="consent"><input v-model="bindingConfirmed" type="checkbox" :disabled="locked" />我确认选用上面的版本、环境与资料集组合</label><button class="primary" :disabled="locked || !bindingConfirmed" @click="applyBinding">确认切换完整组合</button></div>
    </div>
    <details class="recovery"><summary>恢复未完成的资料操作</summary><p class="hint">复制或切换中断后，可使用操作日志中的事务编号继续恢复。恢复会校验原有记录，遇到未知变化时保留现场。</p><div class="input-row"><select v-model="recoveryKind" :disabled="locked" aria-label="恢复操作类型"><option value="import">资料复制</option><option value="binding">组合切换</option></select><input v-model="recoveryTransaction" :disabled="locked" placeholder="粘贴日志中的事务编号" aria-label="待恢复的事务编号" /></div><label class="consent"><input v-model="recoveryConfirmed" type="checkbox" :disabled="locked" />我确认恢复此编号对应的未完成操作</label><button :disabled="locked || !recoveryConfirmed || !recoveryTransaction.trim()" @click="recover">确认恢复</button></details>
  </section>
</template>

<style scoped>
.import-panel { margin-top: 18px; padding-top: 15px; border-top: 1px solid var(--line); font-size: 11px; line-height: 1.7; }h3 { font-size: 11px; margin: 0 0 7px; }.hint,dt { color: var(--fg-muted); }.form-row { display: grid; grid-template-columns: 90px minmax(0,1fr); align-items: center; gap: 9px; margin-top: 9px; }
.input-row,.actions { display: flex; gap: 7px; flex-wrap: wrap; align-items: center; }.input-row input { flex: 1; min-width: 160px; }.actions { margin-top: 10px; }input:not([type=checkbox]),select { border: 1px solid var(--input-border); border-bottom-color: var(--input-bottom); background: var(--input-bg); color: var(--fg); border-radius: 4px; padding: 7px 9px; min-width: 0; font: inherit; }input:disabled,select:disabled { background: var(--panel-soft); color: var(--fg-muted); opacity: .65; }.issue { color: var(--error); overflow-wrap: anywhere; }
.review,.recovery { margin-top: 12px; padding: 12px; border: 1px solid var(--line); background: var(--panel-soft); color: var(--fg); border-radius: 5px; }.binding-section { margin-top: 18px; }details { margin-top: 8px; }summary { cursor: pointer; }ul { margin: 6px 0; padding-left: 20px; }li,code,dd { overflow-wrap: anywhere; }dl { display: flex; gap: 12px 24px; flex-wrap: wrap; margin: 7px 0; }.wide { flex-basis: 100%; }dd { margin: 2px 0 0; }.consent { display: flex; gap: 6px; align-items: flex-start; margin: 12px 0 8px; }.consent input { margin-top: 4px; flex-shrink: 0; }button { font-size: 11px; }.table-scroll { max-height: 230px; overflow: auto; margin-top: 7px; }table { width: 100%; border-collapse: collapse; table-layout: fixed; }th,td { text-align: left; padding: 6px; border-bottom: 1px solid var(--line); vertical-align: top; overflow-wrap: anywhere; }th { color: var(--fg-secondary); background: var(--panel-faint); font-weight: 500; }td { color: var(--fg); }
</style>
