<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { storeToRefs } from "pinia"
import { useRoute, useRouter } from "vue-router"
import { useI18n } from "vue-i18n"
import { isSafePluginHostUrl, type PluginHostExtension } from "../../api/plugins"
import { HostPluginBridge, type BridgeFrameTarget } from "../../extensions/pluginBridge"
import type { BridgeCapability, BridgeRequestEnvelope } from "../../extensions/pluginBridgeSchemas"
import { useExtensionsStore } from "../../stores/extensions"

const PREFERENCE_PREFIX = "plugin-floating-panel:"
const HOST_IMPLEMENTED_CAPABILITIES = new Set<BridgeCapability>([
  "artifact.open",
  "navigation.openExternal",
  "navigation.openPluginRoute",
  "theme.get",
  "locale.get",
  "context.get",
])
const THEME_TOKEN_NAMES = ["--bg", "--surface", "--text", "--text-soft", "--border", "--accent", "--danger"] as const

const route = useRoute()
const router = useRouter()
const { locale, t } = useI18n()
const extensionsStore = useExtensionsStore()
const { floatingExtensions } = storeToRefs(extensionsStore)
const activeExtension = computed(() => floatingExtensions.value[0] ?? null)
const frame = ref<HTMLIFrameElement | null>(null)
const frameSrc = ref("about:blank")
const panelOpen = ref(false)
let bridge: HostPluginBridge | null = null

function preferenceKey(pluginId: string) {
  return `${PREFERENCE_PREFIX}${pluginId}`
}

function readOpenPreference(pluginId: string) {
  try {
    const value = JSON.parse(localStorage.getItem(preferenceKey(pluginId)) || "{}") as { open?: unknown }
    return value.open === true
  } catch {
    return false
  }
}

function saveOpenPreference() {
  const extension = activeExtension.value
  if (!extension) return
  localStorage.setItem(preferenceKey(extension.pluginId), JSON.stringify({ open: panelOpen.value }))
}

function themeTokens() {
  const styles = getComputedStyle(document.documentElement)
  return Object.fromEntries(THEME_TOKEN_NAMES.map((name) => [name, styles.getPropertyValue(name).trim()]))
}

function createInstanceId() {
  if (typeof globalThis.crypto.randomUUID === "function") return globalThis.crypto.randomUUID()
  const values = new Uint8Array(16)
  globalThis.crypto.getRandomValues(values)
  return Array.from(values, (value) => value.toString(16).padStart(2, "0")).join("")
}

function safeExternalUrl(value: unknown) {
  if (typeof value !== "string") return null
  try {
    const url = new URL(value)
    return ["http:", "https:"].includes(url.protocol) ? url.href : null
  } catch {
    return null
  }
}

function isOwnedPluginRoute(pluginId: string, value: unknown): value is string {
  if (typeof value !== "string" || !value.startsWith("/")) return false
  const encoded = encodeURIComponent(pluginId)
  return value === `/settings/plugins/${encoded}` || value.startsWith(`/plugins/${encoded}/`)
}

async function handleBridgeRequest(extension: PluginHostExtension, request: BridgeRequestEnvelope) {
  if (request.type === "theme.get") return { tokens: themeTokens() }
  if (request.type === "locale.get") return { locale: locale.value }
  if (request.type === "context.get") return { route: { name: route.name ?? null, path: route.path } }
  if (request.type === "artifact.open") {
    await router.push({
      name: "plugin-artifact-detail",
      params: { pluginId: extension.pluginId, artifactId: String(request.payload.artifactId) },
    })
    return { opened: true }
  }
  if (request.type === "navigation.openPluginRoute") {
    const destination = request.payload.route
    if (!isOwnedPluginRoute(extension.pluginId, destination)) throw new Error("Plugin route is outside this extension namespace.")
    await router.push(destination)
    return { opened: true }
  }
  if (request.type === "navigation.openExternal") {
    const destination = safeExternalUrl(request.payload.url)
    if (!destination) throw new Error("External URL is not allowed.")
    window.open(destination, "_blank", "noopener,noreferrer")
    return { opened: true }
  }
  throw new Error(`Bridge capability is not implemented by the generic host: ${request.type}`)
}

function disposeBridge() {
  bridge?.dispose()
  bridge = null
  frameSrc.value = "about:blank"
}

async function activateExtension(extension: PluginHostExtension | null) {
  disposeBridge()
  if (!extension || !isSafePluginHostUrl(extension.ui.floatingPanel?.entryUrl)) {
    panelOpen.value = false
    return
  }
  panelOpen.value = readOpenPreference(extension.pluginId)
  await nextTick()
  const target = frame.value?.contentWindow
  if (!target) return
  const grantedCapabilities = extension.capabilities.filter((capability) => HOST_IMPLEMENTED_CAPABILITIES.has(capability))
  bridge = new HostPluginBridge({
    pluginId: extension.pluginId,
    instanceId: createInstanceId(),
    frameTarget: target as unknown as BridgeFrameTarget,
    grantedCapabilities,
    handleRequest: (request) => handleBridgeRequest(extension, request),
    locale: () => String(locale.value),
    themeTokens,
  })
  bridge.start()
  frameSrc.value = extension.ui.floatingPanel.entryUrl
}

function togglePanel() {
  panelOpen.value = !panelOpen.value
  saveOpenPreference()
}

function closePanel() {
  panelOpen.value = false
  saveOpenPreference()
}

function onShortcut(event: KeyboardEvent) {
  if (event.ctrlKey && event.shiftKey && !event.altKey && !event.metaKey && event.key.toLowerCase() === "a") {
    event.preventDefault()
    togglePanel()
  }
}

watch(
  () => (activeExtension.value ? `${activeExtension.value.pluginId}\u0000${activeExtension.value.ui.floatingPanel?.entryUrl ?? ""}` : ""),
  () => void activateExtension(activeExtension.value),
  { immediate: true },
)

watch(frame, (value) => {
  if (value && activeExtension.value && !bridge) void activateExtension(activeExtension.value)
})

onMounted(() => {
  window.addEventListener("keydown", onShortcut)
  void extensionsStore.ensureLoaded()
})

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onShortcut)
  disposeBridge()
})
</script>

<template>
  <div v-if="activeExtension" class="floating-extension-host" data-testid="floating-extension-host">
    <section
      v-show="panelOpen"
      class="floating-extension-panel"
      :aria-label="activeExtension.displayName"
      data-testid="floating-extension-panel"
    >
      <header class="floating-extension-header">
        <div>
          <strong>{{ activeExtension.displayName }}</strong>
          <small>{{ activeExtension.statusText || t(`extensionHost.state.${activeExtension.state}`) }}</small>
        </div>
        <button type="button" :aria-label="t('extensionHost.minimize')" @click="closePanel">−</button>
      </header>
      <iframe
        ref="frame"
        class="floating-extension-frame"
        :src="frameSrc"
        :title="activeExtension.displayName"
        sandbox="allow-scripts"
        referrerpolicy="no-referrer"
      />
    </section>
    <button
      type="button"
      class="floating-extension-launcher"
      :class="{ 'is-open': panelOpen }"
      :aria-label="panelOpen ? t('extensionHost.minimize') : t('extensionHost.open', { name: activeExtension.displayName })"
      :aria-expanded="panelOpen"
      data-testid="floating-extension-launcher"
      @click="togglePanel"
    >
      <span aria-hidden="true">✦</span>
      <i v-if="activeExtension.unreadCount" class="floating-extension-badge">{{
        activeExtension.unreadCount > 9 ? "9+" : activeExtension.unreadCount
      }}</i>
    </button>
  </div>
</template>
