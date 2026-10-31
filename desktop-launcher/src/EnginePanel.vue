<script setup lang="ts">
import { ref, watch } from 'vue'
import { invoke } from '@tauri-apps/api/core'
import type { OperationSnapshot } from './bridge'
import { formatBytes } from './bytes'
import Icon from './LauncherIcon.vue'
const props = defineProps<{ root: string; releaseId: string; disabled: boolean }>()
const emit = defineEmits<{ operate: [label: string, action: () => Promise<OperationSnapshot>] }>()
type Issue = { message?: string; path?: string; kind?: string }
type Plan = { plan_sha256: string; engine_id: string; release_id: string; kind: string; instance_id: string; download_bytes: number; packages: string[]; source_paths: string[]; write_roots: string[]; issues: Issue[]; status: string }
type Inspection = { installation: string; instance_id?: string; generation?: number; dirty?: boolean; issues: Issue[]; layout?: { environment_root?: string; engine_source_root?: string; profile_root?: string } }
const engines = [
  { id: 'kohya', name: 'Kohya', emblem: 'K', description: 'SD · SDXL · LoRA 与全量微调', style: 'kohya' },
  { id: 'anima-fast', name: 'Anima Fast', emblem: 'A', description: 'Anima 模型训练环境', style: 'anima' },
  { id: 'ai-toolkit', name: 'AI Toolkit', emblem: 'AI', description: '多模型训练工作流', style: 'toolkit' },
  { id: 'diffsynth', name: 'DiffSynth', emblem: 'D', description: 'DiffSynth 模型训练环境', style: 'diffsynth' },
]
const selected = ref('kohya'), inspections = ref<Record<string, Inspection>>({}), plan = ref<Plan | null>(null), busy = ref(false), error = ref(''), expanded = ref(false)
let epoch = 0
watch(() => [props.root, props.releaseId], () => { epoch++; inspections.value = {}; plan.value = null; busy.value = false; error.value = ''; expanded.value = false }, { flush: 'sync' })
watch(selected, () => { epoch++; plan.value = null; error.value = '' }, { flush: 'sync' })
async function query(action: string, rebuild = false) {
  if (props.disabled || busy.value) return
  const serial = ++epoch, engineId = selected.value; busy.value = true; error.value = ''; plan.value = null; expanded.value = true
  try {
    const value = await invoke('query_engine_control', { root: props.root, releaseId: props.releaseId, engineId, action, rebuild })
    if (serial !== epoch) return
    if (action === 'inspect_readonly') inspections.value[engineId] = value as Inspection
    else plan.value = value as Plan
  } catch (reason) { if (serial === epoch) error.value = String(reason) }
  finally { if (serial === epoch) busy.value = false }
}
function inspectEngine(id: string) { if (busy.value || props.disabled) return; selected.value = id; return query('inspect_readonly') }
function manage(id: string) { if (busy.value) return; selected.value = id; expanded.value = true }
function apply(action: string) {
  const root = props.root, releaseId = props.releaseId, engineId = selected.value, reviewed = plan.value
  if (props.disabled || busy.value || (action === 'repair_apply' && !reviewed)) return
  plan.value = null; delete inspections.value[engineId]
  emit('operate', `执行 ${engines.find(engine => engine.id === engineId)?.name ?? engineId} 独立操作`, () => invoke<OperationSnapshot>('apply_engine_control', { root, releaseId, engineId, action, plan: reviewed }))
}
const stateName = (value?: string) => ({ ready: '文件校验通过', missing: '尚未安装', dirty: '有未完成的变更', broken: '需要修复', unknown: '无法确认' }[value ?? ''] ?? '待独立检查')
</script>
<template>
  <section class="engine-list" aria-label="四个训练引擎独立环境">
    <article v-for="engine in engines" :key="engine.id" class="engine-row"><div class="engine-emblem" :class="engine.style">{{ engine.emblem }}</div><div class="engine-copy"><h2>{{ engine.name }}<span class="engine-state" :class="{ good: inspections[engine.id]?.installation === 'ready' }"><i v-if="inspections[engine.id]?.installation === 'ready'"></i>{{ busy && selected === engine.id ? '正在检查…' : stateName(inspections[engine.id]?.installation) }}</span></h2><p>{{ engine.description }}</p><div class="engine-meta">{{ inspections[engine.id]?.instance_id ? `独立实例 ${inspections[engine.id]?.instance_id}` : '独立 Python 与依赖 · 按需安装' }}</div></div><div class="engine-actions"><button class="quiet-button" :disabled="disabled || busy" @click="inspectEngine(engine.id)">独立检查</button><button :disabled="busy" @click="manage(engine.id)">管理<Icon name="arrow" /></button></div></article>
    <div v-if="expanded" class="engine-management"><div class="section-caption"><h2>{{ engines.find(engine => engine.id === selected)?.name }} · 独立环境</h2><button class="text-button" :disabled="busy" @click="expanded = false">收起</button></div><p class="hint">首次安装：先停止训练器服务，再点击“预览独立安装”，查看清单后“确认执行此计划”。文件检查与解释器探测分别执行，模型、显存与具体训练条件在训练网页中检查。</p><div class="actions"><button :disabled="disabled || busy" @click="query('plan_install')">预览独立安装</button><button :disabled="disabled || busy" @click="query('plan_repair')">预览精准修复</button><button :disabled="disabled || busy" @click="query('plan_install', true)">预览新实例重建</button><button :disabled="disabled || busy" @click="apply('recover')">恢复未完成变更</button></div><p v-if="error" role="alert" class="gui-issue">{{ error }}</p><template v-if="inspections[selected]"><p class="hint">文件状态：{{ stateName(inspections[selected]?.installation) }}<span v-if="inspections[selected]?.generation !== undefined"> · 代次 {{ inspections[selected]?.generation }}</span></p><p v-for="(issue, index) in inspections[selected]?.issues" :key="index" class="gui-issue">{{ issue.message ?? issue.path ?? issue.kind }}</p><p v-if="inspections[selected]?.layout?.environment_root" class="hint">环境路径：<code>{{ inspections[selected]?.layout?.environment_root }}</code></p><button :disabled="disabled || busy || inspections[selected]?.installation !== 'ready'" @click="apply('probe_execute')">独立解释器探测</button></template><div v-if="plan" class="gui-recovery"><p>{{ plan.kind === 'install' ? '安装到新实例' : '精准修复当前实例' }} · 下载 {{ formatBytes(plan.download_bytes) }} · 实例 {{ plan.instance_id }}</p><p v-if="plan.packages.length">依赖：{{ plan.packages.join('、') }}</p><p v-if="plan.source_paths.length">训练源码：{{ plan.source_paths.length }} 个文件</p><ul><li v-for="directory in plan.write_roots" :key="directory">{{ directory }}</li></ul><p v-for="(issue, index) in plan.issues" :key="index" class="gui-issue">{{ issue.message ?? issue.path ?? issue.kind }}</p><p class="hint">确认后将下载清单中的固定资产并执行操作。失败或取消会保留恢复信息。</p><button :disabled="disabled || busy" @click="apply('repair_apply')">确认执行此计划</button></div></div>
  </section>
