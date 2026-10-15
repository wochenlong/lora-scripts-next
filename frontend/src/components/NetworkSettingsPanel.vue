<script setup lang="ts">
import { onMounted, reactive, ref } from "vue"
import { useI18n } from "vue-i18n"
import { networkApi, type NetworkSettings, type NetworkState } from "../api/plugins"

const { t } = useI18n()
const loaded = ref(false)
const busy = ref(false)
const error = ref("")
const effective = ref<NetworkState["effective"]>()
const draft = reactive<NetworkSettings>({
  mode: "auto",
  http_proxy: "",
  https_proxy: "",
  no_proxy: "localhost,127.0.0.1,::1",
})

async function load() {
  if (busy.value) return
  busy.value = true
  error.value = ""
  try {
    const state = await networkApi.get()
    Object.assign(draft, state.settings)
    effective.value = state.effective
    loaded.value = true
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason)
  } finally {
    busy.value = false
  }
}

async function save() {
  busy.value = true
  error.value = ""
  try {
    const state = await networkApi.save({ ...draft })
    Object.assign(draft, state.settings)
    effective.value = state.effective
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : String(reason)
  } finally {
    busy.value = false
  }
}

onMounted(() => { void load() })
</script>

<template>
  <section class="settings-card network-settings-card" data-testid="network-settings-card">
    <h2>{{ t("network.title") }}</h2>
    <small>{{ t("network.description") }}</small>

    <form class="network-settings-form" @submit.prevent="save">
      <fieldset :disabled="busy || !loaded">
        <label class="network-field">
          <span>{{ t("network.mode") }}</span>
          <select v-model="draft.mode" data-testid="network-mode">
            <option v-for="mode in ['auto', 'system', 'manual', 'direct']" :key="mode" :value="mode">{{ t(`network.${mode}`) }}</option>
          </select>
        </label>

        <template v-if="draft.mode === 'manual'">
          <label class="network-field">
            <span>HTTP</span>
            <input v-model="draft.http_proxy" placeholder="http://127.0.0.1:7890" autocomplete="off">
          </label>
          <label class="network-field">
            <span>HTTPS</span>
            <input v-model="draft.https_proxy" placeholder="http://127.0.0.1:7890" autocomplete="off">
          </label>
        </template>

        <label class="network-field network-field-wide">
          <span>{{ t("network.bypass") }}</span>
          <input v-model="draft.no_proxy" data-testid="network-bypass">
        </label>
      </fieldset>

      <div class="network-actions">
        <button type="submit" class="primary-action" :disabled="busy || !loaded">{{ t("network.save") }}</button>
        <button
          v-if="error"
          type="button"
          class="secondary-action"
          data-testid="network-retry"
          :disabled="busy"
          @click="load"
        >{{ t("datasetManage.retry") }}</button>
      </div>
    </form>

    <p v-if="effective" class="network-effective" role="status">
      {{ t("network.effective") }}:
      {{ t(`network.${effective.network_mode}`) }}
      ·
      {{ effective.proxy_enabled ? t("network.viaProxy") : t("network.direct") }}
      <code v-if="effective.https_proxy || effective.http_proxy">{{ effective.https_proxy || effective.http_proxy }}</code>
    </p>
    <p v-if="effective?.warning" class="network-warning" role="status">{{ effective.warning }}</p>
    <p v-if="error" class="network-error" role="alert">{{ error }}</p>
  </section>
</template>
