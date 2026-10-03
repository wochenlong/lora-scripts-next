<script setup lang="ts">
import { reactive, ref } from "vue"
import { useI18n } from "vue-i18n"
import { networkApi, type NetworkSettings, type NetworkState } from "../api/plugins"

const { t } = useI18n()
const loaded = ref(false)
const busy = ref(false)
const error = ref("")
const effective = ref<NetworkState['effective']>()
const draft = reactive<NetworkSettings>({ mode: "auto", http_proxy: "", https_proxy: "", no_proxy: "localhost,127.0.0.1,::1" })

async function load(event: Event) {
  if (!(event.target as HTMLDetailsElement).open || loaded.value || busy.value) return
  busy.value = true
  error.value = ""
  try {
    const state = await networkApi.get()
    Object.assign(draft, state.settings)
    effective.value = state.effective
    loaded.value = true
  } catch (reason) { error.value = reason instanceof Error ? reason.message : String(reason) }
  finally { busy.value = false }
}

async function save() {
  busy.value = true
  error.value = ""
  try {
    const state = await networkApi.save({ ...draft })
    Object.assign(draft, state.settings)
    effective.value = state.effective
  } catch (reason) { error.value = reason instanceof Error ? reason.message : String(reason) }
  finally { busy.value = false }
}
</script>

<template>
  <details class="network-settings" @toggle="load">
    <summary>{{ t('network.title') }}</summary>
    <p>{{ t('network.description') }}</p>
    <form @submit.prevent="save">
      <fieldset :disabled="busy || !loaded">
        <label>{{ t('network.mode') }}
          <select v-model="draft.mode">
            <option v-for="mode in ['auto', 'system', 'manual', 'direct']" :key="mode" :value="mode">{{ t(`network.${mode}`) }}</option>
          </select>
        </label>
        <template v-if="draft.mode === 'manual'">
          <label>HTTP <input v-model="draft.http_proxy" placeholder="http://127.0.0.1:7890" autocomplete="off"></label>
          <label>HTTPS <input v-model="draft.https_proxy" placeholder="http://127.0.0.1:7890" autocomplete="off"></label>
        </template>
        <label>{{ t('network.bypass') }} <input v-model="draft.no_proxy"></label>
        <button type="submit" class="secondary-action">{{ t('network.save') }}</button>
      </fieldset>
    </form>
    <p v-if="effective" role="status">
      {{ t('network.effective') }}: {{ t(`network.${effective.network_mode}`) }}
      · {{ effective.proxy_enabled ? t('network.viaProxy') : t('network.direct') }}
      {{ effective.https_proxy || effective.http_proxy }}
    </p>
    <p v-if="effective?.warning" role="status">{{ effective.warning }}</p>
    <p v-if="error" role="alert">{{ error }}</p>
  </details>
</template>

<style scoped>
.network-settings { margin-block: 1rem; padding: 1rem; border: 1px solid var(--border-color, #394352); border-radius: 8px; }
summary { cursor: pointer; }
fieldset { display: flex; flex-wrap: wrap; gap: 1rem; border: 0; padding: 0; }
label { display: flex; flex-direction: column; gap: 0.4rem; }
input, select { padding: 0.4rem; color: inherit; background: transparent; border: 1px solid var(--border-color, #394352); }
</style>
