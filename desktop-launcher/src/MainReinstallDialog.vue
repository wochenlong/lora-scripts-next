<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import Icon from './LauncherIcon.vue'
import { t } from './i18n'

const props = defineProps<{
  phase: 'preparing' | 'ready' | 'blocked' | 'error' | 'cancelled'
  root: string
  version: string
  reason: string
  progress: string
  shared: boolean
  connectionError: boolean
  download: string
}>()
const emit = defineEmits<{ cancel: []; confirm: [] }>()
const cancelButton = ref<HTMLButtonElement>()
const preparing = computed(() => props.phase === 'preparing')
const status = computed(() => ({
  preparing: t('正在准备重新安装…'),
  ready: t('安装计划已准备好'),
  blocked: t('暂时无法重新安装'),
  error: t('安装计划准备失败'),
  cancelled: t('已取消'),
}[props.phase]))

onMounted(async () => { await nextTick(); cancelButton.value?.focus() })
function trapFocus(event: KeyboardEvent) {
  if (event.key !== 'Tab') return
  const items = [...(event.currentTarget as HTMLElement).querySelectorAll<HTMLElement>('button:not(:disabled), summary, [tabindex="0"]')]
  const first = items[0], last = items[items.length - 1]
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
}
</script>

<template>
  <div class="dialog-backdrop" @keydown.esc.prevent.stop="emit('cancel')" @keydown="trapFocus">
    <section class="confirmation-dialog main-reinstall-dialog" role="dialog" aria-modal="true" aria-labelledby="main-reinstall-title" aria-describedby="main-reinstall-detail" :aria-busy="preparing" :data-reinstall-phase="phase">
      <header><h2 id="main-reinstall-title">{{ t('重新安装主程序环境') }}</h2><button class="icon-button" data-action="close-reinstall-main" :aria-label="t('关闭')" @click="emit('cancel')"><Icon name="close" /></button></header>
      <p id="main-reinstall-detail">{{ t('将在新目录安装主程序环境，验证通过后再切换。原环境会保留，训练引擎、模型和用户资料不变。这会重新下载缺少的主程序依赖。') }}</p>
      <section class="main-reinstall-status" :class="{ issue: phase === 'blocked' || phase === 'error' }" :role="phase === 'blocked' || phase === 'error' ? 'alert' : 'status'" aria-live="polite" aria-atomic="true">
        <div class="main-reinstall-status-title"><Icon :name="preparing ? 'refresh' : phase === 'ready' ? 'check' : 'info'" :class="{ spin: preparing }" /><strong>{{ status }}</strong></div>
        <p v-if="preparing">{{ progress || t('正在核对主程序环境…') }}</p>
        <p v-else-if="reason">{{ reason }}</p>
        <p v-if="connectionError">{{ t('暂时无法读取准备进度，正在重新连接；不会重复开始检查。') }}</p>
        <p v-if="preparing && shared">{{ t('此准备任务正在被其他页面共用。取消会同时停止共用的检查。') }}</p>
      </section>
      <p v-if="phase === 'ready'" class="main-reinstall-download">{{ t('预计下载：{size}', { size: download }) }}</p>
      <details class="main-reinstall-details"><summary>{{ t('查看安装详情') }}</summary><dl><div><dt>{{ t('目标版本') }}</dt><dd>{{ version }}</dd></div><div><dt>{{ t('安装目录') }}</dt><dd>{{ root }}</dd></div></dl></details>
      <div class="main-reinstall-actions"><button ref="cancelButton" data-action="cancel-reinstall-main" @click="emit('cancel')">{{ phase === 'blocked' || phase === 'error' ? t('关闭') : t('取消') }}</button><button class="primary" data-action="confirm-reinstall-main" :disabled="phase !== 'ready'" @click="emit('confirm')">{{ t('确认重新安装') }}</button></div>
    </section>
  </div>
</template>

<style scoped>
.main-reinstall-dialog{width:480px}
.main-reinstall-dialog>header{display:flex;align-items:center;justify-content:space-between;gap:16px}
.main-reinstall-dialog>header .icon-button{min-height:28px;width:28px;flex-shrink:0}
.main-reinstall-status{padding:14px 16px;border:1px solid var(--line);border-radius:6px;background:var(--control-bg)}
.main-reinstall-status-title{display:flex;align-items:center;gap:10px;color:var(--text-strong)}
.main-reinstall-status-title svg{width:17px;height:17px;flex-shrink:0}
.main-reinstall-status p{margin:8px 0 0;font-size:13px}
.main-reinstall-status.issue{border-color:var(--warning);background:var(--control-bg)}
.main-reinstall-download{font-weight:600;color:var(--text-strong)}
.main-reinstall-details{margin-top:16px;color:var(--text-secondary)}
.main-reinstall-details summary{cursor:pointer;line-height:2}
.main-reinstall-details dl{margin:8px 0 0;font-size:13px;line-height:1.75}
.main-reinstall-details dl>div{margin-top:8px}
.main-reinstall-details dt{color:var(--text-muted)}
.main-reinstall-details dd{margin:0;overflow-wrap:anywhere;color:var(--text-secondary)}
.main-reinstall-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:20px}
</style>
