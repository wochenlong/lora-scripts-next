<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue"
import { storeToRefs } from "pinia"
import { useRoute, useRouter } from "vue-router"
import { useI18n } from "vue-i18n"
import { ChatDotRound, Minus } from "@element-plus/icons-vue"
import {
  isSafePluginUiUrl,
  pluginsApi,
  type PluginConfirmationDecision,
  type PluginConfirmationProjection,
  type PluginHostExtension,
} from "../../api/plugins"
import { HostPluginBridge, type BridgeFrameTarget } from "../../extensions/pluginBridge"
import { createPluginFrameBridge, createPluginFrameInstanceId } from "../../extensions/pluginFrameBridge"
import { useExtensionsStore } from "../../stores/extensions"
import HostConfirmationLayer from "./HostConfirmationLayer.vue"

const PREFERENCE_PREFIX = "plugin-floating-panel:"
const DEFAULT_PANEL_WIDTH = 520
const DEFAULT_PANEL_HEIGHT = 680
const MIN_PANEL_WIDTH = 420
const MIN_PANEL_HEIGHT = 480
const MAX_PANEL_WIDTH = 760
const VIEWPORT_GUTTER = 32
const VIEWPORT_VERTICAL_RESERVE = 96
const route = useRoute()
const router = useRouter()
const { locale, t } = useI18n()
const extensionsStore = useExtensionsStore()
const { floatingExtensions } = storeToRefs(extensionsStore)
const activeExtension = computed(() => floatingExtensions.value[0] ?? null)
const frame = ref<HTMLIFrameElement | null>(null)
const frameSrc = ref("about:blank")
const panelOpen = ref(false)
const panelWidth = ref(DEFAULT_PANEL_WIDTH)
const panelHeight = ref(DEFAULT_PANEL_HEIGHT)
const viewportWidth = ref(window.innerWidth)
const pendingConfirmations = ref<PluginConfirmationProjection[]>([])
const confirmation = computed(
  () => pendingConfirmations.value.find((value) => value.pluginId === activeExtension.value?.pluginId) ?? null,
)
const confirmationBusy = ref(false)
const confirmationError = ref("")
let bridge: HostPluginBridge | null = null
let appearanceObserver: MutationObserver | null = null
let resizeOrigin: { x: number; y: number; width: number; height: number } | null = null

const panelStyle = computed(() =>
  viewportWidth.value > 768 ? { width: `${panelWidth.value}px`, height: `${panelHeight.value}px` } : undefined,
)

function preferenceKey(pluginId: string) {
  return `${PREFERENCE_PREFIX}${pluginId}`
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(Math.max(value, minimum), maximum)
}

function clampPanelSize(width: number, height: number) {
  const maxWidth = Math.max(1, Math.min(MAX_PANEL_WIDTH, window.innerWidth - VIEWPORT_GUTTER))
  const maxHeight = Math.max(1, window.innerHeight - VIEWPORT_VERTICAL_RESERVE)
  return {
    width: clamp(width, Math.min(MIN_PANEL_WIDTH, maxWidth), maxWidth),
    height: clamp(height, Math.min(MIN_PANEL_HEIGHT, maxHeight), maxHeight),
  }
}

function readPanelPreference(pluginId: string) {
  try {
    const value = JSON.parse(localStorage.getItem(preferenceKey(pluginId)) || "{}") as {
      open?: unknown
      width?: unknown
      height?: unknown
    }
    const size = clampPanelSize(
      typeof value.width === "number" && Number.isFinite(value.width) ? value.width : DEFAULT_PANEL_WIDTH,
      typeof value.height === "number" && Number.isFinite(value.height) ? value.height : DEFAULT_PANEL_HEIGHT,
    )
    return { open: value.open === true, ...size }
  } catch {
    return { open: false, ...clampPanelSize(DEFAULT_PANEL_WIDTH, DEFAULT_PANEL_HEIGHT) }
  }
}

function saveOpenPreference() {
  const extension = activeExtension.value
  if (!extension) return
  localStorage.setItem(
    preferenceKey(extension.pluginId),
    JSON.stringify({ open: panelOpen.value, width: panelWidth.value, height: panelHeight.value }),
  )
}

function applyPanelSize(width: number, height: number) {
  const size = clampPanelSize(width, height)
  panelWidth.value = size.width
  panelHeight.value = size.height
}

function stopResize() {
  if (!resizeOrigin) return
  resizeOrigin = null
  window.removeEventListener("pointermove", onResizeMove)
  window.removeEventListener("pointerup", stopResize)
  saveOpenPreference()
}

function onResizeMove(event: PointerEvent) {
  if (!resizeOrigin) return
  applyPanelSize(
    resizeOrigin.width + resizeOrigin.x - event.clientX,
    resizeOrigin.height + resizeOrigin.y - event.clientY,
  )
}

function startResize(event: PointerEvent) {
  if (window.innerWidth <= 768) return
  event.preventDefault()
  resizeOrigin = {
    x: event.clientX,
    y: event.clientY,
    width: panelWidth.value,
    height: panelHeight.value,
  }
  window.addEventListener("pointermove", onResizeMove)
  window.addEventListener("pointerup", stopResize)
}

