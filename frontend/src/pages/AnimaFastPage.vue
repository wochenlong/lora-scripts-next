<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { useI18n } from "vue-i18n"
import { animaFastApi, type AnimaFastStatus } from "../api/animaFast"
import TrainingPage from "./TrainingPage.vue"

withDefaults(defineProps<{ bare?: boolean }>(), { bare: false })
const trainingRef = ref<InstanceType<typeof TrainingPage>>()
defineExpose({
  saveConfig: () => trainingRef.value?.saveConfig(),
  openImport: () => trainingRef.value?.openImport(),
  resetConfig: () => trainingRef.value?.resetConfig(),
})

const status=ref<AnimaFastStatus>({state:"unknown",feature_enabled:true});const loading=ref(false);const logs=ref<string[]>([]);const progress=ref(0);const phase=ref("");let timer:number|undefined;let logSource:EventSource|undefined;let progressSource:EventSource|undefined
const {t}=useI18n()
const ready=computed(()=>status.value.state==="ready");const working=computed(()=>["installing","auditing"].includes(status.value.state));const label=computed(()=>{const key=`animaFast.state.${status.value.state}`;const translated=t(key);return translated===key?status.value.state:translated})
function stopPolling(){if(timer!==undefined){window.clearInterval(timer);timer=undefined}}
function closeStreams(){logSource?.close();progressSource?.close();logSource=undefined;progressSource=undefined}
function streams(taskId:string,logUrl?:string,progressUrl?:string){closeStreams();logSource=new EventSource(logUrl||`/api/plugins/anima-lora/install/log/stream/${taskId}`);logSource.onmessage=e=>{try{const d=JSON.parse(e.data);if(d.text)logs.value.push(d.text);if(d.done)logSource?.close()}catch{logs.value.push(e.data)}};progressSource=new EventSource(progressUrl||`/api/plugins/anima-lora/install/progress/stream/${taskId}`);progressSource.onmessage=e=>{try{const d=JSON.parse(e.data);if(d.type==="progress"){progress.value=Number(d.percent||0);phase.value=d.message||d.phase||""}if(d.done||d.type==="done")progressSource?.close()}catch{}}}
async function refresh(reportError=true){try{status.value=await animaFastApi.status();if(ready.value)stopPolling();const id=status.value.facts?.task_id;if(id&&working.value&&!logSource)streams(id)}catch(e){if(reportError)ElMessage.error(e instanceof Error?e.message:t("animaFast.msg.statusFail"))}}
async function install(repair=false){try{await ElMessageBox.confirm(t("animaFast.confirm.message"),repair?t("animaFast.confirm.repairTitle"):t("animaFast.confirm.installTitle"),{type:"warning"});loading.value=true;logs.value=[];progress.value=0;const d=repair?await animaFastApi.repair():await animaFastApi.install();if(d.already_ready){status.value=d.status||status.value;if(ready.value)stopPolling();return ElMessage.success(t("animaFast.msg.ready"))}if(d.task_id)streams(d.task_id,d.log_stream||d.log_stream_url,d.progress_stream||d.progress_stream_url);await refresh();ElMessage.success(t("animaFast.msg.started"))}catch(e){if(e!=="cancel"&&e!=="close")ElMessage.error(e instanceof Error?e.message:t("animaFast.msg.fail"))}finally{loading.value=false}}
onMounted(async()=>{await refresh();if(!ready.value)timer=window.setInterval(()=>refresh(false),2000)});onBeforeUnmount(()=>{stopPolling();closeStreams()})
</script>
<template><TrainingPage v-if="ready" ref="trainingRef" title="Anima LoRA Fast" area="anima-lora-fast" schema-name="anima-lora-fast" :bare="bare"><template #form-top><slot name="form-top" /></template></TrainingPage><div v-else class="fast-page" :class="{ bare }"><div class="fast-main"><slot name="form-top" /><section class="fast-intro"><span v-if="!bare" class="eyebrow">ANIMA FAST RUNTIME</span><h1 v-if="!bare">Anima LoRA Fast</h1><p v-if="!bare">{{t("animaFast.intro")}}</p><div class="fast-state" :data-state="status.state"><span>{{label}}</span><strong>{{status.state}}</strong></div><div v-if="status.facts?.audit?.errors?.length" class="audit-errors"><strong>{{t("animaFast.auditTitle")}}</strong><p v-for="error in status.facts.audit.errors" :key="error">{{error}}</p></div><div class="fast-actions"><button class="primary-action" :disabled="loading||working||!status.feature_enabled" @click="install(false)">{{working?t("animaFast.installWorking"):t("animaFast.install")}}</button><button v-if="status.state==='broken'" class="secondary-action" :disabled="loading" @click="install(true)">{{t("animaFast.repair")}}</button></div></section></div><aside class="install-console"><header><span>{{phase||t("animaFast.consoleIdle")}}</span><b>{{progress}}%</b></header><div class="install-progress"><i :style="{width:`${progress}%`}" /></div><pre>{{logs.length?logs.join('\n'):t("animaFast.consoleWaiting")}}</pre></aside></div></template>