</template>
<style scoped>
.engine-row{display:flex;align-items:center;gap:17px;min-height:80px;padding:10px 16px 10px 9px;border-bottom:1px solid var(--line)}.engine-row:last-of-type{border-bottom:0}.engine-row:hover{background:var(--text-hover-bg)}.engine-emblem{height:43px;width:43px;display:grid;place-items:center;flex-shrink:0;border-radius:10px;font-size:25px;font-weight:400;border:1px solid var(--line)}.kohya{background:var(--engine-kohya-bg);color:var(--engine-kohya-fg)}.anima{background:var(--engine-anima-bg);color:var(--engine-anima-fg)}.toolkit{background:var(--engine-toolkit-bg);color:var(--engine-toolkit-fg);font-size:18px}.diffsynth{background:var(--engine-diffsynth-bg);color:var(--engine-diffsynth-fg)}.engine-copy{flex:1;min-width:0}.engine-copy h2{font-size:14px;font-weight:550;margin:0;display:flex;align-items:center;gap:15px}.engine-copy p{font-size:12px;color:var(--text-secondary);margin:5px 0}.engine-meta{font-size:12px;color:var(--text-muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:420px}.engine-actions{display:flex;align-items:center;gap:15px}.engine-actions button{font-size:14px}.engine-actions>button:last-child{min-width:77px}.engine-actions svg{width:14px;height:14px}.engine-management{margin:15px 0;padding:17px;border:1px solid var(--line);border-radius:6px;background:var(--panel-soft)}.engine-management h2{font-size:14px;margin:0}.engine-management>button{font-size:14px}@media(max-width:1080px){.engine-row{min-height:76px;gap:14px;padding-right:12px}.engine-actions{gap:8px}.engine-copy h2{font-size:13px;gap:12px}.engine-meta{font-size:12px;max-width:310px}}@media(min-height:800px){.engine-row{min-height:105px}}
</style>
