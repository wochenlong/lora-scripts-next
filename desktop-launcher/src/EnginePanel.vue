<script setup lang="ts">
import { ref, watch } from 'vue'
import { invoke } from '@tauri-apps/api/core'
import type { OperationSnapshot } from './bridge'
import { formatBudgetBytes } from './download-budget'
const props=defineProps<{root:string;releaseId:string;disabled:boolean}>()
const emit=defineEmits<{operate:[label:string,action:()=>Promise<OperationSnapshot>]}>()
type Plan={plan_sha256:string;engine_id:string;release_id:string;kind:string;instance_id:string;download_bytes:number;packages:string[];source_paths:string[];write_roots:string[];issues:{message?:string;path?:string;kind?:string}[];status:string}
type Inspection={installation:string;instance_id?:string;generation?:number;dirty?:boolean;issues:{message?:string;path?:string;kind?:string}[];layout?:{environment_root?:string;engine_source_root?:string;profile_root?:string}}
const engines=[{id:'kohya',name:'Kohya'},{id:'anima-fast',name:'Anima Fast（快速版）'},{id:'ai-toolkit',name:'AI Toolkit（AI工具箱）'},{id:'diffsynth',name:'DiffSynth（扩散合成）'}]
const selected=ref('kohya'),inspection=ref<Inspection|null>(null),plan=ref<Plan|null>(null),busy=ref(false),error=ref('')
let epoch=0
watch(()=>[props.root,props.releaseId,selected.value],()=>{epoch++;inspection.value=null;plan.value=null;error.value=''})
async function query(action:string,rebuild=false){
  if(props.disabled||busy.value)return
  const serial=++epoch;busy.value=true;error.value='';plan.value=null
  try{
    const value=await invoke('query_engine_control',{root:props.root,releaseId:props.releaseId,engineId:selected.value,action,rebuild})
    if(serial!==epoch)return
    if(action==='inspect_readonly')inspection.value=value as Inspection
    else plan.value=value as Plan
  }catch(reason){if(serial===epoch)error.value=String(reason)}finally{busy.value=false}
}
function apply(action:string){
  const root=props.root,releaseId=props.releaseId,engineId=selected.value,reviewed=plan.value
  if(props.disabled||busy.value)return
  if(action==='repair_apply'&&!reviewed)return
  plan.value=null;inspection.value=null
  emit('operate','执行独立引擎操作',()=>invoke<OperationSnapshot>('apply_engine_control',{root,releaseId,engineId,action,plan:reviewed}))
}
const stateName=(value:string)=>({ready:'文件校验通过',missing:'尚未安装',dirty:'有未完成的变更',broken:'需要修复',unknown:'无法确认'}[value]??value)
</script>
<template>
  <section class="gui-diagnostics" aria-labelledby="engine-control-title">
    <div class="section-caption"><h2 id="engine-control-title">训练引擎独立环境</h2></div>
    <p class="hint">每个引擎使用独立的 Python、依赖和训练源码。文件检查通过后可单独探测解释器；训练就绪状态由具体任务检查。</p>
    <label>选择引擎<select v-model="selected" :disabled="disabled||busy"><option v-for="engine in engines" :key="engine.id" :value="engine.id">{{engine.name}}</option></select></label>
    <div class="actions"><button :disabled="disabled||busy" @click="query('inspect_readonly')">独立检查</button><button :disabled="disabled||busy" @click="query('plan_install')">预览独立安装</button><button :disabled="disabled||busy" @click="query('plan_repair')">预览精准修复</button><button :disabled="disabled||busy" @click="query('plan_install',true)">预览新实例重建</button></div>
    <p v-if="error" role="alert" class="gui-issue">{{error}}</p>
    <template v-if="inspection">
      <p>文件状态：{{stateName(inspection.installation)}}<span v-if="inspection.instance_id"> · 实例 {{inspection.instance_id}}</span></p>
      <p v-for="(issue,index) in inspection.issues" :key="index" class="gui-issue">{{issue.message??issue.path??issue.kind}}</p>
      <div class="actions"><button :disabled="disabled||busy||inspection.installation!=='ready'" @click="apply('probe_execute')">独立解释器探测</button><button :disabled="disabled||busy" @click="apply('recover')">恢复未完成变更</button></div>
    </template>
    <div v-if="plan" class="gui-recovery">
      <p>{{plan.kind==='install'?'安装到新实例':'精准修复当前实例'}} · 下载 {{formatBudgetBytes(plan.download_bytes)}} · 实例 {{plan.instance_id}}</p>
      <p v-if="plan.packages.length">依赖：{{plan.packages.join('、')}}</p><p v-if="plan.source_paths.length">训练源码：{{plan.source_paths.length}} 个文件</p>
      <ul><li v-for="directory in plan.write_roots" :key="directory">{{directory}}</li></ul>
      <p class="hint">确认后将下载清单中的固定资产并执行操作。失败或取消会保留恢复信息。</p>
      <button :disabled="disabled||busy" @click="apply('repair_apply')">确认执行此计划</button>
    </div>
  </section>
</template>
