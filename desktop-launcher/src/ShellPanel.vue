<script setup lang="ts">
import {ref,watch} from 'vue'
import {invoke} from '@tauri-apps/api/core'
const props=defineProps<{root:string;releaseId:string;disabled:boolean}>()
const busy=ref(false),error=ref(''),info=ref(''),plan=ref<{plan_sha256:string}|null>(null),confirmed=ref(false),transaction=ref('')
watch(()=>[props.root,props.releaseId],()=>{plan.value=null;confirmed.value=false;error.value='';info.value=''})
async function control(action:string){
 if(props.disabled||busy.value)return
 if(action==='launch'&&(!plan.value||!confirmed.value))return
 busy.value=true;error.value=''
 try{
  const value=await invoke<Record<string,unknown>>('shell_control',{root:props.root,releaseId:props.releaseId,action,mode:'normal',planSha256:plan.value?.plan_sha256??null,transaction:transaction.value||null})
  if(action==='preview')plan.value=value as {plan_sha256:string}
  info.value=String(value.reason??value.status??'预览已完成')
 }catch(reason){error.value=String(reason)}finally{busy.value=false}
}
</script>
<template><section class="gui-diagnostics"><h2>启动器更新与恢复</h2><p class="hint">生产更新渠道尚未配置。当前可在明确启用的空沙盒会话中验证同一包的更新与恢复；实际更新将退出启动器，由独立更新助手完成。</p><div class="actions"><button :disabled="disabled||busy" @click="control('status')">检查更新状态</button><button :disabled="disabled||busy" @click="control('preview')">预览沙盒更新</button></div><p v-if="info">{{info}}</p><p v-if="error" class="gui-issue" role="alert">{{error}}</p><div v-if="plan"><label><input v-model="confirmed" type="checkbox" :disabled="disabled||busy"/>确认退出启动器并执行已预览的更新</label><button :disabled="disabled||busy||!confirmed" @click="control('launch')">交给独立更新助手</button></div><label>恢复事务<input v-model="transaction" :disabled="disabled||busy" placeholder="shell-update-…"/></label><button :disabled="disabled||busy||!transaction" @click="control('recover')">继续恢复该更新</button></section></template>
