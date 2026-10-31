<script setup lang="ts">
import { t, locale } from './i18n'
import AcrylicSelect from './AcrylicSelect.vue'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { invoke } from '@tauri-apps/api/core'

const props = defineProps<{ root: string; releaseId: string; disabled: boolean }>()
const emit = defineEmits<{ changed: [] }>()
interface TrustStatus { status: string; production_ready?: boolean; fixture_session?: boolean; fixture_id?: string; sequence?: number; accepted_at?: number; receipt_count?: number; available_cases?: string[]; reason?: string }
interface Receipt { sequence: number; accepted_at: number; envelope_raw: string }
interface TrustHistory { status: string; receipts: Receipt[]; revoked_releases?: string[] }
interface ReleaseNote { id: string; version: string; published_at: number }
const view = ref<TrustStatus | null>(null)
const history = ref<TrustHistory | null>(null)
const busy = ref(false), error = ref(''), notice = ref(''), fixtureConsent = ref(false), selectedCase = ref('valid-v1')
let epoch = 0
const caseNames: Record<string, string> = { 'valid-v1': '接受有效测试清单', 'rotate-v2': '验证密钥轮换', 'revoke-v3': '验证安全撤销', expired: '拒绝过期清单', 'wrong-platform': '拒绝错误平台', tampered: '拒绝被篡改清单', replay: '拒绝旧清单重放' }
const cases = computed(() => (view.value?.available_cases ?? []).filter((id) => Object.hasOwn(caseNames, id)))
const locked = computed(() => props.disabled || busy.value || !props.root.trim())
const mode = computed(() => view.value?.fixture_session ? '隔离测试会话' : view.value?.production_ready ? '签名发布目录' : '内置发布目录')
const date = (value?: number) => value ? new Date(value * 1000).toLocaleString(locale.value) : t("尚未接受新清单")
function releases(receipt: Receipt): ReleaseNote[] {
  try {
    const envelope = JSON.parse(receipt.envelope_raw) as { payload: string }
    const payload = JSON.parse(envelope.payload) as { releases?: { release: { id: string; version: string }; published_at: number }[] }
    return (payload.releases ?? []).map((item) => ({ ...item.release, published_at: item.published_at }))
  } catch { return [] }
}
async function control(action: 'status' | 'history' | 'open_fixture' | 'refresh', fixtureCase: string | null = null) {
  if (locked.value || (action === 'open_fixture' && !fixtureConsent.value)) return
  const serial = ++epoch, root = props.root
  busy.value = true; error.value = ''; notice.value = ''
  try {
    const result = await invoke<TrustStatus | TrustHistory>('catalog_control', { root, action, fixtureCase })
    if (serial !== epoch) return
    if (action === 'history') history.value = result as TrustHistory
    else if (action === 'status') view.value = result as TrustStatus
    else {
      notice.value = action === 'open_fixture' ? '已打开固定沙盒测试会话。' : (result as TrustStatus).reason ?? '清单校验已完成，当前启动版本由你另行选择。'
      const latest = await invoke<TrustStatus>('catalog_control', { root, action: 'status', fixtureCase: null })
      if (serial !== epoch) return
      view.value = latest
      history.value = null; fixtureConsent.value = false
      emit('changed')
    }
  } catch (reason) { if (serial === epoch) error.value = String(reason) }
  finally { if (serial === epoch) busy.value = false }
}
watch(() => [props.root, props.releaseId], () => { epoch++; view.value = null; history.value = null; busy.value = false; error.value = ''; notice.value = ''; fixtureConsent.value = false }, { flush: 'sync' })
onBeforeUnmount(() => { epoch++ })
</script>

