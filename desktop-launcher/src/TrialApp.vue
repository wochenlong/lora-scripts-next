<script setup lang="ts">
import { nextTick,onBeforeUnmount,onMounted,ref } from 'vue'
import { invoke } from '@tauri-apps/api/core'
import { getCurrentWindow } from '@tauri-apps/api/window'
import Icon from './LauncherIcon.vue'
const request=ref<{token:string;transaction:string;trial_mode:string}|null>(null),error=ref(''),recovery=ref<HTMLButtonElement>(),status=ref('正在验证只读恢复界面…')
let timer:ReturnType<typeof setInterval>|undefined
async function closeWindow(){try{await getCurrentWindow().close()}catch(reason){error.value=String(reason)}}
async function dragWindow(event:MouseEvent){if(event.button!==0||(event.target as HTMLElement).closest('button'))return;try{await getCurrentWindow().startDragging()}catch{}}
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
<template><div class="trial-shell"><header class="trial-titlebar" @mousedown="dragWindow"><img src="/assets/home-logo.webp" alt="Next Trainer" /><span>Next Trainer · 启动器恢复检查</span><button aria-label="关闭恢复检查窗口" @click="closeWindow"><Icon name="close" /></button></header><main class="trial"><h1>启动器只读恢复检查</h1><p>{{status}}</p><p>此窗口只用于验证启动器更新后的界面和恢复入口。</p><button ref="recovery" @click="checkRecovery">查看恢复入口</button><p v-if="error" role="alert">{{error}}</p></main></div></template>
<style scoped>
.trial-shell{height:100%;overflow:auto;background:#172a3d;color:#dbe7f6}.trial-titlebar{height:45px;display:flex;align-items:center;gap:10px;padding-left:15px;font-size:12px;user-select:none;border-bottom:1px solid #c9d9ed16}.trial-titlebar img{width:29px;height:29px;border-radius:6px}.trial-titlebar button{margin-left:auto;width:48px;height:44px;background:none;border:0;border-radius:0}.trial-titlebar button:hover{background:#c93849}.trial{max-width:680px;margin:60px auto;padding:32px;background:#22394f;border:1px solid #c6d8ef25;border-radius:10px;color:#dce9f9;font-family:system-ui,sans-serif}.trial h1{font-size:23px}.trial p{font-size:13px;line-height:1.8;color:#b7cbe2}.trial button{padding:10px 16px;background:#9db5d2;color:#142b45}.trial [role=alert]{color:#edbac3}
</style>