function resizeWithKeyboard(event: KeyboardEvent) {
  const step = event.shiftKey ? 32 : 16
  const deltas: Partial<Record<string, [number, number]>> = {
    ArrowLeft: [step, 0],
    ArrowRight: [-step, 0],
    ArrowUp: [0, step],
    ArrowDown: [0, -step],
  }
  const delta = deltas[event.key]
  if (!delta) return
  event.preventDefault()
  applyPanelSize(panelWidth.value + delta[0], panelHeight.value + delta[1])
  saveOpenPreference()
}

function onViewportResize() {
  viewportWidth.value = window.innerWidth
  applyPanelSize(panelWidth.value, panelHeight.value)
}

function syncHostState() {
  bridge?.postHostState()
}

function disposeBridge() {
  bridge?.dispose()
  bridge = null
  frameSrc.value = "about:blank"
}

function upsertConfirmation(value: PluginConfirmationProjection) {
  pendingConfirmations.value = [value, ...pendingConfirmations.value.filter((item) => item.ticketId !== value.ticketId)]
  confirmationError.value = ""
}

async function refreshPendingConfirmations() {
  try {
    pendingConfirmations.value = await pluginsApi.listPendingConfirmations()
  } catch {
    pendingConfirmations.value = []
  }
}

async function activateExtension(extension: PluginHostExtension | null) {
  disposeBridge()
  if (!extension || !isSafePluginUiUrl(extension.ui.floatingPanel?.entryUrl, extension.pluginId)) {
    panelOpen.value = false
    pendingConfirmations.value = []
    return
  }
  const preference = readPanelPreference(extension.pluginId)
  panelOpen.value = preference.open
  panelWidth.value = preference.width
  panelHeight.value = preference.height
  await nextTick()
  const target = frame.value?.contentWindow
  if (!target) return
  bridge = createPluginFrameBridge({
    extension,
    placement: "floating-panel",
    instanceId: createPluginFrameInstanceId(),
    frameTarget: target as unknown as BridgeFrameTarget,
    router,
    route,
    locale: () => String(locale.value),
    onConfirmation: upsertConfirmation,
  })
  bridge.start()
  frameSrc.value = extension.ui.floatingPanel.entryUrl
}

async function resolveConfirmation(decision: PluginConfirmationDecision) {
  const current = confirmation.value
  if (!current || confirmationBusy.value) return
  confirmationBusy.value = true
  confirmationError.value = ""
  try {
    const resolved = await pluginsApi.resolveConfirmation(current.ticketId, decision)
    if (confirmation.value?.ticketId === current.ticketId && resolved.state === decision) {
      pendingConfirmations.value = pendingConfirmations.value.filter((item) => item.ticketId !== current.ticketId)
    }
    else confirmationError.value = t("extensionHost.confirmation.failed")
  } catch {
    confirmationError.value = t("extensionHost.confirmation.failed")
  } finally {
    confirmationBusy.value = false
  }
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

watch(locale, syncHostState)

onMounted(() => {
  window.addEventListener("keydown", onShortcut)
  window.addEventListener("resize", onViewportResize)
  appearanceObserver = new MutationObserver(syncHostState)
  appearanceObserver.observe(document.documentElement, { attributes: true, attributeFilter: ["class", "style"] })
  void extensionsStore.ensureLoaded().then(refreshPendingConfirmations)
})

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onShortcut)
  window.removeEventListener("resize", onViewportResize)
  appearanceObserver?.disconnect()
  appearanceObserver = null
  stopResize()
  disposeBridge()
})
</script>

<template>
  <div v-if="activeExtension" class="floating-extension-host" data-testid="floating-extension-host">
    <section
      v-show="panelOpen"
      class="floating-extension-panel"
      :style="panelStyle"
      :aria-label="activeExtension.displayName"
      data-testid="floating-extension-panel"
    >
      <button
        type="button"
        class="floating-extension-resize"
        :aria-label="t('extensionHost.resize')"
        data-testid="floating-extension-resize"
        @pointerdown="startResize"
        @keydown="resizeWithKeyboard"
      />
      <header class="floating-extension-header">
        <div>
          <strong>{{ activeExtension.displayName }}</strong>
          <small>{{ activeExtension.statusText || t(`extensionHost.state.${activeExtension.state}`) }}</small>
        </div>
        <button type="button" :aria-label="t('extensionHost.minimize')" @click="closePanel"><Minus aria-hidden="true" /></button>
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
      <ChatDotRound aria-hidden="true" />
      <i v-if="activeExtension.unreadCount" class="floating-extension-badge">{{
        activeExtension.unreadCount > 9 ? "9+" : activeExtension.unreadCount
      }}</i>
    </button>
    <HostConfirmationLayer
      v-if="confirmation"
      :confirmation="confirmation"
      :plugin-name="activeExtension.displayName"
      :busy="confirmationBusy"
      :error="confirmationError"
      @resolve="resolveConfirmation"
    />
  </div>
</template>
