<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { storeToRefs } from "pinia"
import { useRoute, useRouter } from "vue-router"
import { useI18n } from "vue-i18n"
import { isSafePluginUiUrl, isValidPluginId, type PluginHostExtension } from "../../api/plugins"
import { HostPluginBridge, type BridgeFrameTarget } from "../../extensions/pluginBridge"
import { createPluginFrameBridge, createPluginFrameInstanceId } from "../../extensions/pluginFrameBridge"
import { useExtensionsStore } from "../../stores/extensions"

const route = useRoute()
const router = useRouter()
const { locale, t } = useI18n()
const extensionsStore = useExtensionsStore()
const { loading, error } = storeToRefs(extensionsStore)
const frame = ref<HTMLIFrameElement | null>(null)
const frameSrc = ref("about:blank")
let bridge: HostPluginBridge | null = null
let appearanceObserver: MutationObserver | null = null
const pluginId = computed(() => String(route.params.pluginId || ""))
const extension = computed(() => (isValidPluginId(pluginId.value) ? extensionsStore.find(pluginId.value) : undefined))
const settingsUrl = computed(() => {
  const value = extension.value?.ui.settings?.entryUrl
  return isSafePluginUiUrl(value, pluginId.value) ? value : ""
})

function disposeBridge() {
  bridge?.dispose()
  bridge = null
  frameSrc.value = "about:blank"
}

function syncHostState() {
  bridge?.postHostState()
}

async function activateExtension(value: PluginHostExtension | undefined) {
  disposeBridge()
  if (!value || !settingsUrl.value) return
  await nextTick()
  const target = frame.value?.contentWindow
  if (!target) return
  bridge = createPluginFrameBridge({
    extension: value,
    placement: "settings",
    instanceId: createPluginFrameInstanceId(),
    frameTarget: target as unknown as BridgeFrameTarget,
    router,
    route,
    locale: () => String(locale.value),
  })
  bridge.start()
  frameSrc.value = settingsUrl.value
}

watch(
  () => `${extension.value?.pluginId ?? ""}\u0000${settingsUrl.value}`,
  () => void activateExtension(extension.value),
  { immediate: true, flush: "post" },
)

watch(locale, syncHostState)

onMounted(() => {
  appearanceObserver = new MutationObserver(syncHostState)
  appearanceObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "style"] })
  void extensionsStore.ensureLoaded()
})
onBeforeUnmount(() => {
  appearanceObserver?.disconnect()
  appearanceObserver = null
  disposeBridge()
})
</script>

<template>
  <div class="plugin-extension-page plugin-settings-page">
    <header>
      <span class="eyebrow">{{ t("extensionHost.settings.eyebrow") }}</span>
      <h1>{{ extension?.displayName || t("extensionHost.settings.title") }}</h1>
      <p>{{ t("extensionHost.settings.subtitle") }}</p>
    </header>
    <section v-if="loading" class="plugin-extension-state" aria-live="polite">{{ t("extensionHost.loading") }}</section>
    <section v-else-if="error" class="plugin-extension-state is-error" role="alert">{{ error }}</section>
    <section v-else-if="!settingsUrl" class="plugin-extension-state">
      <h2>{{ t("extensionHost.settings.unavailable") }}</h2>
      <p>{{ t("extensionHost.settings.unavailableHint") }}</p>
    </section>
    <iframe
      v-else
      ref="frame"
      class="plugin-settings-frame"
      :src="frameSrc"
      :title="t('extensionHost.settings.frameTitle', { name: extension?.displayName || pluginId })"
      sandbox="allow-scripts"
      referrerpolicy="no-referrer"
    />
  </div>
</template>