<template>
  <section class="trust-panel" aria-labelledby="trust-panel-title">
    <div class="section-caption"><h2 id="trust-panel-title">{{ t("更新来源与可信历史") }}</h2><span v-if="view" class="mode">{{ t(mode) }}</span></div>
    <p class="hint">{{ t("检查更新会验证发布签名和兼容性。选用新版本前仍需你确认。") }}</p>
    <div class="actions"><button :disabled="locked" @click="control('status')">{{ t("查看更新来源") }}</button><button :disabled="locked" @click="control('refresh')">{{ t("检查更新") }}</button><button :disabled="locked" @click="control('history')">{{ t("查看可信历史") }}</button></div>
    <p v-if="busy" role="status">{{ t("正在校验发布信息…") }}</p>
    <p v-if="error" class="issue" role="alert">{{ error }}</p><p v-if="notice" role="status">{{ t(notice) }}</p>
    <template v-if="view">
      <p v-if="view.reason" class="hint">{{ view.reason }}</p>
      <dl v-if="view.fixture_session || view.production_ready"><div><dt>{{ t("最近接受") }}</dt><dd>{{ date(view.accepted_at) }}</dd></div><div><dt>{{ t("可信记录") }}</dt><dd>{{ t('{count} 条', { count: view.receipt_count ?? 0 }) }}</dd></div></dl>
    </template>
    <div v-if="history" class="history">
      <p v-if="!history.receipts?.length" class="hint">{{ t("尚无远端签名记录。内置版本的身份随本启动器保存。") }}</p>
      <p v-else class="hint">{{ t("这些记录已在本地重新核验签名及公钥链。历史清单过期或下架后，已接受版本仍保留离线身份；已知安全撤销会继续阻止选用。") }}</p>
      <article v-for="receipt in history.receipts" :key="receipt.sequence"><strong>{{ t('清单 {count}', { count: receipt.sequence }) }}</strong><span> · {{ t('接受于 {date}', { date: date(receipt.accepted_at) }) }}</span><ul><li v-for="release in releases(receipt)" :key="release.id">{{ release.version }} · {{ t('发布于 {date}', { date: date(release.published_at) }) }}<span v-if="release.id === releaseId"> {{ t("· 当前所选版本") }}</span></li></ul></article>
      <div v-if="history.revoked_releases?.length" class="issue"><strong>{{ t("已收到安全撤销") }}</strong><ul><li v-for="id in history.revoked_releases" :key="id">{{ id }}</li></ul><p>{{ t("相关安装和资料仍保留，请选择未受影响的版本。") }}</p></div>
    </div>
    <details v-if="!view?.fixture_session" class="fixture"><summary>{{ t("开发验证：打开隔离测试会话") }}</summary><p>{{ t("此操作只适用于专门新建的空沙盒目录。测试会话将使用公开测试签名，固定绑定本启动器；请选择独立目录，确认其中没有日常安装、模型或用户资料。") }}</p><label class="consent"><input v-model="fixtureConsent" type="checkbox" :disabled="locked" />{{ t("我确认当前目录是新建的隔离空沙盒，仅用于更新流程验证") }}</label><button :disabled="locked || !fixtureConsent" @click="control('open_fixture')">{{ t("在当前空沙盒打开测试会话") }}</button></details>
    <div v-else class="fixture"><p><strong>{{ t("当前目录正在使用公开测试签名。") }}</strong>{{ t("测试场景按固定清单执行，数据与正式安装分开。") }}</p><label>{{ t("验证场景") }}<AcrylicSelect v-model="selectedCase" :disabled="locked" :options="cases.map(id => ({ value: id, label: t(caseNames[id] ?? id) }))" :aria-label="t('验证场景')" /></label><button :disabled="locked || !cases.includes(selectedCase)" @click="control('refresh', selectedCase)">{{ t("运行所选验证") }}</button></div>
  </section>
</template>

<style scoped>
.trust-panel { margin-top: 18px; border-top: 1px solid var(--line); padding-top: 15px; font-size: 14px; line-height: 1.7; }
.section-caption,.actions { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.section-caption { justify-content: space-between; }.actions { margin-top: 10px; }.mode,.hint,dt { color: var(--text-muted); }
.issue { color: var(--error); overflow-wrap: anywhere; }.history article { padding: 9px 0; border-bottom: 1px solid var(--line); }.history ul { margin: 4px 0; }
dl { display: flex; gap: 24px; margin: 10px 0; }dd { margin: 2px 0 0; }.fixture { margin-top: 13px; padding: 10px; border: 1px solid var(--warning-line); border-radius: 3px; background: var(--warning-bg); }
summary { cursor: pointer; }.consent { display: flex; align-items: flex-start; gap: 6px; margin: 10px 0; }.consent input { margin-top: 4px; }.fixture .acrylic-select { margin: 0 8px; max-width: 100%; }button,select { font: inherit; }
</style>
