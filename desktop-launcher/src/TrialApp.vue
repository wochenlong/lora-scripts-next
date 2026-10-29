<script setup lang="ts">
import { nextTick,onBeforeUnmount,onMounted,ref } from 'vue'
import { invoke } from '@tauri-apps/api/core'
const request=ref<{token:string;transaction:string;trial_mode:string}|null>(null),error=ref(''),recovery=ref<HTMLButtonElement>(),status=ref('正在验证只读恢复界面…')
let timer:ReturnType<typeof setInterval>|undefined
async function checkRecovery(){if(request.value)await invoke('trial_recovery_available',{token:request.value.token})}
onMounted(async()=>{
 try{
  request.value=await invoke('trial_context')
  await nextTick();await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))
  if(!recovery.value?.isConnected)throw new Error('恢复入口未渲染')
  await checkRecovery();await invoke('trial_rendered',{token:request.value!.token})
  status.value='窗口与恢复入口已完成只读检查，正在等待更新助手确认。'
  timer=setInterval(()=>{void invoke('trial_poll').catch(reason=>{error.value=String(reason)})},250)
 }catch(reason){error.value=String(reason)}
})
onBeforeUnmount(()=>{if(timer)clearInterval(timer)})
</script>
<template><main class="trial"><h1>启动器只读恢复检查</h1><p>{{status}}</p><p>此窗口只用于验证启动器更新后的界面和恢复入口。</p><button ref="recovery" @click="checkRecovery">查看恢复入口</button><p v-if="error" role="alert">{{error}}</p></main></template>
<style scoped>.trial{max-width:680px;margin:72px auto;padding:32px;background:#fff;border:1px solid #dde3eb;border-radius:12px;color:#253349;font-family:system-ui,sans-serif}.trial p{line-height:1.8}.trial button{padding:10px 16px;border:1px solid #bdc9d8;border-radius:6px;background:#eef4fc}</style>
